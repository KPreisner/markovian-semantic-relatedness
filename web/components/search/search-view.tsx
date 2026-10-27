"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { JobProgress, liveStatus, StatusBadge } from "@/components/jobs/job-progress";
import { Badge } from "@/components/ui/badge";
import type { Search, SearchHit } from "@/lib/api";
import { useJobEvents } from "@/lib/client/use-job-events";
import { formatCount, formatScore, formatSeconds } from "@/lib/format";
import { conceptColor, segments } from "@/lib/highlight";
import { weakConcepts } from "@/lib/strength";

export type SearchConcept = { concept_id: string; root: string; terms: string[] };

export function SearchView({ search, concepts }: { search: Search; concepts: SearchConcept[] }) {
  const router = useRouter();
  const job = search.job;
  const running = job !== null && (job.status === "queued" || job.status === "running");
  const stream = useJobEvents(running ? job.job_id : null);

  // When the scan finishes, reload the page's data from the server: the hits are in now.
  useEffect(() => {
    if (stream.result) router.refresh();
  }, [stream.result, router]);

  // term → the concepts (by position) it belongs to, for coloring matches.
  const owners = useMemo(() => {
    const map = new Map<string, number[]>();
    concepts.forEach((c, i) => c.terms.forEach((t) => map.set(t, [...(map.get(t) ?? []), i])));
    return map;
  }, [concepts]);
  const weak = useMemo(() => weakConcepts(concepts, search.hits), [concepts, search.hits]);
  const maxScores = concepts.map((_, i) =>
    Math.max(...search.hits.map((h) => h.concept_scores[i] ?? 0), Number.EPSILON),
  );

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center gap-2">
        {concepts.map((c, i) => (
          <Link
            key={c.concept_id}
            href={`/concepts/${c.concept_id}`}
            className="flex items-center gap-2 rounded-full border bg-card px-3 py-1 font-mono text-sm hover:bg-muted"
            style={{ borderColor: conceptColor(i) }}
          >
            <span className="size-2.5 rounded-full" style={{ background: conceptColor(i) }} />
            {c.root}
          </Link>
        ))}
        <span className="text-muted-foreground">in</span>
        <Badge variant="outline" className="font-mono">
          {search.corpus_id}
        </Badge>
        <Badge variant="outline" className="font-mono">
          top {String(search.params.top_k_terms)} terms · {String(search.params.top_n)} hits
        </Badge>
        {search.params.match === "substring" && (
          <Badge variant="outline" className="font-mono">
            inside words
          </Badge>
        )}
        {job && !running && <StatusBadge status={job.status} />}
        {job && !running && (
          <span className="tabular font-mono text-sm text-muted-foreground">
            scanned in {formatSeconds(job.compute_seconds)}
            {job.attempts > 1 && ` · ${job.attempts} attempts`}
          </span>
        )}
      </div>

      {job && (running || job.status === "failed") && (
        <JobProgress
          job={job}
          progress={stream.progress}
          status={liveStatus(job, stream.progress, stream.result !== null, stream.error)}
          error={
            stream.error ??
            (job.error
              ? { type: "error", code: job.error.code, message: job.error.message ?? "" }
              : null)
          }
        />
      )}

      {!running && job?.status === "succeeded" && search.hits.length === 0 && (
        <p className="rounded-3xl border bg-card p-8 text-center text-muted-foreground">
          No chunk in <span className="font-mono">{search.corpus_id}</span> matched these concepts.
        </p>
      )}

      {search.hits.length > 0 && weak.length > 0 && (
        <div className="rounded-2xl border border-warning/40 bg-warning/10 px-5 py-4 text-sm">
          <p className="font-medium">
            No strong matches for {listRoots(weak.map((i) => concepts[i].root))}.
          </p>
          <p className="mt-1 text-muted-foreground">
            {weak.length === 1 ? "No hit" : "For each of them, no hit"} has the chosen term or two
            of the concept&rsquo;s terms, so these hits share only loosely related words.{" "}
            <span className="font-mono">{search.corpus_id}</span> may not cover{" "}
            {weak.length === 1 ? "it" : "them"}.
          </p>
        </div>
      )}

      {search.hits.length > 0 && (
        <ol className="flex flex-col gap-4">
          {search.hits.map((hit) => (
            <HitCard
              key={hit.rank}
              hit={hit}
              concepts={concepts}
              owners={owners}
              maxScores={maxScores}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

function listRoots(roots: string[]): string {
  const quoted = roots.map((r) => `“${r}”`);
  return quoted.length < 3
    ? quoted.join(" or ")
    : `${quoted.slice(0, -1).join(", ")}, or ${quoted.at(-1)}`;
}

function HitCard({
  hit,
  concepts,
  owners,
  maxScores,
}: {
  hit: SearchHit;
  concepts: SearchConcept[];
  owners: Map<string, number[]>;
  maxScores: number[];
}) {
  const parts = segments(hit.chunk_text, hit.matches);
  const matched = [...new Set(hit.matches.map((m) => m.term))];
  return (
    <li className="group grid gap-4 rounded-3xl border bg-card p-5 transition-colors hover:border-primary/40 md:grid-cols-[4.5rem_1fr]">
      <div className="flex items-baseline gap-3 md:flex-col md:gap-1">
        <span className="tabular font-mono text-xs text-muted-foreground">#{hit.rank}</span>
        <span className="tabular text-gradient font-mono text-2xl font-semibold">
          {formatScore(hit.score)}
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <p className="leading-relaxed">
          {parts.map((part, i) => {
            if (part.terms.length === 0) return <span key={i}>{part.text}</span>;
            const indices = [...new Set(part.terms.flatMap((t) => owners.get(t) ?? []))];
            const colors = indices.length ? indices.map(conceptColor) : ["var(--primary)"];
            return (
              <mark
                key={i}
                title={part.terms.join(", ")}
                className="rounded-sm px-0.5 text-foreground"
                style={{
                  background:
                    colors.length === 1
                      ? `color-mix(in oklch, ${colors[0]} 28%, transparent)`
                      : `linear-gradient(90deg, ${colors.map((c) => `color-mix(in oklch, ${c} 30%, transparent)`).join(", ")})`,
                  boxShadow: `inset 0 -2px 0 ${colors[0]}`,
                }}
              >
                {part.text}
              </mark>
            );
          })}
        </p>
        {concepts.length > 1 && (
          <div className="grid gap-1.5 sm:grid-cols-2">
            {concepts.map((c, i) => (
              <div key={c.concept_id} className="flex items-center gap-2 text-xs">
                <span className="w-24 truncate font-mono text-muted-foreground">{c.root}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${((hit.concept_scores[i] ?? 0) / maxScores[i]) * 100}%`,
                      background: conceptColor(i),
                    }}
                  />
                </div>
                <span className="tabular w-12 text-right font-mono">
                  {formatScore(hit.concept_scores[i] ?? 0)}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs text-muted-foreground">
          <span className="truncate" title={hit.doc_id}>
            {hit.doc_id}
          </span>
          <span>
            {hit.file_path} · chunk {hit.chunk_index}
          </span>
          <span>
            {formatCount(matched.length)} term{matched.length === 1 ? "" : "s"}:{" "}
            {matched.slice(0, 8).join(", ")}
            {matched.length > 8 && "…"}
          </span>
        </div>
      </div>
    </li>
  );
}
