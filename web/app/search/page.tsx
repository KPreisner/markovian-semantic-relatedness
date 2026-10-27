import type { Metadata } from "next";
import { Suspense } from "react";

import { type Chip, SearchBuilder } from "@/components/search/search-builder";
import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { zGetConceptResponse, zListCorporaResponse, zListModelsResponse } from "@/lib/api/zod.gen";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage({ searchParams }: PageProps<"/search">) {
  return (
    <>
      <PageHeader
        eyebrow="Search"
        title={
          <>
            Rank text by <em className="text-gradient pr-1">meaning</em>
          </>
        }
        lead="Each concept's top-weighted terms are matched as plain substrings in every paragraph of the corpus, so nothing is tokenized or indexed ahead of time."
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
          <SearchLoader searchParams={searchParams} />
        </Suspense>
      </div>
    </>
  );
}

async function SearchLoader({
  searchParams,
}: {
  searchParams: PageProps<"/search">["searchParams"];
}) {
  const { concepts } = await searchParams;
  const ids = (Array.isArray(concepts) ? concepts.join(",") : (concepts ?? ""))
    .split(",")
    .filter(Boolean);
  const [models, corpora, chosen] = await Promise.all([
    load("/models", zListModelsResponse),
    load("/corpora", zListCorporaResponse),
    Promise.all(
      ids
        .slice(0, 10)
        .map((id) =>
          load(`/concepts/${encodeURIComponent(id)}`, zGetConceptResponse, { limit: 1 }),
        ),
    ),
  ]);
  const initial: Chip[] = chosen
    .filter((c) => c.model_id === chosen[0].model_id)
    .map((c) => ({
      key: c.concept_id,
      root: c.root.term,
      model_id: c.model_id,
      concept_id: c.concept_id,
      job_id: null,
    }));
  return <SearchBuilder models={models} corpora={corpora} initial={initial} />;
}
