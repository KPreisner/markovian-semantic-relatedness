"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/jobs/job-progress";
import { IndexShell } from "@/components/site/index-shell";
import { Badge } from "@/components/ui/badge";
import type { ConceptEntry, ConceptIndex, ModelSummary } from "@/lib/api";
import { formatCount, formatDate, formatSeconds, paramsLabel, percent } from "@/lib/format";
import { CONCEPT_INDEX, type IndexFilters } from "@/lib/index-filters";

export function ConceptIndexView({
  index,
  models,
  filters,
}: {
  index: ConceptIndex;
  models: ModelSummary[];
  filters: IndexFilters;
}) {
  return (
    <IndexShell
      spec={CONCEPT_INDEX}
      filters={filters}
      counts={index.counts}
      active={index.entries.some((e) => e.status === "queued" || e.status === "running")}
      models={models.map((m) => m.model_id)}
      empty={
        <>
          No concepts yet. <Link href="/concepts/new">Build the first one →</Link>
        </>
      }
    >
      {index.entries.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {index.entries.map((entry) => (
            <EntryCard key={entry.concept_id ?? entry.job?.job_id} entry={entry} />
          ))}
        </ul>
      ) : null}
    </IndexShell>
  );
}

function EntryCard({ entry }: { entry: ConceptEntry }) {
  const job = entry.job;
  const href = entry.concept_id ? `/concepts/${entry.concept_id}` : `/jobs/${job?.job_id}`;
  const progress = job?.progress as { phase?: string; step?: number; total?: number } | null;
  return (
    <li>
      <Link
        href={href}
        className="group grid gap-3 rounded-2xl border bg-card p-4 transition-colors hover:border-primary/40 md:grid-cols-[minmax(12rem,18rem)_1fr_auto] md:items-center"
      >
        <div className="flex min-w-0 flex-col gap-1">
          <span className="truncate font-mono text-lg font-semibold group-hover:text-primary">
            {entry.root.term}
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            {entry.model_id}
            <br />
            {paramsLabel(entry.params)}
          </span>
        </div>

        <div className="min-w-0 text-sm">
          {entry.status === "ready" && (
            <p className="truncate text-muted-foreground">
              <span className="tabular font-mono text-foreground">
                {formatCount(entry.term_count ?? 0)}
              </span>{" "}
              terms
              {entry.top_terms.length > 0 && (
                <>
                  {" · "}
                  <span className="font-mono">{entry.top_terms.join(", ")}</span>…
                </>
              )}
            </p>
          )}
          {entry.status === "running" && (
            <div className="flex items-center gap-3">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="bg-gradient h-full rounded-full transition-[width]"
                  style={{ width: `${percent(progress?.step ?? 0, progress?.total ?? 0)}%` }}
                />
              </div>
              <span className="tabular shrink-0 font-mono text-xs text-muted-foreground">
                {progress?.phase ?? "starting"}
                {progress?.total ? ` · ${progress.step ?? 0} / ${progress.total}` : ""}
              </span>
            </div>
          )}
          {entry.status === "queued" && (
            <p className="text-muted-foreground">Waiting for a worker.</p>
          )}
          {entry.status === "failed" && job?.error && (
            <p className="truncate text-destructive">
              <span className="font-mono">{job.error.code}</span>
              {job.error.message && (
                <span className="text-muted-foreground"> · {job.error.message}</span>
              )}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          {entry.status === "ready" ? (
            <StatusBadge status="succeeded" label="built" />
          ) : (
            <StatusBadge status={entry.status} />
          )}
          {job && job.compute_seconds !== null && (
            <Badge variant="outline" className="tabular font-mono">
              {formatSeconds(job.compute_seconds)}
            </Badge>
          )}
          {job && job.attempts > 1 && (
            <Badge variant="outline" className="tabular font-mono">
              {job.attempts} attempts
            </Badge>
          )}
          {job && job.warnings.length > 0 && (
            <Badge variant="outline" className="border-warning/50 font-mono text-warning">
              {job.warnings.length} warning{job.warnings.length === 1 ? "" : "s"}
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
