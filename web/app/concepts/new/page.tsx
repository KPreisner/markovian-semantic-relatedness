import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { ConceptExplainer } from "@/components/workbench/concept-explainer";
import { Workbench } from "@/components/workbench/workbench";
import { zListModelsResponse } from "@/lib/api/zod.gen";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Build a concept" };

export default function BuildConceptPage() {
  return (
    <>
      <PageHeader
        eyebrow="Concepts"
        title={
          <>
            Build a <em className="text-gradient pr-1">concept</em>
          </>
        }
        lead="A concept is a query expansion with intuitive weights: the terms a random walk from your chosen term reaches much sooner than usual, each weighted against the chosen term's 100. Pick a model and a term. A concept built before opens at once; a new one is walked by a worker while you watch."
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<Skeleton className="h-96 rounded-2xl" />}>
          <WorkbenchLoader />
        </Suspense>
        <ConceptExplainer />
      </div>
    </>
  );
}

async function WorkbenchLoader() {
  return <Workbench models={await load("/models", zListModelsResponse)} />;
}
