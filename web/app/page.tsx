import Link from "next/link";
import { Suspense } from "react";

import { WalkGraph } from "@/components/home/walk-graph";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { zHealthResponse, zListCorporaResponse, zListModelsResponse } from "@/lib/api/zod.gen";
import { formatCount } from "@/lib/format";
import { load } from "@/lib/server/data";

const STEPS = [
  {
    title: "Count co-occurrence",
    body: "Every paragraph of the source is a bag of terms. Terms that share one are joined, and the counts make a sparse graph over the whole vocabulary.",
  },
  {
    title: "Walk from the root",
    body: "A random walk spreads out from the root term, step by step. Each term's expected hitting time says how close it is to the root.",
  },
  {
    title: "Compare with reference terms",
    body: "Hitting times to a few dozen reference terms give each term's usual distance. Terms unusually close to the root, in standard deviations, form its concept.",
  },
  {
    title: "Search raw text",
    body: "The concept's weighted terms are matched in untokenized text, paragraph by paragraph. Several concepts combine by geometric mean, so a hit has to fit all of them.",
  },
];

export default function Home() {
  return (
    <>
      <section className="relative overflow-hidden border-b">
        <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
        {/* The aurora: two soft blooms of the accent colors behind the hero. */}
        <div className="pointer-events-none absolute -top-40 left-1/4 size-[36rem] rounded-full bg-primary/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 -bottom-48 size-[32rem] rounded-full bg-accent/15 blur-3xl" />
        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-16 md:grid-cols-[1.05fr_1fr] md:py-24">
          <div className="flex flex-col gap-6">
            <p className="font-mono text-xs tracking-[0.2em] text-muted-foreground uppercase">
              Markovian Semantic Relatedness
            </p>
            <h1 className="text-5xl leading-[1.02] md:text-7xl">
              Meaning, found by <em className="text-gradient pr-1">wandering</em>.
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              Give it a word. A random walk across a co-occurrence graph finds the terms that sit
              unusually close to it: its concept. Then it ranks paragraphs anywhere by that concept,
              with no embeddings and no training on the text being searched.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                asChild
                size="lg"
                className="bg-gradient h-12 px-7 text-base text-primary-foreground shadow-[0_0_40px_var(--glow)] transition-transform hover:scale-[1.03]"
              >
                <Link href="/workbench">Build a concept →</Link>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="h-12 px-7 text-base backdrop-blur"
              >
                <a href="/fastapi/docs">Explore the API</a>
              </Button>
            </div>
          </div>
          <WalkGraph className="rounded-3xl border bg-card/60 p-4 shadow-[0_0_80px_var(--glow)] backdrop-blur" />
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <h2 className="mb-8 text-4xl">How it works</h2>
        <ol className="grid gap-4 md:grid-cols-4">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="relative rounded-2xl border bg-card p-5 transition-colors hover:border-primary/40"
            >
              <span className="text-gradient font-heading text-5xl leading-none">0{i + 1}</span>
              <h3 className="mt-2 font-sans text-base font-semibold tracking-normal">
                {step.title}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-20">
        <Suspense fallback={<StackSkeleton />}>
          <StackStats />
        </Suspense>
      </section>
    </>
  );
}

async function StackStats() {
  const [models, corpora, health] = await Promise.all([
    load("/models", zListModelsResponse),
    load("/corpora", zListCorporaResponse),
    load("/health", zHealthResponse).catch(() => null),
  ]);
  const terms = models.reduce((sum, m) => sum + m.term_count, 0);
  const tiles = [
    {
      label: "models",
      value: formatCount(models.length),
      detail: models.map((m) => m.model_id).join(", ") || "none yet",
    },
    { label: "vocabulary", value: formatCount(terms), detail: "terms across the models" },
    {
      label: "corpora",
      value: formatCount(corpora.length),
      detail: corpora.map((c) => c.corpus_id).join(", ") || "none yet",
    },
    {
      label: "workers",
      value: health?.workers.count === null || !health ? "?" : formatCount(health.workers.count),
      detail: health ? `stack ${health.status}` : "health unavailable",
    },
  ];
  return (
    <div className="grid gap-4 md:grid-cols-4">
      {tiles.map((tile) => (
        <Link
          key={tile.label}
          href={tile.label === "workers" ? "/health" : "/workbench"}
          className="group rounded-2xl border bg-card p-5 transition-colors hover:border-primary/50"
        >
          <p className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
            {tile.label}
          </p>
          <p className="tabular mt-1 font-mono text-3xl font-semibold">{tile.value}</p>
          <p className="mt-1 truncate text-sm text-muted-foreground group-hover:text-foreground">
            {tile.detail}
          </p>
        </Link>
      ))}
    </div>
  );
}

function StackSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-28 rounded-2xl" />
      ))}
    </div>
  );
}
