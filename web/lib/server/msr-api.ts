import "server-only";

import type { z } from "zod";

import { zErrorResponse } from "@/lib/api/zod.gen";
import { config } from "@/lib/server/config";
import { CORRELATION_HEADER } from "@/lib/server/correlation";
import { HttpError } from "@/lib/server/errors";
import { logger } from "@/lib/server/log";

// The server-only client for FastAPI (http://api:8000 inside the stack). Imported only by route
// handlers and server components; the browser never talks to the API.
//
// - Every response is validated with its generated Zod schema; a mismatch is a 502
//   `upstream_invalid`, never a silently wrong page.
// - GETs retry on 502/503/504 and on network errors (twice, with a short backoff). POSTs don't:
//   a retried search would start a second search.
// - The API's error bodies pass through with their status.

const RETRY_STATUSES = new Set([502, 503, 504]);
const GET_ATTEMPTS = 3;
const BACKOFF_MS = 200;

/** Query parameters; an array is sent as the parameter repeated (`?status=a&status=b`). */
export type Query = Record<string, string | number | readonly string[] | undefined | null>;

export type ApiCall<S extends z.ZodType> = {
  path: string;
  method?: "GET" | "POST";
  query?: Query;
  body?: unknown;
  /** The response body's schema (`zXxxResponse` from lib/api/zod.gen.ts). */
  schema: S;
  correlationId: string;
  /** Extra statuses whose body matches `schema` rather than the error shape (e.g. /health's
   * 503). */
  okStatuses?: number[];
  signal?: AbortSignal;
};

export type ApiResult<T> = { status: number; data: T };

export function apiUrl(path: string, query?: Query): URL {
  const url = new URL(path.replace(/^\//, ""), config().MSR_API_URL.replace(/\/?$/, "/"));
  for (const [key, value] of Object.entries(query ?? {})) {
    if (Array.isArray(value)) {
      for (const item of value) url.searchParams.append(key, item);
    } else if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

export async function callApi<S extends z.ZodType>(
  call: ApiCall<S>,
): Promise<ApiResult<z.infer<S>>> {
  const method = call.method ?? "GET";
  const url = apiUrl(call.path, call.query);
  const attempts = method === "GET" ? GET_ATTEMPTS : 1;
  const log = logger().child({
    correlation_id: call.correlationId,
    upstream: `${method} ${url.pathname}`,
  });

  for (let attempt = 1; ; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers: {
          Accept: "application/json",
          [CORRELATION_HEADER]: call.correlationId,
          ...(call.body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: call.body === undefined ? undefined : JSON.stringify(call.body),
        signal: anySignal(AbortSignal.timeout(config().MSR_API_TIMEOUT_MS), call.signal),
        cache: "no-store",
      });
    } catch (error) {
      const timedOut = error instanceof DOMException && error.name === "TimeoutError";
      if (attempt < attempts && !call.signal?.aborted) {
        log.warn({ attempt, error: String(error) }, "upstream_retry");
        await sleep(BACKOFF_MS * attempt);
        continue;
      }
      throw timedOut
        ? HttpError.of(504, "upstream_timeout", "the API didn't answer in time")
        : HttpError.of(502, "upstream_unavailable", "the API is unreachable");
    }

    if (
      RETRY_STATUSES.has(response.status) &&
      !call.okStatuses?.includes(response.status) &&
      attempt < attempts
    ) {
      log.warn({ attempt, status: response.status }, "upstream_retry");
      await response.body?.cancel();
      await sleep(BACKOFF_MS * attempt);
      continue;
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw HttpError.of(
        502,
        "upstream_invalid",
        `the API answered ${response.status} without JSON`,
      );
    }

    if (!response.ok && !call.okStatuses?.includes(response.status)) {
      const error = zErrorResponse.safeParse(body);
      throw error.success
        ? new HttpError(response.status, error.data)
        : HttpError.of(response.status, "upstream_error", `the API answered ${response.status}`);
    }

    const parsed = call.schema.safeParse(body);
    if (!parsed.success) {
      log.error({ issues: parsed.error.issues }, "upstream_invalid");
      throw HttpError.of(502, "upstream_invalid", "the API's response didn't match its schema");
    }
    return { status: response.status, data: parsed.data };
  }
}

function anySignal(...signals: (AbortSignal | undefined)[]): AbortSignal {
  return AbortSignal.any(signals.filter((s): s is AbortSignal => s !== undefined));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
