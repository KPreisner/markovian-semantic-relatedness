import type { ErrorResponse } from "@/lib/api";

/** An error with an HTTP status and the API's one error shape, `{"error": {code, message,
 * details?}}`. The BFF passes the API's errors through and adds its own codes:
 * `upstream_unavailable` (502), `upstream_timeout` (504), `upstream_invalid` (502: a response
 * that doesn't match the schema), and `invalid_request` (422). */
export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: ErrorResponse,
  ) {
    super(body.error.message);
  }

  static of(status: number, code: string, message: string, details?: unknown): HttpError {
    return new HttpError(status, {
      error: details === undefined ? { code, message } : { code, message, details },
    });
  }
}
