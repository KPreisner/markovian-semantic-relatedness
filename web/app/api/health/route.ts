import { zHealthResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle } from "@/lib/server/route";

/** The stack's health report from the API (503 when it says `down`). */
export async function GET(request: Request) {
  return handle(request, ({ correlationId }) =>
    callApi({ path: "/health", schema: zHealthResponse, correlationId, okStatuses: [503] }),
  );
}
