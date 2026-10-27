import { zGetConceptResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, queryOf } from "@/lib/server/route";

export async function GET(request: Request, ctx: RouteContext<"/api/concepts/[conceptId]">) {
  const { conceptId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({
      path: `/concepts/${encodeURIComponent(conceptId)}`,
      query: queryOf(request, "limit"),
      schema: zGetConceptResponse,
      correlationId,
    }),
  );
}
