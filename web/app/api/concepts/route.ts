import { zListConceptsResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, queryOf } from "@/lib/server/route";

/** The concepts index: stored concepts and unfinished or failed concept jobs, newest first. */
export async function GET(request: Request) {
  return handle(request, ({ correlationId }) =>
    callApi({
      path: "/concepts",
      query: queryOf(request, "model", "term", "status", "limit", "offset"),
      schema: zListConceptsResponse,
      correlationId,
    }),
  );
}
