import {
  zConceptsForRootResponse,
  zRequestConceptBody,
  zRequestConceptResponse,
} from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle, jsonBody, queryOf } from "@/lib/server/route";

/** Request a concept: 200 `ready` (cached) or 202 `pending` with the job building it. */
export async function POST(request: Request, ctx: RouteContext<"/api/models/[modelId]/concepts">) {
  const { modelId } = await ctx.params;
  return handle(request, async ({ correlationId }) =>
    callApi({
      path: `/models/${encodeURIComponent(modelId)}/concepts`,
      method: "POST",
      body: await jsonBody(request, zRequestConceptBody),
      schema: zRequestConceptResponse,
      correlationId,
    }),
  );
}

/** Cached concepts for `?root=`, without starting a job. */
export async function GET(request: Request, ctx: RouteContext<"/api/models/[modelId]/concepts">) {
  const { modelId } = await ctx.params;
  return handle(request, ({ correlationId }) =>
    callApi({
      path: `/models/${encodeURIComponent(modelId)}/concepts`,
      query: queryOf(request, "root"),
      schema: zConceptsForRootResponse,
      correlationId,
    }),
  );
}
