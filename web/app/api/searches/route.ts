import { zCreateSearchBody, zCreateSearchResponse, zListSearchesResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, jsonBody, queryOf } from "@/lib/server/route";

/** Start a search: 202 with the search and its job. */
export async function POST(request: Request) {
  return handle(request, async ({ correlationId }) =>
    callApi({
      path: "/searches",
      method: "POST",
      body: await jsonBody(request, zCreateSearchBody),
      schema: zCreateSearchResponse,
      correlationId,
    }),
  );
}

/** The searches index: every search with its concepts, latest job, and stored hits. */
export async function GET(request: Request) {
  return handle(request, ({ correlationId }) =>
    callApi({
      path: "/searches",
      query: queryOf(request, "model", "corpus", "term", "status", "limit", "offset"),
      schema: zListSearchesResponse,
      correlationId,
    }),
  );
}
