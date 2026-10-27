// Whether a search found anything clearly about its concepts.
//
// A concept's long tail of weak terms ("said", "year") matches almost any chunk, so a corpus that
// never mentions the subject still returns a full page of hits. A hit is a strong match for a
// concept when its chunk has the concept's chosen term, or at least two of its terms in separate
// places: "Cuarón" inside "Alfonso Cuarón" is one mention, not two.

type Concept = { root: string; terms: readonly string[] };
type Span = { term: string; start: number; end: number };
type Hit = { matches: readonly Span[] };

export function strongFor(concept: Concept, hit: Hit): boolean {
  const own = new Set(concept.terms);
  const spans = hit.matches.filter((m) => own.has(m.term));
  if (spans.some((m) => m.term === concept.root)) return true;
  const nested = (m: Span) =>
    spans.some(
      (o) => o !== m && o.start <= m.start && o.end >= m.end && o.end - o.start > m.end - m.start,
    );
  return new Set(spans.filter((m) => !nested(m)).map((m) => m.term)).size >= 2;
}

/** The concepts (by position) that no hit matches strongly. */
export function weakConcepts(concepts: readonly Concept[], hits: readonly Hit[]): number[] {
  return concepts.flatMap((c, i) => (hits.some((h) => strongFor(c, h)) ? [] : [i]));
}
