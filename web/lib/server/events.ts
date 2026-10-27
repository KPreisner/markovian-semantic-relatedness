import "server-only";

import { createParser, type EventSourceMessage, type EventSourceParser } from "eventsource-parser";

import { zJobEventData } from "@/lib/api/zod.gen";
import { config } from "@/lib/server/config";
import { CORRELATION_HEADER, correlationId } from "@/lib/server/correlation";
import { HttpError } from "@/lib/server/errors";
import { logger } from "@/lib/server/log";
import { apiUrl } from "@/lib/server/msr-api";

// A job's progress, relayed from FastAPI's `GET /jobs/{id}/events` (Jobs and progress in the
// plan):
// - the browser's `Last-Event-ID` is forwarded, so its reconnect resumes where it stopped;
// - each event is validated against the generated Zod union and passed on unchanged with its
//   `id:`; one that doesn't match is logged and dropped;
// - ping comments are passed on, so proxies keep the connection open;
// - when the browser disconnects, the upstream request is aborted. That ends only FastAPI's
//   response, never the job.

const encoder = new TextEncoder();

export const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
};

export async function relayJobEvents(request: Request, jobId: string): Promise<Response> {
  const id = correlationId(request);
  const log = logger().child({ correlation_id: id, job_id: jobId });
  const upstream = new AbortController();
  request.signal.addEventListener("abort", () => upstream.abort(), { once: true });

  const lastEventId = request.headers.get("Last-Event-ID");
  // The timeout bounds only the wait for the response headers; the stream itself stays open.
  const timer = setTimeout(
    () => upstream.abort(new DOMException("no answer", "TimeoutError")),
    config().MSR_API_TIMEOUT_MS,
  );
  let response: Response;
  try {
    response = await fetch(apiUrl(`/jobs/${encodeURIComponent(jobId)}/events`), {
      headers: {
        Accept: "text/event-stream",
        [CORRELATION_HEADER]: id,
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      signal: upstream.signal,
      cache: "no-store",
    });
  } catch {
    return errorResponse(HttpError.of(502, "upstream_unavailable", "the API is unreachable"), id);
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok || !response.body) {
    // The API's 404/422 error body, passed through.
    const body = await response.json().catch(() => null);
    return Response.json(body ?? HttpError.of(response.status, "upstream_error", "").body, {
      status: response.status,
      headers: { [CORRELATION_HEADER]: id },
    });
  }

  const relayed = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(sseMessages())
    .pipeThrough(
      new TransformStream<Message, Uint8Array>({
        transform(message, controller) {
          const out = encode(message, log);
          if (out) controller.enqueue(encoder.encode(out));
        },
      }),
    );
  const reader = relayed.getReader();

  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) controller.close();
        else controller.enqueue(value);
      } catch (error) {
        // The upstream ended mid-stream: end ours; the browser reconnects with Last-Event-ID.
        if (!upstream.signal.aborted) log.warn({ error: String(error) }, "event_stream_broken");
        controller.close();
      }
    },
    cancel() {
      upstream.abort();
    },
  });

  return new Response(stream, { headers: { ...SSE_HEADERS, [CORRELATION_HEADER]: id } });
}

type Message = { kind: "event"; event: EventSourceMessage } | { kind: "comment"; text: string };

/** Upstream SSE text → events and comments, in the order they arrived. */
function sseMessages(): TransformStream<string, Message> {
  let parser: EventSourceParser;
  return new TransformStream<string, Message>({
    start(controller) {
      parser = createParser({
        onEvent: (event) => controller.enqueue({ kind: "event", event }),
        onComment: (text) => controller.enqueue({ kind: "comment", text }),
      });
    },
    transform(chunk) {
      parser.feed(chunk);
    },
  });
}

/** One upstream message as SSE text, or null to drop it. A valid event's data goes out exactly
 * as the API sent it. */
function encode(message: Message, log: ReturnType<typeof logger>): string | null {
  if (message.kind === "comment") return `: ${message.text.trim()}\n\n`; // a ping
  const { id, data } = message.event;
  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    log.warn({ data }, "event_not_json");
    return null;
  }
  const event = zJobEventData.safeParse(parsed);
  if (!event.success) {
    log.warn({ issues: event.error.issues }, "event_invalid");
    return null;
  }
  return `${id ? `id: ${id}\n` : ""}data: ${data}\n\n`;
}

function errorResponse(error: HttpError, id: string): Response {
  return Response.json(error.body, { status: error.status, headers: { [CORRELATION_HEADER]: id } });
}
