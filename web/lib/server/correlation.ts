import { v7 as uuidv7, validate } from "uuid";

export const CORRELATION_HEADER = "X-Correlation-ID";

/** The request's correlation id if it sent a valid UUID, otherwise a new UUIDv7. The same id is
 * sent to FastAPI, stored on the jobs it creates, and logged by every service. */
export function correlationId(request: Request): string {
  const sent = request.headers.get(CORRELATION_HEADER);
  return sent && validate(sent) ? sent : uuidv7();
}
