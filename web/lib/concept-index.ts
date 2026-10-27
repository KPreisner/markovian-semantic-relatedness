// The concepts index's filters, as they live in the page's URL and go to the API.

import type { ConceptIndexCounts, EntryStatus } from "@/lib/api";

export const PAGE_SIZE = 50;

export const TABS = {
  all: { label: "All", statuses: null },
  built: { label: "Built", statuses: ["ready"] },
  building: { label: "Building", statuses: ["queued", "running"] },
  failed: { label: "Failed", statuses: ["failed"] },
} as const satisfies Record<string, { label: string; statuses: readonly EntryStatus[] | null }>;

export type Tab = keyof typeof TABS;

export type IndexFilters = { tab: Tab; term: string; model: string; page: number };

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

export function parseFilters(params: SearchParams): IndexFilters {
  const tab = first(params.tab);
  const page = Number.parseInt(first(params.page), 10);
  return {
    tab: tab in TABS ? (tab as Tab) : "all",
    term: first(params.term),
    model: first(params.model),
    page: Number.isFinite(page) && page > 1 ? page : 1,
  };
}

/** The `GET /concepts` query for these filters. */
export function apiQuery(filters: IndexFilters) {
  return {
    status: TABS[filters.tab].statuses ?? undefined,
    term: filters.term || undefined,
    model: filters.model || undefined,
    limit: PAGE_SIZE,
    offset: (filters.page - 1) * PAGE_SIZE,
  };
}

/** The page's own URL for these filters, leaving defaults out. */
export function indexHref(filters: IndexFilters): string {
  const params = new URLSearchParams();
  if (filters.tab !== "all") params.set("tab", filters.tab);
  if (filters.term) params.set("term", filters.term);
  if (filters.model) params.set("model", filters.model);
  if (filters.page > 1) params.set("page", String(filters.page));
  const query = params.toString();
  return query ? `/concepts?${query}` : "/concepts";
}

export function tabCount(tab: Tab, counts: ConceptIndexCounts): number {
  const statuses = TABS[tab].statuses ?? (["ready", "queued", "running", "failed"] as const);
  return statuses.reduce((sum, s) => sum + counts[s], 0);
}

export function pageCount(filters: IndexFilters, counts: ConceptIndexCounts): number {
  return Math.max(1, Math.ceil(tabCount(filters.tab, counts) / PAGE_SIZE));
}
