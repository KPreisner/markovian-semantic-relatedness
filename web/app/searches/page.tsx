import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { ExampleFigure } from "@/components/explain/concept-example";
import { SearchIndexView } from "@/components/search/search-index";
import { KeyPoints } from "@/components/site/key-points";
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

const POINTS = [
  {
    title: "Semantic",
    body: "A paragraph can rank high without your word, through the words that mean the same thing.",
  },
  {
    title: "Ranked",
    body: "Each paragraph scores the total of its matched words' scores. With several concepts, a paragraph has to fit every one to rank high.",
  },
  {
    title: "Any chunk size",
    body: "Paragraphs here, but a chunk can be a sentence, a page, or a whole document.",
  },
  {
    title: "Raw text",
    body: "No preprocessing, no index, no embeddings; words are matched straight in the text.",
  },
];

export default function SearchesPage({ searchParams }: PageProps<"/searches">) {
  return (
    <>
      <PageHeader
        eyebrow="Search"
        title={
          <>
            Search by <em className="text-gradient pr-1">meaning</em>
          </>
        }
        lead="A search scores every paragraph of raw news text (CC-NEWS) with one or more concepts and puts the best matches first."
        aside={<ExampleFigure />}
      >
        <KeyPoints points={POINTS} />
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
        <p className="mb-6 text-sm text-muted-foreground">
          Every search run on this site. Open one to read its ranked paragraphs, with matches
          highlighted by concept.
        </p>
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
