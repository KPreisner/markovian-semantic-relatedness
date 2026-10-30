import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { WalkGraph } from "@/components/explain/walk-graph";
import { PageHeader } from "@/components/site/page-header";
import { Button } from "@/components/ui/button";
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
        lead="A concept is the weighted set of terms that a random walk from your chosen term reaches much sooner than usual. Pick a model and a term to build one."
      >
        <div className="mt-2">
          <Button
            asChild
            className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            <Link href="/concepts">All concepts →</Link>
          </Button>
        </div>
      </PageHeader>
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<Skeleton className="h-96 rounded-2xl" />}>
          <WorkbenchLoader />
        </Suspense>
        <ConceptExplainer />
        <WalkGraph className="mx-auto mt-10 max-w-2xl rounded-3xl border bg-card/60 p-4 shadow-[0_0_60px_var(--glow)]" />
      </div>
    </>
  );
}

async function WorkbenchLoader() {
  return <Workbench models={await load("/models", zListModelsResponse)} />;
}
