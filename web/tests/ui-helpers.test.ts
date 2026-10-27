// The UI's pure helpers: highlight segmentation, match strength, the concepts index's filters,
// formatting, and the recent-concepts store.
import { describe, expect, it } from "vitest";

import { readRecent, rememberConcept } from "@/lib/client/recent";
import { apiQuery, indexHref, pageCount, parseFilters, tabCount } from "@/lib/concept-index";
import {
  formatBytes,
  formatSeconds,
  formatWeight,
  paramsLabel,
  percent,
  scoringLabel,
  usesScoringDefaults,
} from "@/lib/format";
import { segments } from "@/lib/highlight";
import { strongFor, weakConcepts } from "@/lib/strength";

describe("segments", () => {
  it("splits text at matches and keeps unmatched text plain", () => {
    expect(segments("the fat cat", [{ term: "cat", start: 8, end: 11 }])).toEqual([
      { text: "the fat ", terms: [] },
      { text: "cat", terms: ["cat"] },
    ]);
  });

  it("marks overlapping matches with every term that covers them", () => {
    const text = "Hermione Granger";
    const parts = segments(text, [
      { term: "Hermione", start: 0, end: 8 },
      { term: "Hermione Granger", start: 0, end: 16 },
      { term: "Granger", start: 9, end: 16 },
    ]);
    expect(parts).toEqual([
      { text: "Hermione", terms: ["Hermione", "Hermione Granger"] },
      { text: " ", terms: ["Hermione Granger"] },
      { text: "Granger", terms: ["Hermione Granger", "Granger"] },
    ]);
    expect(parts.map((p) => p.text).join("")).toBe(text);
  });

  it("highlights a match inside a word, as a substring search finds", () => {
    expect(segments("category", [{ term: "cat", start: 0, end: 3 }])).toEqual([
      { text: "cat", terms: ["cat"] },
      { text: "egory", terms: [] },
    ]);
  });

  it("clamps spans that run past the text", () => {
    expect(segments("dog", [{ term: "dogs", start: 0, end: 4 }])).toEqual([
      { text: "dog", terms: ["dogs"] },
    ]);
  });
});

describe("match strength", () => {
  const hermione = {
    root: "Hermione Granger",
    terms: ["Hermione Granger", "Ron", "Hogwarts", "sorted", "Alfonso Cuarón", "Cuarón"],
  };
  // Each term at its own place in the chunk, unless a span is given.
  const hit = (...terms: (string | [string, number, number])[]) => ({
    matches: terms.map((t, i) =>
      typeof t === "string"
        ? { term: t, start: i * 100, end: i * 100 + t.length }
        : { term: t[0], start: t[1], end: t[2] },
    ),
  });

  it("calls a hit strong with the chosen term, or two of the concept's terms", () => {
    expect(strongFor(hermione, hit("Hermione Granger"))).toBe(true);
    expect(strongFor(hermione, hit("Ron", "Hogwarts"))).toBe(true);
    expect(strongFor(hermione, hit("sorted"))).toBe(false);
    // The same term found twice is still one term.
    expect(strongFor(hermione, hit("sorted", "sorted"))).toBe(false);
  });

  it("counts a term inside a longer matched term as the same mention", () => {
    const cuaron = hit(["Alfonso Cuarón", 0, 14], ["Cuarón", 8, 14]);
    expect(strongFor(hermione, cuaron)).toBe(false);
    expect(strongFor(hermione, hit(["Alfonso Cuarón", 0, 14], ["Cuarón", 40, 46]))).toBe(true);
  });

  it("counts only the concept's own terms", () => {
    expect(strongFor(hermione, hit("sorted", "tariff"))).toBe(false);
  });

  it("names each concept no hit matches strongly", () => {
    const tariff = { root: "tariff", terms: ["tariff", "trade", "duties"] };
    expect(weakConcepts([hermione, tariff], [hit("sorted", "tariff"), hit("trade")])).toEqual([0]);
    expect(weakConcepts([hermione], [])).toEqual([0]);
    expect(weakConcepts([tariff], [hit("trade", "duties")])).toEqual([]);
  });
});

describe("concepts index filters", () => {
  const counts = { ready: 120, queued: 1, running: 2, failed: 3 };

  it("reads the URL, falling back to defaults for anything unknown", () => {
    expect(parseFilters({})).toEqual({ tab: "all", term: "", model: "", page: 1 });
    expect(parseFilters({ tab: "failed", term: " cat ", model: "m", page: "3" })).toEqual({
      tab: "failed",
      term: "cat",
      model: "m",
      page: 3,
    });
    expect(parseFilters({ tab: "bogus", page: "-2" })).toMatchObject({ tab: "all", page: 1 });
    expect(parseFilters({ tab: ["built", "failed"], page: "x" })).toMatchObject({
      tab: "built",
      page: 1,
    });
  });

  it("asks the API for the tab's statuses and the page's rows", () => {
    const filters = { tab: "building", term: "", model: "", page: 2 } as const;
    expect(apiQuery(filters)).toEqual({
      status: ["queued", "running"],
      term: undefined,
      model: undefined,
      limit: 50,
      offset: 50,
    });
    expect(apiQuery({ ...filters, tab: "all" }).status).toBeUndefined();
  });

  it("writes the URL back without defaults", () => {
    expect(indexHref({ tab: "all", term: "", model: "", page: 1 })).toBe("/concepts");
    expect(indexHref({ tab: "failed", term: "Ron W", model: "", page: 2 })).toBe(
      "/concepts?tab=failed&term=Ron+W&page=2",
    );
  });

  it("counts each tab and its pages", () => {
    expect(tabCount("all", counts)).toBe(126);
    expect(tabCount("building", counts)).toBe(3);
    expect(pageCount({ tab: "built", term: "", model: "", page: 1 }, counts)).toBe(3);
    expect(pageCount({ tab: "failed", term: "", model: "", page: 1 }, counts)).toBe(1);
    expect(
      pageCount({ tab: "failed", term: "", model: "", page: 1 }, { ...counts, failed: 0 }),
    ).toBe(1);
  });
});

describe("formatting", () => {
  it("formats weights from the root's 100 down to tiny values", () => {
    expect([100, 70.62, 1.6, 0.034, 0.00012].map(formatWeight)).toEqual([
      "100.0",
      "70.6",
      "1.60",
      "0.034",
      "1.2e-4",
    ]);
  });

  it("formats bytes, durations, and percentages", () => {
    expect([512, 2_016_659, 3_500_000_000].map(formatBytes)).toEqual(["512 B", "2.0 MB", "3.5 GB"]);
    expect([0.238, 7.5, 16.68, 125, null].map(formatSeconds)).toEqual([
      "238 ms",
      "7.5 s",
      "17 s",
      "2 min 5 s",
      "—",
    ]);
    expect([percent(50, 100), percent(5, 0), percent(150, 100)]).toEqual([50, 0, 100]);
  });

  const defaults = {
    refs: "degree-mean",
    steps: 1000,
    threshold: 6,
    q: 50,
    trim_ratio: 0.2,
    stored_terms: 5000,
    root_weight: 100,
  };

  it("labels a concept's parameters, mentioning settings other than z only when changed", () => {
    expect(paramsLabel(defaults)).toBe("degree-mean · λ 1000 · z ≥ 6");
    expect(paramsLabel({ ...defaults, steps: 20, threshold: 4, q: 30, trim_ratio: 0.1 })).toBe(
      "degree-mean · λ 20 · z ≥ 4 · R 0.1 · Q 30",
    );
  });

  it("tells two concepts of one term apart by their scoring settings", () => {
    expect(scoringLabel(defaults)).toBe("z ≥ 6");
    expect(scoringLabel({ ...defaults, threshold: 4, trim_ratio: 0.1 })).toBe("z ≥ 4 · R 0.1");
    expect(scoringLabel({ ...defaults, stored_terms: 1000, root_weight: 1 })).toBe(
      "z ≥ 6 · 1,000 stored · root 1",
    );
    expect(usesScoringDefaults(defaults)).toBe(true);
    expect(usesScoringDefaults({ ...defaults, trim_ratio: 0.1 })).toBe(false);
  });
});

class MemoryStorage implements Storage {
  private items = new Map<string, string>();
  get length() {
    return this.items.size;
  }
  clear() {
    this.items.clear();
  }
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  key(index: number) {
    return [...this.items.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
}

describe("recent concepts", () => {
  it("keeps the latest first, without duplicates", () => {
    const storage = new MemoryStorage();
    rememberConcept({ concept_id: "a", model_id: "m", root: "cat" }, storage);
    rememberConcept({ concept_id: "b", model_id: "m", root: "dog" }, storage);
    rememberConcept({ concept_id: "a", model_id: "m", root: "cat" }, storage);
    expect(readRecent(storage).map((c) => c.concept_id)).toEqual(["a", "b"]);
  });

  it("survives garbage and missing storage", () => {
    const storage = new MemoryStorage();
    storage.setItem("msr:recent-concepts", "{not json");
    expect(readRecent(storage)).toEqual([]);
    storage.setItem(
      "msr:recent-concepts",
      JSON.stringify([
        { concept_id: 1 },
        { concept_id: "x", model_id: "m", root: "r", opened_at: "t" },
      ]),
    );
    expect(readRecent(storage).map((c) => c.concept_id)).toEqual(["x"]);
    expect(readRecent(undefined)).toEqual([]);
  });
});

describe("forgetting recent concepts", () => {
  it("drops the given ids and can clear everything", async () => {
    const { clearRecent, forgetConcepts } = await import("@/lib/client/recent");
    const storage = new MemoryStorage();
    for (const id of ["a", "b", "c"])
      rememberConcept({ concept_id: id, model_id: "m", root: id }, storage);
    expect(forgetConcepts(["b"], storage).map((c) => c.concept_id)).toEqual(["c", "a"]);
    expect(clearRecent(storage)).toEqual([]);
    expect(readRecent(storage)).toEqual([]);
  });
});
