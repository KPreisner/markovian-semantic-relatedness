import { relayJobEvents } from "@/lib/server/events";

/** The job's progress as Server-Sent Events, relayed from the API (see lib/server/events.ts). */
export async function GET(request: Request, ctx: RouteContext<"/api/jobs/[jobId]/events">) {
  const { jobId } = await ctx.params;
  return relayJobEvents(request, jobId);
}
