import { useSyncExternalStore } from "react";

// Concepts this browser opened recently, for the workbench and the search builder. A per-viewer
// convenience in localStorage: it can be empty or unavailable (private windows), and nothing
// depends on it.

export type RecentConcept = {
  concept_id: string;
  model_id: string;
  root: string;
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
  const next = [
    { ...concept, opened_at: now.toISOString() },
    ...readRecent(storage).filter((c) => c.concept_id !== concept.concept_id),
  ].slice(0, LIMIT);
  try {
    storage?.setItem(KEY, JSON.stringify(next));
  } catch {
    // Full or blocked storage: the list just isn't remembered.
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CHANGED));
  return next;
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
