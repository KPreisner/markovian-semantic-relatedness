import "server-only";

import pino from "pino";

import { config } from "@/lib/server/config";

// JSON lines, one per event, with the request's correlation id bound by `route.ts` (as the
// Python services' structlog output carries it).
let root: pino.Logger | undefined;

export function logger(): pino.Logger {
  root ??= pino({
    level: config().LOG_LEVEL,
    base: { service: "web" },
    timestamp: pino.stdTimeFunctions.isoTime,
  });
  return root;
}
