import { useSyncExternalStore } from "react";

// Concepts this browser opened recently, for the build page and the search builder. A per-viewer
// convenience in localStorage: it can be empty or unavailable (private windows), and nothing
// depends on it.

export type RecentConcept = {
  concept_id: string;
  model_id: string;
  root: string;
  /** The concept's parameters, to tell concepts of one chosen term apart (missing from entries
   * remembered before they were recorded). */
  params?: Record<string, unknown>;
  opened_at: string;
};

const KEY = "msr:recent-concepts";
const LIMIT = 24;

export function readRecent(storage: Storage | undefined = safeStorage()): RecentConcept[] {
  try {
    const raw = storage?.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isRecent) : [];
  } catch {
    return [];
  }
}

export function rememberConcept(
  concept: Omit<RecentConcept, "opened_at">,
  storage: Storage | undefined = safeStorage(),
  now: Date = new Date(),
): RecentConcept[] {
  return write(
    [
      { ...concept, opened_at: now.toISOString() },
      ...readRecent(storage).filter((c) => c.concept_id !== concept.concept_id),
    ].slice(0, LIMIT),
    storage,
  );
}

/** Drop concepts that no longer exist (the database was reset, or their model deleted). The list
 * lives in this browser, so nothing on the server can clear it. */
export function forgetConcepts(
  ids: readonly string[],
  storage: Storage | undefined = safeStorage(),
): RecentConcept[] {
  return write(
    readRecent(storage).filter((c) => !ids.includes(c.concept_id)),
    storage,
  );
}

function write(list: RecentConcept[], storage: Storage | undefined): RecentConcept[] {
  try {
    storage?.setItem(KEY, JSON.stringify(list));
  } catch {
    // Full or blocked storage: the list just isn't remembered.
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CHANGED));
  return list;
}

let pruned = false;

/** Once per page load, check the remembered concepts still exist and forget the ones that
 * don't, filling in the parameters of entries remembered without them. At most `LIMIT` small
 * requests (`limit=1`). */
export async function pruneMissing(fetcher: typeof fetch = fetch): Promise<string[]> {
  if (pruned) return [];
  pruned = true;
  const missing: string[] = [];
  const params = new Map<string, Record<string, unknown>>();
  await Promise.all(
    readRecent().map(async (c) => {
      try {
        const response = await fetcher(`/api/concepts/${encodeURIComponent(c.concept_id)}?limit=1`);
        if (response.status === 404) missing.push(c.concept_id);
        else if (response.ok && !c.params) {
          const body = (await response.json()) as { params?: Record<string, unknown> };
          if (body.params) params.set(c.concept_id, body.params);
        }
      } catch {
        // Unreachable is not missing.
      }
    }),
  );
  if (missing.length) forgetConcepts(missing);
  if (params.size) {
    write(
      readRecent().map((c) =>
        params.has(c.concept_id) ? { ...c, params: params.get(c.concept_id) } : c,
      ),
      safeStorage(),
    );
  }
  return missing;
}

const CHANGED = "msr:recent-changed";
const NONE: RecentConcept[] = [];
let snapshot: { raw: string | null; list: RecentConcept[] } = { raw: null, list: NONE };

/** The recent concepts, kept current across tabs. Empty on the server and until hydration, so the
 * server's HTML and the first client render agree. */
export function useRecentConcepts(): RecentConcept[] {
  return useSyncExternalStore(subscribe, currentRecent, () => NONE);
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

function currentRecent(): RecentConcept[] {
  let raw: string | null = null;
  try {
    raw = safeStorage()?.getItem(KEY) ?? null;
  } catch {
    raw = null;
  }
  // The same array until the stored value changes, as useSyncExternalStore requires.
  if (raw !== snapshot.raw) snapshot = { raw, list: readRecent() };
  return snapshot.list;
}

function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function isRecent(value: unknown): value is RecentConcept {
  const v = value as RecentConcept;
  return (
    typeof v === "object" &&
    v !== null &&
    typeof v.concept_id === "string" &&
    typeof v.model_id === "string" &&
    typeof v.root === "string" &&
    typeof v.opened_at === "string"
  );
}
