"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type IndexFilters, type IndexSpec, PAGE_SIZE } from "@/lib/index-filters";
import { formatCount } from "@/lib/format";
import { cn } from "@/lib/utils";

const REFRESH_MS = 3000;

/** An index page's frame: status tabs with counts, model and corpus pickers (when there's a
 * choice), a filter by chosen term, the rows, and paging. The filters live in the URL. While a
 * row is active, the page reloads its rows from the server every few seconds. */
export function IndexShell({
  spec,
  filters,
  counts,
  active,
  models = [],
  corpora = [],
  empty,
  children,
}: {
  spec: IndexSpec;
  filters: IndexFilters;
  counts: Record<string, number>;
  /** Some row is queued or running. */
  active: boolean;
  models?: string[];
  corpora?: string[];
  /** What to show without any rows and without filters. */
  empty: ReactNode;
  /** The rows; null without any. */
  children: ReactNode | null;
}) {
  const router = useRouter();
  const [term, setTerm] = useState(filters.term);
  const go = (next: Partial<IndexFilters>) =>
    router.replace(spec.href({ ...filters, page: 1, ...next }), { scroll: false });

  // Typing filters by chosen term after a pause.
  useEffect(() => {
    if (term.trim() === filters.term) return;
    const timer = setTimeout(
      () =>
        router.replace(spec.href({ ...filters, term: term.trim(), page: 1 }), { scroll: false }),
      300,
    );
    return () => clearTimeout(timer);
  }, [term, filters, router, spec]);

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, router]);

  const pages = spec.pageCount(filters, counts);
  const total = spec.tabCount(filters.tab, counts);
  const filtered =
    filters.term || filters.model || filters.corpus || filters.tab !== Object.keys(spec.tabs)[0];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div role="tablist" className="flex flex-wrap gap-1 rounded-xl border bg-muted/40 p-1">
          {Object.entries(spec.tabs).map(([tab, { label }]) => (
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
              {label}
              <span className="tabular font-mono text-xs text-muted-foreground">
                {formatCount(spec.tabCount(tab, counts))}
              </span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Picker
            label="Model"
            every="every model"
            options={models}
            value={filters.model}
            onChange={(model) => go({ model })}
          />
          <Picker
            label="Corpus"
            every="every corpus"
            options={corpora}
            value={filters.corpus}
            onChange={(corpus) => go({ corpus })}
          />
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

      {children ?? (
        <p className="rounded-3xl border bg-card p-8 text-center text-muted-foreground">
          {filtered ? "Nothing matches these filters." : empty}
        </p>
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

/** A select over ids, shown only when there's more than one to choose from. */
function Picker(props: {
  label: string;
  every: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  if (props.options.length < 2) return null;
  return (
    <select
      aria-label={props.label}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      className="h-9 rounded-lg border bg-card px-2 font-mono text-sm"
    >
      <option value="">{props.every}</option>
      {props.options.map((id) => (
        <option key={id} value={id}>
          {id}
        </option>
      ))}
    </select>
  );
}
