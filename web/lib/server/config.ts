import "server-only";

import { z } from "zod";

// The BFF's settings, validated once. instrumentation.ts reads them at startup, so a bad value
// stops the server instead of failing the first request.
const Env = z.object({
  MSR_API_URL: z.url().default("http://api:8000"),
  MSR_API_TIMEOUT_MS: z.coerce.number().int().positive().default(10_000),
  LOG_LEVEL: z
    .string()
    .transform((level) => level.toLowerCase())
    .pipe(z.enum(["trace", "debug", "info", "warn", "warning", "error", "fatal", "silent"]))
    .transform((level) => (level === "warning" ? "warn" : level))
    .default("info"),
});

export type Config = z.infer<typeof Env>;

let cached: Config | undefined;

export function config(): Config {
  cached ??= Env.parse(process.env);
  return cached;
}

/** For tests: forget the parsed settings so the next call reads process.env again. */
export function resetConfig(): void {
  cached = undefined;
}
