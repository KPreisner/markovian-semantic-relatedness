// The filters of an index page (/concepts, /searches), as they live in the page's URL and go to
// the API.

export const PAGE_SIZE = 50;

type TabSpec = { label: string; statuses: readonly string[] | null };

export type IndexFilters = {
  tab: string;
  term: string;
  model: string;
  corpus: string;
  page: number;
};

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

/** One index page's tabs and URL; every helper is pure. The first tab is the default. */
export function indexSpec(path: string, tabs: Record<string, TabSpec>) {
  const defaultTab = Object.keys(tabs)[0];

  function parse(params: SearchParams): IndexFilters {
    const tab = first(params.tab);
    const page = Number.parseInt(first(params.page), 10);
    return {
      tab: tab in tabs ? tab : defaultTab,
      term: first(params.term),
      model: first(params.model),
      corpus: first(params.corpus),
      page: Number.isFinite(page) && page > 1 ? page : 1,
    };
  }

  /** The API query (`GET <path>`) for these filters. */
  function apiQuery(filters: IndexFilters) {
    return {
      status: tabs[filters.tab]?.statuses ?? undefined,
      term: filters.term || undefined,
      model: filters.model || undefined,
      corpus: filters.corpus || undefined,
      limit: PAGE_SIZE,
      offset: (filters.page - 1) * PAGE_SIZE,
    };
  }

  /** The page's own URL for these filters, leaving defaults out. */
  function href(filters: IndexFilters): string {
    const params = new URLSearchParams();
    if (filters.tab !== defaultTab) params.set("tab", filters.tab);
    if (filters.term) params.set("term", filters.term);
    if (filters.model) params.set("model", filters.model);
    if (filters.corpus) params.set("corpus", filters.corpus);
    if (filters.page > 1) params.set("page", String(filters.page));
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  }

  function tabCount(tab: string, counts: Record<string, number>): number {
    const statuses = tabs[tab]?.statuses ?? Object.keys(counts);
    return statuses.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
  }

  function pageCount(filters: IndexFilters, counts: Record<string, number>): number {
    return Math.max(1, Math.ceil(tabCount(filters.tab, counts) / PAGE_SIZE));
  }

  return { path, tabs, parse, apiQuery, href, tabCount, pageCount };
}

export type IndexSpec = ReturnType<typeof indexSpec>;

export const CONCEPT_INDEX = indexSpec("/concepts", {
  all: { label: "All", statuses: null },
  built: { label: "Built", statuses: ["ready"] },
  building: { label: "Building", statuses: ["queued", "running"] },
  failed: { label: "Failed", statuses: ["failed"] },
});

export const SEARCH_INDEX = indexSpec("/searches", {
  all: { label: "All", statuses: null },
  done: { label: "Done", statuses: ["succeeded"] },
  running: { label: "Running", statuses: ["queued", "running"] },
  failed: { label: "Failed", statuses: ["failed"] },
});
