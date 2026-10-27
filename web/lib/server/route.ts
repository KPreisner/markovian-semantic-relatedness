import "server-only";

import type { z } from "zod";

import { CORRELATION_HEADER, correlationId } from "@/lib/server/correlation";
import { HttpError } from "@/lib/server/errors";
import { logger } from "@/lib/server/log";
import type { ApiResult } from "@/lib/server/msr-api";

export type RequestContext = { correlationId: string; request: Request };

/** Run a route handler's work and answer with its result: the upstream status and validated
 * body, or an error in the API's shape. Every response echoes the correlation id, and each
 * request logs one line. */
export async function handle<T>(
  request: Request,
  work: (ctx: RequestContext) => Promise<ApiResult<T>>,
): Promise<Response> {
  const id = correlationId(request);
  const started = performance.now();
  const headers = { [CORRELATION_HEADER]: id };
  let status = 500;
  try {
    const result = await work({ correlationId: id, request });
    status = result.status;
    return Response.json(result.data, { status, headers });
  } catch (error) {
    if (error instanceof HttpError) {
      status = error.status;
      return Response.json(error.body, { status, headers });
    }
    logger().error({ correlation_id: id, err: error }, "bff_error");
    return Response.json(HttpError.of(500, "internal_error", "the web server failed").body, {
      status,
      headers,
    });
  } finally {
    const { pathname } = new URL(request.url);
    logger().info(
      {
        correlation_id: id,
        method: request.method,
        path: pathname,
        status,
        ms: Math.round(performance.now() - started),
      },
      "response",
    );
  }
}

/** The request's JSON body, checked against the operation's generated schema. Unknown fields
 * are rejected, as the API rejects them. */
export async function jsonBody<S extends z.ZodObject>(
  request: Request,
  schema: S,
): Promise<z.infer<S>> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    throw HttpError.of(422, "invalid_request", "the request body isn't JSON");
  }
  const parsed = schema.strict().safeParse(body);
  if (!parsed.success) {
    throw HttpError.of(
      422,
      "invalid_request",
      "invalid request",
      parsed.error.issues.map((issue) => ({
        loc: ["body", ...issue.path],
        msg: issue.message,
        type: issue.code,
      })),
    );
  }
  // `strict()` keeps the shape, so the output is the schema's own.
  return parsed.data as z.infer<S>;
}

/** The given query parameters of the request, for passing on to the API. */
export function queryOf(request: Request, ...names: string[]): Record<string, string | undefined> {
  const params = new URL(request.url).searchParams;
  return Object.fromEntries(names.map((name) => [name, params.get(name) ?? undefined]));
}
