import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SearchIndexView } from "@/components/search/search-index";
import { PageHeader } from "@/components/site/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  zListCorporaResponse,
  zListModelsResponse,
  zListSearchesResponse,
} from "@/lib/api/zod.gen";
import { SEARCH_INDEX } from "@/lib/index-filters";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Searches" };

export default function SearchesPage({ searchParams }: PageProps<"/searches">) {
  return (
    <>
      <PageHeader
        eyebrow="Search"
        title={
          <>
            Every <em className="text-gradient pr-1">search</em>
          </>
        }
        lead="Each search run on this stack, with its concepts, corpus, and settings, and each one still running or failed. Open one to read its results again, or to see why it failed."
      >
        <div className="mt-2">
          <Button
            asChild
            className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            <Link href="/search">New search →</Link>
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
  searchParams: PageProps<"/searches">["searchParams"];
}) {
  const filters = SEARCH_INDEX.parse(await searchParams);
  const [index, models, corpora] = await Promise.all([
    load("/searches", zListSearchesResponse, SEARCH_INDEX.apiQuery(filters)),
    load("/models", zListModelsResponse),
    load("/corpora", zListCorporaResponse),
  ]);
  return (
    <SearchIndexView
      index={index}
      models={models.map((m) => m.model_id)}
      corpora={corpora.map((c) => c.corpus_id)}
      filters={filters}
    />
  );
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
