import type { Metadata } from "next";
import { Suspense } from "react";

import { type SearchConcept, SearchView } from "@/components/search/search-view";
import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { zGetConceptResponse, zGetSearchResponse } from "@/lib/api/zod.gen";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Search results" };

export default function SearchResultsPage({ params }: PageProps<"/searches/[searchId]">) {
  return (
    <Suspense fallback={<ResultsSkeleton />}>
      <SearchContent params={params} />
    </Suspense>
  );
}

async function SearchContent({ params }: { params: PageProps<"/searches/[searchId]">["params"] }) {
  const { searchId } = await params;
  const search = await load(`/searches/${encodeURIComponent(searchId)}`, zGetSearchResponse, {
    limit: 1000,
  });
  // Each concept's matched terms (its top K), to color the matches by concept.
  const topK = Number(search.params.top_k_terms ?? 100);
  const concepts: SearchConcept[] = await Promise.all(
    search.concept_ids.map(async (id) => {
      const concept = await load(`/concepts/${id}`, zGetConceptResponse, { limit: topK });
      return {
        concept_id: id,
        root: concept.root.term,
        params: concept.params,
        terms: concept.terms.filter((t) => t.weight > 0).map((t) => t.term),
      };
    }),
  );
  const roots = concepts.map((c) => c.root).join(" × ");
  return (
    <>
      <PageHeader
        eyebrow={`search · ${search.model_id}`}
        title={<span className="text-gradient font-mono">{roots}</span>}
        lead={
          concepts.length > 1
            ? "Chunks scored by the geometric mean of each concept's score: a chunk ranks high only if it's relevant to every concept."
            : "Chunks scored by the summed weights of the concept terms they contain (each term counts once per chunk, as in the paper)."
        }
      />
      <div className="mx-auto w-full max-w-6xl px-4 py-10">
        <SearchView search={search} concepts={concepts} />
      </div>
    </>
  );
}

function ResultsSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-16">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-36 rounded-3xl" />
      ))}
    </div>
  );
}
