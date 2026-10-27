// Matched terms in a hit's chunk, as text segments for highlighting.
//
// Matches can overlap ("Hermione", "Hermione Granger"), and every match counts in the score, so
// a segment carries every term that covers it; the UI colors it by the concepts those terms
// belong to.

export type Span = { term: string; start: number; end: number };
export type Segment = { text: string; terms: string[] };

export function segments(text: string, matches: readonly Span[]): Segment[] {
  const cuts = new Set<number>([0, text.length]);
  for (const m of matches) {
    cuts.add(Math.max(0, Math.min(text.length, m.start)));
    cuts.add(Math.max(0, Math.min(text.length, m.end)));
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [start, end] = [points[i], points[i + 1]];
    if (start === end) continue;
    const terms = [
      ...new Set(matches.filter((m) => m.start <= start && m.end >= end).map((m) => m.term)),
    ];
    const last = out.at(-1);
    if (last && sameTerms(last.terms, terms)) last.text += text.slice(start, end);
    else out.push({ text: text.slice(start, end), terms });
  }
  return out;
}

function sameTerms(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((t) => b.includes(t));
}

/** Concept index → its CSS color variable (globals.css defines ten). */
export function conceptColor(index: number): string {
  return `var(--concept-${(index % 10) + 1})`;
}
