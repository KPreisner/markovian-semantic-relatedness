"use client";

import { Loader2, Plus, Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useEffectEvent, useLayoutEffect, useState } from "react";

import { TermCombobox } from "@/components/workbench/term-combobox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import type { ConceptStatus, ConceptSummary, Corpus, ModelSummary, SearchStarted } from "@/lib/api";
import { api, ApiRequestError } from "@/lib/client/api";
import { pruneMissing, useRecentConcepts } from "@/lib/client/recent";
import { useJobEvents } from "@/lib/client/use-job-events";
import {
  formatBytes,
  formatCount,
  paramsLabel,
  scoringLabel,
  usesScoringDefaults,
} from "@/lib/format";
import { conceptColor } from "@/lib/highlight";
import { cn } from "@/lib/utils";

/** A concept in the search: ready (has an id), or still being built by a job. */
export type Chip = {
  key: string;
  root: string;
  model_id: string;
  concept_id: string | null;
  job_id: string | null;
  /** The concept's parameters, shown to tell concepts of one chosen term apart. */
  params: Record<string, unknown> | null;
};

const MAX_CONCEPTS = 10; // the API's limit

export function SearchBuilder({
  models,
  corpora,
  initial,
}: {
  models: ModelSummary[];
  corpora: Corpus[];
  initial: Chip[];
}) {
  const router = useRouter();
  const [chips, setChips] = useState<Chip[]>(initial);
  const [modelId, setModelId] = useState(initial[0]?.model_id ?? models[0]?.model_id ?? "");
  const [term, setTerm] = useState("");
  const [adding, setAdding] = useState(false);
  const [corpusId, setCorpusId] = useState(corpora[0]?.corpus_id ?? "");
  const [topK, setTopK] = useState(100);
  const [topN, setTopN] = useState(100);
  const [match, setMatch] = useState<"word" | "substring">("word");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  // A chosen term with concepts already built: which one to add.
  const [choice, setChoice] = useState<{ root: string; concepts: ConceptSummary[] } | null>(null);
  const recent = useRecentConcepts();
  useEffect(() => void pruneMissing(), []);

  // Next keeps this page alive (hidden) after Search navigates away, and Back shows it again with
  // its state. The chips and settings are worth keeping; a request in flight is not.
  useLayoutEffect(
    () => () => {
      setStarting(false);
      setAdding(false);
    },
    [],
  );

  // Every concept of a search comes from one model; the first chip decides it.
  const lockedModel = chips[0]?.model_id;
  const activeModel = lockedModel ?? modelId;
  const building = chips.some((c) => c.concept_id === null);
  const suggestions = recent.filter(
    (r) => r.model_id === activeModel && !chips.some((c) => c.concept_id === r.concept_id),
  );

  function add(chip: Chip) {
    setChips((cs) =>
      cs.some((c) => c.concept_id && c.concept_id === chip.concept_id)
        ? cs
        : [...cs, chip].slice(0, MAX_CONCEPTS),
    );
  }

  /** Add a concept by its chosen term. With no concept built yet, build one with the default
   * parameters; with only that one, add it; with others, ask which. */
  async function addTerm(root: string) {
    if (!root || !activeModel) return;
    setAdding(true);
    setError(null);
    setChoice(null);
    try {
      const built = await api<ConceptSummary[]>(
        `/models/${encodeURIComponent(activeModel)}/concepts?root=${encodeURIComponent(root)}`,
      );
      if (built.length === 0) {
        await buildDefault(root);
      } else if (built.length === 1 && usesScoringDefaults(built[0].params)) {
        addBuilt(root, built[0]);
      } else {
        setChoice({ root, concepts: built });
      }
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "Couldn't add that concept.");
    } finally {
      setAdding(false);
    }
  }

  function addBuilt(root: string, concept: ConceptSummary) {
    add({
      key: concept.concept_id,
      root,
      model_id: activeModel,
      concept_id: concept.concept_id,
      job_id: null,
      params: concept.params,
    });
    setTerm("");
    setChoice(null);
  }

  /** Request the term's concept with the default parameters: cached, or built by a new job. */
  async function buildDefault(root: string) {
    const status = await api<ConceptStatus>(`/models/${encodeURIComponent(activeModel)}/concepts`, {
      method: "POST",
      json: { root },
    });
    add({
      key: `${root}:${status.concept_id ?? status.job_id}`,
      root,
      model_id: activeModel,
      concept_id: status.concept_id,
      job_id: status.job_id,
      params: status.job?.params ?? null,
    });
    setTerm("");
    setChoice(null);
  }

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const started = await api<SearchStarted>("/searches", {
        method: "POST",
        json: {
          concept_ids: chips.map((c) => c.concept_id),
          corpus: corpusId,
          top_k_terms: topK,
          top_n: topN,
          match,
        },
      });
      router.push(`/searches/${started.search_id}`);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "The search couldn't start.");
      setStarting(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
      <div className="flex flex-col gap-8">
        <section aria-labelledby="concepts-heading" className="flex flex-col gap-3">
          <h2
            id="concepts-heading"
            className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase"
          >
            1 · Concepts
          </h2>
          {!lockedModel && models.length > 1 && (
            <Select value={modelId} onValueChange={setModelId}>
              <SelectTrigger className="w-64 font-mono">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m.model_id} value={m.model_id} className="font-mono">
                    {m.model_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <ul className="flex min-h-12 flex-wrap gap-2 rounded-2xl border border-dashed p-3">
            {chips.length === 0 && (
              <li className="self-center text-sm text-muted-foreground">
                Add one or more concepts.
              </li>
            )}
            {chips.map((chip, i) => (
              <ConceptChip
                key={chip.key}
                chip={chip}
                index={i}
                onReady={(conceptId) =>
                  setChips((cs) =>
                    cs.map((c) => (c.key === chip.key ? { ...c, concept_id: conceptId } : c)),
                  )
                }
                onFailed={() => setChips((cs) => cs.filter((c) => c.key !== chip.key))}
                onRemove={() => setChips((cs) => cs.filter((c) => c.key !== chip.key))}
              />
            ))}
          </ul>
          <div className="flex gap-2">
            <div className="flex-1 rounded-xl border bg-card px-1">
              <TermCombobox
                key={activeModel}
                modelId={activeModel}
                value={term}
                onValueChange={setTerm}
                onPick={addTerm}
                placeholder="Add a concept by its chosen term"
              />
            </div>
            <Button
              variant="outline"
              className="h-12"
              onClick={() => addTerm(term)}
              disabled={!term || adding || chips.length >= MAX_CONCEPTS}
            >
              {adding ? <Loader2 className="animate-spin" /> : <Plus />} Add
            </Button>
          </div>
          {choice && (
            <div className="flex flex-col gap-2 rounded-xl border bg-card p-3 text-sm">
              <p>
                <span className="font-mono">{choice.root}</span> already has{" "}
                {choice.concepts.length === 1 ? "a concept" : `${choice.concepts.length} concepts`}.
                Which one?
              </p>
              <div className="flex flex-wrap gap-2">
                {choice.concepts.map((c) => (
                  <button
                    key={c.concept_id}
                    type="button"
                    onClick={() => addBuilt(choice.root, c)}
                    className="rounded-full border px-3 py-1 font-mono text-xs hover:border-primary"
                  >
                    {paramsLabel(c.params)}
                  </button>
                ))}
                {!choice.concepts.some((c) => usesScoringDefaults(c.params)) && (
                  <button
                    type="button"
                    onClick={() =>
                      buildDefault(choice.root).catch((e) =>
                        setError(
                          e instanceof ApiRequestError ? e.message : "Couldn't add that concept.",
                        ),
                      )
                    }
                    className="rounded-full border border-dashed px-3 py-1 text-xs hover:border-primary"
                  >
                    Build one with the default parameters
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setChoice(null)}
                  className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {chips.length > 1 && (
            <p className="text-sm text-muted-foreground">
              With several concepts, a chunk&apos;s score is the geometric mean of each
              concept&apos;s score, so a chunk ranks high only if it&apos;s relevant to every
              concept.
            </p>
          )}
          {suggestions.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Recent:</span>
              {suggestions.slice(0, 8).map((r) => (
                <button
                  key={r.concept_id}
                  type="button"
                  onClick={() =>
                    add({
                      key: r.concept_id,
                      root: r.root,
                      model_id: r.model_id,
                      concept_id: r.concept_id,
                      job_id: null,
                      params: r.params ?? null,
                    })
                  }
                  className="rounded-full border px-3 py-1 font-mono hover:border-primary"
                >
                  + {r.root}
                  {r.params && (
                    <span className="text-xs text-muted-foreground">
                      {" "}
                      · {scoringLabel(r.params)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </section>

        <section aria-labelledby="corpus-heading" className="flex flex-col gap-3">
          <h2
            id="corpus-heading"
            className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase"
          >
            2 · Search Corpus
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {corpora.map((c) => (
              <button
                key={c.corpus_id}
                type="button"
                onClick={() => setCorpusId(c.corpus_id)}
                aria-pressed={c.corpus_id === corpusId}
                className={cn(
                  "rounded-2xl border bg-card p-4 text-left transition-all hover:border-primary/40",
                  c.corpus_id === corpusId &&
                    "border-primary/70 shadow-[0_0_0_1px_var(--primary),0_0_40px_var(--glow)]",
                )}
              >
                <p className="font-mono font-semibold">{c.corpus_id}</p>
                {c.description && (
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{c.description}</p>
                )}
                <p className="tabular mt-3 font-mono text-xs text-muted-foreground">
                  {formatCount(c.file_count)} file{c.file_count === 1 ? "" : "s"} ·{" "}
                  {formatBytes(c.byte_count)} · {c.formats.join(", ")}
                </p>
              </button>
            ))}
            {corpora.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No corpora yet: prepare one with{" "}
                <code className="font-mono">task build:corpus</code>.
              </p>
            )}
          </div>
        </section>
      </div>

      <aside className="flex flex-col gap-6 rounded-3xl border bg-card p-5 lg:sticky lg:top-20 lg:self-start">
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <Label>Terms per concept</Label>
            <span className="tabular font-mono text-sm">{topK}</span>
          </div>
          <Slider
            min={10}
            max={1000}
            step={10}
            value={[topK]}
            onValueChange={([v]) => setTopK(v)}
            aria-label="Terms per concept"
          />
          <p className="text-xs text-muted-foreground">
            The top-ranked terms of each concept that are matched.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="top-n">Results to keep</Label>
          <Input
            id="top-n"
            type="number"
            min={1}
            max={1000}
            value={topN}
            onChange={(e) =>
              !Number.isNaN(e.target.valueAsNumber) &&
              setTopN(Math.min(1000, Math.max(1, e.target.valueAsNumber)))
            }
            className="tabular font-mono"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label id="match-label">Match</Label>
          <div
            role="radiogroup"
            aria-labelledby="match-label"
            className="grid grid-cols-2 gap-1 rounded-lg border bg-muted/40 p-1"
          >
            {(
              [
                ["word", "Whole words"],
                ["substring", "Inside words"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={match === value}
                onClick={() => setMatch(value)}
                className={cn(
                  "rounded-md px-2 py-1 text-sm transition-colors",
                  match === value
                    ? "bg-card font-medium shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {match === "word"
              ? "“cat” finds “cat’s” but not “category”. Chinese, Japanese, Thai, and other text without spaces is matched anywhere."
              : "“cat” also finds “category” and “scat”: more hits, more noise."}
          </p>
        </div>
        {error && (
          <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <Button
          size="lg"
          onClick={start}
          disabled={chips.length === 0 || building || !corpusId || starting}
          className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
        >
          {starting ? <Loader2 className="animate-spin" /> : <Search />}
          {building ? "Waiting for concepts…" : "Search"}
        </Button>
      </aside>
    </div>
  );
}

function ConceptChip({
  chip,
  index,
  onReady,
  onFailed,
  onRemove,
}: {
  chip: Chip;
  index: number;
  onReady: (conceptId: string) => void;
  onFailed: () => void;
  onRemove: () => void;
}) {
  const stream = useJobEvents(chip.concept_id ? null : chip.job_id);
  const finished = useEffectEvent((resultId: string | null, failed: boolean) => {
    if (resultId) onReady(resultId);
    if (failed) onFailed();
  });
  useEffect(() => {
    finished(stream.result?.result_id ?? null, stream.error !== null);
  }, [stream.result, stream.error]);

  const color = conceptColor(index);
  const pct = stream.progress
    ? Math.round((stream.progress.step / Math.max(1, stream.progress.total)) * 100)
    : 0;
  return (
    <li
      className="relative flex items-center gap-2 overflow-hidden rounded-full border bg-card py-1 pr-1 pl-3 font-mono text-sm"
      style={{ borderColor: color }}
    >
      <span className="size-2.5 rounded-full" style={{ background: color }} />
      {chip.root}
      {chip.params && (
        <span className="text-xs text-muted-foreground">{scoringLabel(chip.params)}</span>
      )}
      {!chip.concept_id && (
        <span className="tabular flex items-center gap-1 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" /> {stream.progress ? `${pct}%` : "queued"}
        </span>
      )}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${chip.root}`}
        className="rounded-full p-1 hover:bg-muted"
      >
        <X className="size-3.5" />
      </button>
      {!chip.concept_id && (
        <span
          className="absolute bottom-0 left-0 h-0.5 transition-[width]"
          style={{ width: `${pct}%`, background: color }}
        />
      )}
    </li>
  );
}
