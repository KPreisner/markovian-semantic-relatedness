import { zCreateSearchBody, zCreateSearchResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, jsonBody } from "@/lib/server/route";

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
