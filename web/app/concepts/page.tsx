import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { ConceptIndexView } from "@/components/concepts/concept-index";
import { PageHeader } from "@/components/site/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { zListConceptsResponse, zListModelsResponse } from "@/lib/api/zod.gen";
import { CONCEPT_INDEX } from "@/lib/index-filters";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Concepts" };

export default function ConceptsPage({ searchParams }: PageProps<"/concepts">) {
  return (
    <>
      <PageHeader
        eyebrow="Concepts"
        title={
          <>
            Every <em className="text-gradient pr-1">concept</em>
          </>
        }
        lead="Each concept built on this stack, with how it was built, and each one still building or failed. Open a building one to watch its walk."
      >
        <div className="mt-2">
          <Button
            asChild
            className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            <Link href="/concepts/new">Build a concept →</Link>
          </Button>
        </div>
      </PageHeader>
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<IndexSkeleton />}>
          <IndexContent searchParams={searchParams} />
        </Suspense>
      </div>
    </>
  );
}

async function IndexContent({
  searchParams,
}: {
  searchParams: PageProps<"/concepts">["searchParams"];
}) {
  const filters = CONCEPT_INDEX.parse(await searchParams);
  const [index, models] = await Promise.all([
    load("/concepts", zListConceptsResponse, CONCEPT_INDEX.apiQuery(filters)),
    load("/models", zListModelsResponse),
  ]);
  return <ConceptIndexView index={index} models={models} filters={filters} />;
}

function IndexSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-10 w-96 rounded-xl" />
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-24 rounded-2xl" />
      ))}
    </div>
  );
}
