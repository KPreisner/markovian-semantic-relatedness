import { zListModelsResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { handle } from "@/lib/server/route";

export async function GET(request: Request) {
  return handle(request, ({ correlationId }) =>
    callApi({ path: "/models", schema: zListModelsResponse, correlationId }),
  );
}
