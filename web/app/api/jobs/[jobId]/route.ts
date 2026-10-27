import { zGetJobResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle } from "@/lib/server/route";

export async function GET(request: Request, ctx: RouteContext<"/api/jobs/[jobId]">) {
  const { jobId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({ path: `/jobs/${encodeURIComponent(jobId)}`, schema: zGetJobResponse, correlationId }),
  );
}
