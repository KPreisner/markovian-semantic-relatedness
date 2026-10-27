"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/jobs/job-progress";
import { IndexShell } from "@/components/site/index-shell";
import { Badge } from "@/components/ui/badge";
import type { SearchEntry, SearchIndex } from "@/lib/api";
import {
  formatBytes,
  formatCount,
  formatDate,
  formatSeconds,
  percent,
  scoringLabel,
} from "@/lib/format";
import { conceptColor } from "@/lib/highlight";
import { type IndexFilters, SEARCH_INDEX } from "@/lib/index-filters";

export function SearchIndexView({
  index,
  models,
  corpora,
  filters,
}: {
  index: SearchIndex;
  models: string[];
  corpora: string[];
  filters: IndexFilters;
}) {
  return (
    <IndexShell
      spec={SEARCH_INDEX}
      filters={filters}
      counts={index.counts}
      active={index.entries.some((e) => e.status === "queued" || e.status === "running")}
      models={models}
      corpora={corpora}
      empty={
        <>
          No searches yet. <Link href="/search">Run the first one →</Link>
        </>
      }
    >
      {index.entries.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {index.entries.map((entry) => (
            <EntryCard key={entry.search_id} entry={entry} />
          ))}
        </ul>
      ) : null}
    </IndexShell>
  );
}

function EntryCard({ entry }: { entry: SearchEntry }) {
  const { job, params } = entry;
  const progress = job.progress as {
    step?: number;
    total?: number;
    bytes_scanned?: number | null;
    hits?: number | null;
  } | null;
  return (
    <li>
      <Link
        href={`/searches/${entry.search_id}`}
        className="group grid gap-3 rounded-2xl border bg-card p-4 transition-colors hover:border-primary/40 md:grid-cols-[1fr_auto] md:items-center"
      >
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {entry.concepts.map((c, i) => (
              <span
                key={c.concept_id}
                className="flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-sm"
                style={{ borderColor: conceptColor(i) }}
              >
                <span className="size-2 rounded-full" style={{ background: conceptColor(i) }} />
                {c.root ?? <span className="text-muted-foreground italic">deleted concept</span>}
                {c.params && (
                  <span className="text-xs text-muted-foreground">{scoringLabel(c.params)}</span>
                )}
              </span>
            ))}
            <span className="text-sm text-muted-foreground">in</span>
            <span className="font-mono text-sm">{entry.corpus_id}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted-foreground">
            <span>{entry.model_id}</span>
            <span>top {String(params.top_k_terms ?? 100)} terms</span>
            <span>{params.match === "substring" ? "inside words" : "whole words"}</span>
            {entry.status === "succeeded" && (
              <span className="text-foreground">
                {formatCount(entry.hit_count)} result{entry.hit_count === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {entry.status === "running" && (
            <div className="flex items-center gap-3">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="bg-gradient h-full rounded-full transition-[width]"
                  style={{ width: `${percent(progress?.step ?? 0, progress?.total ?? 0)}%` }}
                />
              </div>
              <span className="tabular shrink-0 font-mono text-xs text-muted-foreground">
                {progress?.bytes_scanned ? formatBytes(progress.bytes_scanned) : "starting"}
                {progress?.hits ? ` · ${formatCount(progress.hits)} matching` : ""}
              </span>
            </div>
          )}
          {entry.status === "queued" && (
            <p className="text-sm text-muted-foreground">Waiting for a worker.</p>
          )}
          {entry.status === "failed" && job.error && (
            <p className="truncate text-sm text-destructive">
              <span className="font-mono">{job.error.code}</span>
              {job.error.message && (
                <span className="text-muted-foreground"> · {job.error.message}</span>
              )}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          {entry.status === "succeeded" ? (
            <StatusBadge status="succeeded" label="done" />
          ) : (
            <StatusBadge status={entry.status} />
          )}
          {job.compute_seconds !== null && (
            <Badge variant="outline" className="tabular font-mono">
              {formatSeconds(job.compute_seconds)}
            </Badge>
          )}
          {job.attempts > 1 && (
            <Badge variant="outline" className="tabular font-mono">
              {job.attempts} attempts
            </Badge>
          )}
          <span className="tabular font-mono text-xs text-muted-foreground">
            {formatDate(entry.created_at)}
          </span>
        </div>
      </Link>
    </li>
  );
}
