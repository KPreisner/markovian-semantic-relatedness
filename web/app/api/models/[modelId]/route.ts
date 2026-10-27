import { zGetModelResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle } from "@/lib/server/route";

export async function GET(request: Request, ctx: RouteContext<"/api/models/[modelId]">) {
  const { modelId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({
      path: `/models/${encodeURIComponent(modelId)}`,
      schema: zGetModelResponse,
      correlationId,
    }),
  );
}
