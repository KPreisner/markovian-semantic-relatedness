import { zTermsResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, queryOf } from "@/lib/server/route";

/** Autocomplete: `?prefix=` (case-sensitive) and `limit`. */
export async function GET(request: Request, ctx: RouteContext<"/api/models/[modelId]/terms">) {
  const { modelId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({
      path: `/models/${encodeURIComponent(modelId)}/terms`,
      query: queryOf(request, "prefix", "limit"),
      schema: zTermsResponse,
      correlationId,
    }),
  );
}
