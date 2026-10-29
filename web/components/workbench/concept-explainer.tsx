import Link from "next/link";

import { Button } from "@/components/ui/button";

const STEPS = [
  {
    title: "A walk from the chosen term",
    body: "The model is a graph: each term is linked to the terms it shares chunks with, more strongly the more often they do. A random walk starts at the chosen term and spreads out for λ steps, and gives every term a hitting time: how soon the walk reaches it.",
  },
  {
    title: "Measured against comparison terms",
    body: "The model also walked from a set of comparison terms spread across the graph (50 unless it was built with another number), so it knows how soon each term is usually reached. A term reached much sooner from the chosen term than from those gets a high z-score, and the terms above the threshold form the concept: a query expansion, ranked and weighted on one scale, where the chosen term is 100 and a term at 25 counts a quarter as much.",
  },
  {
    title: "A tool for discovery",
    body: "On its own, a concept answers “what is related to this term?” in the text the model was built from, and can turn up the needle in the haystack, a rare term tied closely to the chosen term that a keyword search would never think to ask for.",
  },
  {
    title: "A ranked, semantic search",
    body: "Those weights score any raw text directly. Each chunk scores the sum of the weights of the concept terms it contains, so a chunk can rank high without the chosen term, through the terms that mean the same thing.",
    action: { href: "/search", label: "Semantically search data with concepts →" },
  },
];

export function ConceptExplainer() {
  return (
    <section aria-labelledby="explainer-heading" className="mt-16 flex flex-col gap-6">
      <h2 id="explainer-heading" className="text-3xl md:text-4xl">
        What a concept is and what to do with it
      </h2>
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex flex-col rounded-2xl border bg-card p-5">
            <span className="text-gradient font-heading text-4xl leading-none">0{i + 1}</span>
            <h3 className="mt-2 font-sans text-base font-semibold tracking-normal">{step.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
            {step.action && (
              <div className="mt-auto pt-4">
                <Button
                  asChild
                  className="bg-gradient h-auto w-full py-2 whitespace-normal text-primary-foreground shadow-[0_0_32px_var(--glow)]"
                >
                  <Link href={step.action.href}>{step.action.label}</Link>
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
