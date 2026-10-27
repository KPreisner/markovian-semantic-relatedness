import type { Metadata } from "next";
import { Suspense } from "react";

import { ConceptView } from "@/components/concepts/concept-view";
import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { zGetConceptResponse } from "@/lib/api/zod.gen";
import { scoringLabel } from "@/lib/format";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Concept" };

export default function ConceptPage({ params }: PageProps<"/concepts/[conceptId]">) {
  return (
    <Suspense fallback={<ConceptSkeleton />}>
      <ConceptContent params={params} />
    </Suspense>
  );
}

async function ConceptContent({
  params,
}: {
  params: PageProps<"/concepts/[conceptId]">["params"];
}) {
  const { conceptId } = await params;
  const concept = await load(`/concepts/${encodeURIComponent(conceptId)}`, zGetConceptResponse, {
    limit: 200,
  });
  return (
    <>
      <PageHeader
        eyebrow={`concept · ${concept.model_id} · ${scoringLabel(concept.params)}`}
        title={<span className="text-gradient font-mono">{concept.root.term}</span>}
        lead="The terms a random walk from the chosen term reaches much sooner than usual: closer to it than they usually are to other terms."
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <ConceptView concept={concept} />
      </div>
    </>
  );
}

function ConceptSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-16">
      <Skeleton className="h-12 w-64 rounded-xl" />
      <Skeleton className="h-[60vh] rounded-3xl" />
    </div>
  );
}
