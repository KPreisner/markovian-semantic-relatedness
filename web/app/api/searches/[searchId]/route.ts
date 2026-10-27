import { zGetSearchResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, queryOf } from "@/lib/server/route";

export async function GET(request: Request, ctx: RouteContext<"/api/searches/[searchId]">) {
  const { searchId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({
      path: `/searches/${encodeURIComponent(searchId)}`,
      query: queryOf(request, "limit"),
      schema: zGetSearchResponse,
      correlationId,
    }),
  );
}
