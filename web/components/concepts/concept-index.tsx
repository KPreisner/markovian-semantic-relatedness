"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/jobs/job-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ConceptEntry, ConceptIndex, ModelSummary } from "@/lib/api";
import {
  type IndexFilters,
  indexHref,
  PAGE_SIZE,
  pageCount,
  TABS,
  type Tab,
  tabCount,
} from "@/lib/concept-index";
import { formatCount, formatDate, formatSeconds, paramsLabel, percent } from "@/lib/format";
import { cn } from "@/lib/utils";

const REFRESH_MS = 3000;

export function ConceptIndexView({
  index,
  models,
  filters,
}: {
  index: ConceptIndex;
  models: ModelSummary[];
  filters: IndexFilters;
}) {
  const router = useRouter();
  const [term, setTerm] = useState(filters.term);
  const go = (next: Partial<IndexFilters>) =>
    router.replace(indexHref({ ...filters, page: 1, ...next }), { scroll: false });

  // Typing filters by root after a pause; the URL keeps the filter, so it survives a reload.
  useEffect(() => {
    if (term.trim() === filters.term) return;
    const timer = setTimeout(
      () =>
        router.replace(indexHref({ ...filters, term: term.trim(), page: 1 }), { scroll: false }),
      300,
    );
    return () => clearTimeout(timer);
  }, [term, filters, router]);

  // While anything on the page is building, reload its rows from the server every few seconds.
  const active = index.entries.some((e) => e.status === "queued" || e.status === "running");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, router]);

  const pages = pageCount(filters, index.counts);
  const total = tabCount(filters.tab, index.counts);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div role="tablist" className="flex flex-wrap gap-1 rounded-xl border bg-muted/40 p-1">
          {(Object.keys(TABS) as Tab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={filters.tab === tab}
              onClick={() => go({ tab })}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors",
                filters.tab === tab
                  ? "bg-card font-medium shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {TABS[tab].label}
              <span className="tabular font-mono text-xs text-muted-foreground">
                {formatCount(tabCount(tab, index.counts))}
              </span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {models.length > 1 && (
            <select
              aria-label="Model"
              value={filters.model}
              onChange={(e) => go({ model: e.target.value })}
              className="h-9 rounded-lg border bg-card px-2 font-mono text-sm"
            >
              <option value="">every model</option>
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.model_id}
                </option>
              ))}
            </select>
          )}
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="Filter by chosen term"
              placeholder="Filter by chosen term"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              className="w-64 pl-8"
            />
          </div>
        </div>
      </div>

      {index.entries.length === 0 ? (
        <p className="rounded-3xl border bg-card p-8 text-center text-muted-foreground">
          {filters.term || filters.tab !== "all" || filters.model ? (
            "No concepts match these filters."
          ) : (
            <>
              No concepts yet. <Link href="/concepts/new">Build the first one →</Link>
            </>
          )}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {index.entries.map((entry) => (
            <EntryCard key={entry.concept_id ?? entry.job?.job_id} entry={entry} />
          ))}
        </ul>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span className="tabular font-mono">
            {formatCount((filters.page - 1) * PAGE_SIZE + 1)}–
            {formatCount(Math.min(filters.page * PAGE_SIZE, total))} of {formatCount(total)}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page <= 1}
              onClick={() => go({ page: filters.page - 1 })}
            >
              ← Newer
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page >= pages}
              onClick={() => go({ page: filters.page + 1 })}
            >
              Older →
            </Button>
          </div>
        </div>
      )}
    </div>
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
