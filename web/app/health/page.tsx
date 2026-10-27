import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { HealthBoard } from "@/components/health/health-board";
import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { zHealthResponse } from "@/lib/api/zod.gen";
import { callApi } from "@/lib/server/msr-api";
import { v7 as uuidv7 } from "uuid";

export const metadata: Metadata = { title: "Health" };

export default function HealthPage() {
  return (
    <>
      <PageHeader
        eyebrow="Stack health"
        title={
          <>
            Is it <em className="text-gradient pr-1">running</em>?
          </>
        }
        lead="The API, its data stores and broker, the workers that answer, and the jobs in flight."
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
          <HealthLoader />
        </Suspense>
      </div>
    </>
  );
}

async function HealthLoader() {
  await connection();
  // The report's 503 still has a body; only an unreachable API leaves it null.
  const report = await callApi({
    path: "/health",
    schema: zHealthResponse,
    correlationId: uuidv7(),
    okStatuses: [503],
  })
    .then((r) => r.data)
    .catch(() => null);
  return <HealthBoard initial={report} />;
}
