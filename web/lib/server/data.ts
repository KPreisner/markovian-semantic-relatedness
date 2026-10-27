import "server-only";

import { notFound } from "next/navigation";
import { connection } from "next/server";
import { v7 as uuidv7 } from "uuid";
import type { z } from "zod";

import { HttpError } from "@/lib/server/errors";
import { callApi, type Query } from "@/lib/server/msr-api";

/** A page's data, fetched on the server straight from the API (no BFF hop). The API's 404
 * becomes the not-found page; anything else reaches the nearest error boundary. */
export async function load<S extends z.ZodType>(
  path: string,
  schema: S,
  query?: Query,
): Promise<z.infer<S>> {
  // Per-request data: tell Cache Components not to prerender it (the correlation id reads the
  // clock, which a prerender can't).
  await connection();
  try {
    const { data } = await callApi({ path, schema, query, correlationId: uuidv7() });
    return data;
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) notFound();
    throw error;
  }
}
