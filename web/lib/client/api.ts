// The browser's calls, all to the BFF's own /api/* routes (which validate the API's responses).

import type { ErrorResponse } from "@/lib/api";

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const response = await fetch(`/api${path}`, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(json === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: json === undefined ? rest.body : JSON.stringify(json),
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as ErrorResponse | null)?.error;
    throw new ApiRequestError(
      response.status,
      error?.code ?? "request_failed",
      error?.message ?? `the server answered ${response.status}`,
      error?.details,
    );
  }
  return body as T;
}
