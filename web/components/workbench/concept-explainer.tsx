import Link from "next/link";

import { formatWeight } from "@/lib/format";

// Illustrative weights in the shape a concept has: the chosen term at 100, the rest far below.
const EXAMPLE = [
  { term: "xylophone", weight: 100 },
  { term: "glockenspiel", weight: 26.2 },
  { term: "marimba", weight: 18.5 },
  { term: "vibraphone", weight: 12.1 },
];
const weightOf = new Map(EXAMPLE.map((t) => [t.term, t.weight]));

// Two chunks, split into plain text and matched terms.
const CHUNKS: (string | { term: string })[][] = [
  ["The ", { term: "xylophone" }, " solo opened the show."],
  [
    "For the second movement the percussionist moved from the ",
    { term: "marimba" },
    " to the ",
    { term: "glockenspiel" },
    ".",
  ],
  ["The orchestra tuned up before the concert."],
];

const STEPS = [
  {
    title: "A walk from the chosen term",
    body: "The model is a graph: each term is linked to the terms it shares chunks with, more strongly the more often they do. A random walk starts at the chosen term and spreads out for λ steps, and gives every term a hitting time: how soon the walk reaches it.",
  },
  {
    title: "Measured against comparison terms",
    body: "The model also walked from about 50 comparison terms spread across the graph, so it knows how soon each term is usually reached. A term reached much sooner from the chosen term than from those gets a high z-score, and the terms above the threshold form the concept.",
  },
  {
    title: "A query expansion with intuitive weights",
    body: "The concept is the chosen term plus the terms that belong with it, ranked and weighted on one scale: the chosen term is 100, and a term at 25 counts a quarter as much. The weights come from the walk alone, with no training and no tuning.",
  },
  {
    title: "A ranked, semantic search",
    body: "Those weights score any raw text directly. Each chunk scores the sum of the weights of the concept terms it contains, so a chunk can rank high without the chosen term, through the terms that mean the same thing.",
  },
];

export function ConceptExplainer() {
  return (
    <section aria-labelledby="explainer-heading" className="mt-16 flex flex-col gap-6">
      <h2 id="explainer-heading" className="text-3xl md:text-4xl">
        What a concept is
      </h2>
      <div className="grid gap-8 lg:grid-cols-[1fr_26rem]">
        <ol className="grid gap-4 sm:grid-cols-2">
          {STEPS.map((step, i) => (
            <li key={step.title} className="rounded-2xl border bg-card p-5">
              <span className="text-gradient font-heading text-4xl leading-none">0{i + 1}</span>
              <h3 className="mt-2 font-sans text-base font-semibold tracking-normal">
                {step.title}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>

        <figure className="flex flex-col gap-4 rounded-3xl border bg-card p-5 shadow-[0_0_60px_var(--glow)]">
          <figcaption className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
            An example, with illustrative weights
          </figcaption>
          <ul className="flex flex-col gap-1.5">
            {EXAMPLE.map((t) => (
              <li
                key={t.term}
                className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2 text-sm"
              >
                <span className="truncate font-mono">{t.term}</span>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="bg-gradient h-full rounded-full"
                    style={{ width: `${t.weight}%` }}
                  />
                </div>
                <span className="tabular text-right font-mono">{formatWeight(t.weight)}</span>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2 border-t pt-4">
            <p className="text-xs text-muted-foreground">Scoring three chunks with it:</p>
            {CHUNKS.map((parts, i) => {
              const terms = parts.flatMap((p) => (typeof p === "string" ? [] : [p.term]));
              const score = terms.reduce((sum, t) => sum + (weightOf.get(t) ?? 0), 0);
              return (
                <div key={i} className="flex items-baseline gap-3 rounded-xl bg-muted/50 p-3">
                  <span className="tabular text-gradient w-14 shrink-0 font-mono text-lg font-semibold">
                    {score > 0 ? score.toFixed(1) : "—"}
                  </span>
                  <p className="text-sm leading-relaxed">
                    {parts.map((p, j) =>
                      typeof p === "string" ? (
                        <span key={j}>{p}</span>
                      ) : (
                        <mark
                          key={j}
                          className="rounded-sm bg-primary/20 px-0.5 text-foreground shadow-[inset_0_-2px_0_var(--primary)]"
                        >
                          {p.term}
                        </mark>
                      ),
                    )}
                  </p>
                </div>
              );
            })}
            <p className="text-xs text-muted-foreground">
              The second chunk never says &ldquo;xylophone&rdquo;, yet still ranks; the third shares
              no term with the concept and isn&rsquo;t a hit. With several concepts, a chunk ranks
              high only if it fits every one.
            </p>
          </div>
          <Link href="/search" className="text-sm font-medium text-primary hover:underline">
            Semantically search data with concepts →
          </Link>
        </figure>
      </div>
    </section>
  );
}
