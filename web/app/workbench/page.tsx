import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Workbench } from "@/components/workbench/workbench";
import { zListModelsResponse } from "@/lib/api/zod.gen";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Workbench" };

export default function WorkbenchPage() {
  return (
    <>
      <PageHeader
        eyebrow="Workbench"
        title={
          <>
            Build a <em className="text-gradient pr-1">concept</em>
          </>
        }
        lead="Pick a model and a chosen term. A cached concept opens at once; a new one is walked by a worker while you watch."
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<Skeleton className="h-96 rounded-2xl" />}>
          <WorkbenchLoader />
        </Suspense>
      </div>
    </>
  );
}

async function WorkbenchLoader() {
  return <Workbench models={await load("/models", zListModelsResponse)} />;
}
