import { formatWeight } from "@/lib/format";
import { cn } from "@/lib/utils";

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

/** How a search scores text with a concept: a worked example, with made-up weights. */
export function ConceptExample() {
  return (
    <section aria-labelledby="example-heading" className="grid gap-8 lg:grid-cols-[1fr_26rem]">
      <div className="flex flex-col gap-4">
        <h2 id="example-heading" className="text-3xl md:text-4xl">
          How a search ranks text
        </h2>
        <p className="max-w-xl text-muted-foreground">
          A concept is its chosen term plus the terms that belong with it, each weighted on one
          scale: the chosen term is 100, and a term at 25 counts a quarter as much. Each chunk
          scores the sum of the weights of the concept terms it contains, so a chunk can rank high
          without the chosen term, through the terms that mean the same thing.
        </p>
      </div>

      <ExampleFigure />
    </section>
  );
}

/** The example on its own: the concept's weights and three chunks scored with them. */
export function ExampleFigure({ className }: { className?: string }) {
  return (
    <figure
      className={cn(
        "flex flex-col gap-4 rounded-3xl border bg-card p-5 shadow-[0_0_60px_var(--glow)]",
        className,
      )}
    >
      <figcaption className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
        An example, with illustrative weights
      </figcaption>
      <ul className="flex flex-col gap-1.5">
        {EXAMPLE.map((t) => (
          <li key={t.term} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2 text-sm">
            <span className="truncate font-mono">{t.term}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="bg-gradient h-full rounded-full" style={{ width: `${t.weight}%` }} />
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
          The second chunk never says &ldquo;xylophone&rdquo;, yet still ranks; the third shares no
          term with the concept and isn&rsquo;t a hit. With several concepts, a chunk ranks high
          only if it fits every one.
        </p>
      </div>
    </figure>
  );
}
