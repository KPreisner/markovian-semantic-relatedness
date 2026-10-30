import Link from "next/link";
import { Suspense } from "react";

import { ConceptExample } from "@/components/explain/concept-example";
import { WalkGraph } from "@/components/explain/walk-graph";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { zHealthResponse, zListCorporaResponse, zListModelsResponse } from "@/lib/api/zod.gen";
import { formatCount } from "@/lib/format";
import { load } from "@/lib/server/data";

// The four things to do with MSR, in order; each card links to where you do it.
const STEPS = [
  {
    title: "Create a model",
    body: "Give it text split into chunks (here, Simple English Wikipedia paragraphs). Terms that share a chunk are linked, and the counts make a co-occurrence graph over the whole vocabulary. Models are built offline with the msr CLI; this demo's is ready to use.",
    action: {
      href: "/MarkovianSemanticRelatedness_april_25_2022.pdf#page=3",
      label: "How to build one ↗",
      newTab: true,
    },
  },
  {
    title: "Create a concept",
    body: "Pick a term. A random walk spreads out from it, and the terms it reaches much sooner than they're usually reached from everywhere else form its concept: weighted terms, with the chosen term at 100.",
    action: { href: "/concepts/new", label: "Build a concept →" },
  },
  {
    title: "Discover",
    body: "A concept answers “what is related to this term?” in the text the model was built from. It can turn up the needle in the haystack: a rare term tied closely to yours that a keyword search would never think to ask for.",
    action: { href: "/concepts", label: "Browse concepts →" },
  },
  {
    title: "Search, ranked by meaning",
    body: "The concept's weights rank chunks of any raw text: no tokenizing, no index, no embeddings, no training on the text being searched. Several concepts combine by geometric mean, so a chunk ranks high only if it fits every one.",
    action: { href: "/search", label: "Search with concepts →" },
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
            <div className="flex max-w-xl flex-col gap-3">
              <p className="text-xl font-semibold md:text-2xl">
                Give it a word. Find its hidden meaning.
              </p>
              <p className="text-lg text-muted-foreground">
                Unsupervised Markov random walks uncover related words, even ones that never appear
                beside it, each scored by how closely it belongs.
              </p>
              <p className="text-lg text-muted-foreground">
                Search any raw text by <em>meaning</em>, not keywords, ranked by those scores.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                asChild
                size="lg"
                className="bg-gradient h-12 px-7 text-base text-primary-foreground shadow-[0_0_40px_var(--glow)] transition-transform hover:scale-[1.03]"
              >
                <Link href="/concepts">Explore concepts →</Link>
              </Button>
            </div>
          </div>
          <WalkGraph className="rounded-3xl border bg-card/60 p-4 shadow-[0_0_80px_var(--glow)] backdrop-blur" />
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <h2 className="mb-8 text-4xl">How to use it</h2>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="flex flex-col rounded-2xl border bg-card p-5 transition-colors hover:border-primary/40"
            >
              <span className="text-gradient font-heading text-5xl leading-none">0{i + 1}</span>
              <h3 className="mt-2 font-sans text-base font-semibold tracking-normal">
                {step.title}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
              <div className="mt-auto pt-4">
                <Button asChild variant="outline" className="w-full">
                  {step.action.newTab ? (
                    <a href={step.action.href} target="_blank">
                      {step.action.label}
                    </a>
                  ) : (
                    <Link href={step.action.href}>{step.action.label}</Link>
                  )}
                </Button>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-16">
        <ConceptExample />
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
          href={tile.label === "workers" ? "/health" : "/concepts"}
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
