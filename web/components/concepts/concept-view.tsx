"use client";

import { Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/jobs/job-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Concept } from "@/lib/api";
import { api } from "@/lib/client/api";
import { rememberConcept } from "@/lib/client/recent";
import { formatCount, formatDate, formatSeconds, formatWeight, paramsLabel } from "@/lib/format";

const PAGES = [200, 1000, 5000];

export function ConceptView({ concept: initial }: { concept: Concept }) {
  const [concept, setConcept] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    rememberConcept({
      concept_id: initial.concept_id,
      model_id: initial.model_id,
      root: initial.root.term,
    });
  }, [initial]);

  const loaded = concept.terms.length;
  const next = PAGES.find((n) => n > loaded && loaded < concept.term_count);
  async function more() {
    if (!next) return;
    setLoading(true);
    try {
      setConcept(await api<Concept>(`/concepts/${concept.concept_id}?limit=${next}`));
    } finally {
      setLoading(false);
    }
  }

  // Bars are relative to the strongest term after the root: the root is 100 by construction and
  // would flatten everything else.
  const maxOther = useMemo(
    () => Math.max(...concept.terms.slice(1).map((t) => t.weight), Number.EPSILON),
    [concept],
  );
  const rows = filter ? concept.terms.filter((t) => t.term.includes(filter)) : concept.terms;
  const job = concept.job;

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="terms stored" value={formatCount(concept.term_count)} />
          <Stat label="built in" value={formatSeconds(job?.compute_seconds)} />
          <Stat label="attempts" value={job ? String(job.attempts) : "—"} />
          <Stat label="built" value={formatDate(concept.created_at)} />
        </dl>
        <div className="flex flex-wrap items-start gap-2 md:flex-col md:items-end">
          <Button
            asChild
            className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            <Link href={`/search?concepts=${concept.concept_id}`}>
              <Search /> Search with this concept
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/workbench">
              <Sparkles /> Build another
            </Link>
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline" className="font-mono">
          {paramsLabel(concept.params)}
        </Badge>
        {job && <StatusBadge status={job.status} />}
        {job?.warnings.map((w) => (
          <Badge key={w} variant="outline" className="border-warning/50 text-warning">
            {w}
          </Badge>
        ))}
      </div>

      <section aria-label="Ranked terms" className="overflow-hidden rounded-3xl border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
          <p className="text-sm text-muted-foreground">
            Ranked by co-occurrence with the root, then by z. Weights are scaled so the root is 100.
          </p>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter loaded terms"
            className="ml-auto h-8 w-48 font-mono"
            aria-label="Filter terms"
          />
        </div>
        <div className="max-h-[70vh] overflow-auto">
          <table className="tabular w-full text-sm">
            <thead className="sticky top-0 z-10 bg-card/95 font-mono text-xs tracking-wider text-muted-foreground uppercase backdrop-blur">
              <tr>
                <th className="px-4 py-2 text-right font-medium">Rank</th>
                <th className="px-4 py-2 text-left font-medium">Term</th>
                <th className="w-[38%] px-4 py-2 text-left font-medium">Weight</th>
                <th className="px-4 py-2 text-right font-medium">Co-occur</th>
                <th className="px-4 py-2 text-right font-medium">Count</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.map((t) => {
                const root = t.rank === 1;
                const width = root ? 100 : Math.max(1, (t.weight / maxOther) * 100);
                return (
                  <tr key={t.term_idx} className="border-t border-border/60 hover:bg-muted/50">
                    <td className="px-4 py-1.5 text-right text-muted-foreground">{t.rank}</td>
                    <td
                      className={root ? "text-gradient px-4 py-1.5 font-semibold" : "px-4 py-1.5"}
                    >
                      {t.term}
                    </td>
                    <td className="px-4 py-1.5">
                      <div className="flex items-center gap-3">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className="bg-gradient h-full rounded-full"
                            style={{ width: `${width}%`, opacity: root ? 1 : 0.85 }}
                          />
                        </div>
                        <span className="w-16 text-right">{formatWeight(t.weight)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-1.5 text-right">{formatCount(t.cooccur)}</td>
                    <td className="px-4 py-1.5 text-right text-muted-foreground">
                      {formatCount(t.term_count)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
          <span>
            Showing {formatCount(rows.length)} of {formatCount(concept.term_count)}
            {filter && ` (filtered from ${formatCount(loaded)} loaded)`}
          </span>
          {next && (
            <Button variant="outline" size="sm" onClick={more} disabled={loading}>
              {loading
                ? "Loading…"
                : `Load ${next === concept.term_count || next >= concept.term_count ? "all" : formatCount(next)}`}
            </Button>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-card px-4 py-3">
      <dt className="font-mono text-xs tracking-widest text-muted-foreground uppercase">{label}</dt>
      <dd className="tabular mt-1 font-mono text-xl font-semibold">{value}</dd>
    </div>
  );
}
