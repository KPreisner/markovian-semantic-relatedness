// The SSE relay against a stub API stream: valid events pass with their ids, pings pass,
// invalid events are dropped, Last-Event-ID is forwarded, and a disconnect aborts the upstream.
import type { IncomingMessage, ServerResponse } from "node:http";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { GET as events } from "@/app/api/jobs/[jobId]/events/route";
import { CONCEPT_ID } from "./fixtures";
import { StubApi } from "./stub-api";

const api = new StubApi();

beforeAll(() => api.start());
afterAll(() => api.stop());
beforeEach(() => api.reset());

const PROGRESS = {
  type: "progress",
  phase: "walk",
  step: 1,
  total: 100,
  message: "walking 'cat'",
  bytes_scanned: null,
  hits: null,
};
const RESULT = { type: "result", result_id: CONCEPT_ID };

function streamHead(res: ServerResponse) {
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
}

function request(headers: Record<string, string> = {}, signal?: AbortSignal) {
  return new Request("http://web/api/jobs/j1/events", { headers, signal });
}

const ctx = { params: Promise.resolve({ jobId: "j1" }) };

async function text(response: Response): Promise<string> {
  return new Response(response.body).text();
}

describe("GET /api/jobs/[jobId]/events", () => {
  it("relays valid events with their ids and pings, and drops invalid ones", async () => {
    api.on("GET /jobs/j1/events", (_req: IncomingMessage, res: ServerResponse) => {
      streamHead(res);
      res.write(`id: 1-0\ndata: ${JSON.stringify(PROGRESS)}\n\n`);
      res.write(": ping\n\n");
      res.write(`id: 2-0\ndata: ${JSON.stringify({ type: "progress", phase: "walk" })}\n\n`); // no step
      res.write("id: 3-0\ndata: not json\n\n");
      res.end(`id: 4-0\ndata: ${JSON.stringify(RESULT)}\n\n`);
    });
    const response = await events(request(), ctx);
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("text/event-stream; charset=utf-8");
    expect(response.headers.get("Cache-Control")).toBe("no-cache, no-transform");
    expect(await text(response)).toBe(
      `id: 1-0\ndata: ${JSON.stringify(PROGRESS)}\n\n` +
        ": ping\n\n" +
        `id: 4-0\ndata: ${JSON.stringify(RESULT)}\n\n`,
    );
  });

  it("forwards Last-Event-ID so a reconnect resumes", async () => {
    api.on("GET /jobs/j1/events", (_req, res) => {
      streamHead(res);
      res.end();
    });
    await text(await events(request({ "Last-Event-ID": "1-0" }), ctx));
    expect(api.seen[0].headers["last-event-id"]).toBe("1-0");
    expect(api.seen[0].headers.accept).toBe("text/event-stream");
  });

  it("aborts the upstream request when the browser disconnects", async () => {
    let closed!: () => void;
    const upstreamClosed = new Promise<void>((resolve) => (closed = resolve));
    api.on("GET /jobs/j1/events", (req, res) => {
      streamHead(res);
      res.write(`id: 1-0\ndata: ${JSON.stringify(PROGRESS)}\n\n`); // and then nothing: a long job
      req.socket.on("close", () => closed());
    });
    const browser = new AbortController();
    const response = await events(request({}, browser.signal), ctx);
    const reader = response.body!.getReader();
    await reader.read(); // the first event arrived
    browser.abort();
    await reader.cancel();
    await expect(upstreamClosed).resolves.toBeUndefined();
  });

  it("passes the API's 404 through as JSON", async () => {
    const body = { error: { code: "job_not_found", message: "no job j1" } };
    api.json("GET /jobs/j1/events", 404, body);
    const response = await events(request(), ctx);
    expect([response.status, await response.json()]).toEqual([404, body]);
  });
});
