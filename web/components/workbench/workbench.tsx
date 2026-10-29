"use client";

import { ChevronDown, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";

import { TermCombobox } from "@/components/workbench/term-combobox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ConceptRequest, ConceptStatus, ConceptSummary, ModelSummary } from "@/lib/api";
import { api, ApiRequestError } from "@/lib/client/api";
import { formatCount, paramsLabel, SCORING_DEFAULTS } from "@/lib/format";
import { cn } from "@/lib/utils";

// The scoring fields the Advanced panel edits; one is sent only when changed.
const DEFAULTS = {
  threshold: SCORING_DEFAULTS.threshold,
  trim_ratio: SCORING_DEFAULTS.trim_ratio,
  stored_terms: SCORING_DEFAULTS.stored_terms,
};
type Advanced = typeof DEFAULTS;

export function Workbench({ models }: { models: ModelSummary[] }) {
  const router = useRouter();
  const [modelId, setModelId] = useState(models[0]?.model_id ?? "");
  const model = models.find((m) => m.model_id === modelId);
  const strategies = useMemo(() => Object.keys(model?.reference_steps ?? {}), [model]);
  const [refsChoice, setRefs] = useState<string>("");
  const refs = strategies.includes(refsChoice) ? refsChoice : (strategies[0] ?? "");
  const [term, setTerm] = useState("");
  const [advanced, setAdvanced] = useState<Advanced>(DEFAULTS);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<{ key: string; concepts: ConceptSummary[] } | null>(null);

  // Back from the concept or job page shows this page again with its state (Next keeps it
  // alive, hidden); the form is worth keeping, a request in flight is not.
  useLayoutEffect(() => () => setBuilding(false), []);

  // Concepts already cached for this root (any parameters): reachable without building. The
  // result is kept with its model and term, so a stale answer never shows for another term.
  const lookup = `${modelId}\u0000${term}`;
  const cached = found?.key === lookup ? found.concepts : null;
  useEffect(() => {
    if (!modelId || !term) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<ConceptSummary[]>(
        `/models/${encodeURIComponent(modelId)}/concepts?root=${encodeURIComponent(term)}`,
        { signal: controller.signal },
      )
        .then((concepts) => setFound({ key: `${modelId}\u0000${term}`, concepts }))
        .catch(() => setFound(null));
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [modelId, term]);

  async function build() {
    if (!model || !term) return;
    setBuilding(true);
    setError(null);
    const request: ConceptRequest = { root: term };
    if (refs && refs !== strategies[0]) request.refs = refs;
    for (const key of Object.keys(DEFAULTS) as (keyof Advanced)[]) {
      if (advanced[key] !== DEFAULTS[key]) request[key] = advanced[key];
    }
    try {
      const status = await api<ConceptStatus>(
        `/models/${encodeURIComponent(model.model_id)}/concepts`,
        {
          method: "POST",
          json: request,
        },
      );
      router.push(
        status.status === "ready" ? `/concepts/${status.concept_id}` : `/jobs/${status.job_id}`,
      );
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "The request failed.");
      setBuilding(false);
    }
  }

  if (models.length === 0) {
    return (
      <p className="rounded-2xl border bg-card p-6 text-muted-foreground">
        No models are registered yet. Build one with{" "}
        <code className="font-mono">task build:model</code>.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="model-heading" className="flex flex-col gap-3">
        <h2
          id="model-heading"
          className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase"
        >
          1 · Model
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {models.map((m) => (
            <button
              key={m.model_id}
              type="button"
              onClick={() => setModelId(m.model_id)}
              aria-pressed={m.model_id === modelId}
              className={cn(
                "rounded-2xl border bg-card p-4 text-left transition-all hover:border-primary/40",
                m.model_id === modelId &&
                  "border-primary/70 shadow-[0_0_0_1px_var(--primary),0_0_40px_var(--glow)]",
              )}
            >
              <p className="font-semibold">{m.model_name || m.model_id}</p>
              {m.description && (
                <p className="mt-1 text-sm text-muted-foreground">{m.description}</p>
              )}
              <p className="tabular mt-3 font-mono text-xs text-muted-foreground">
                {formatCount(m.term_count)} terms
                {m.parts_used !== null &&
                  m.parts_total !== null &&
                  ` · ${m.parts_used}/${m.parts_total} parts`}
              </p>
            </button>
          ))}
        </div>
      </section>

      <section aria-labelledby="term-heading" className="flex flex-col gap-3">
        <h2
          id="term-heading"
          className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase"
        >
          2 · Chosen term
        </h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="flex-1 rounded-xl border bg-card px-1">
            <TermCombobox
              key={modelId}
              modelId={modelId}
              value={term}
              onValueChange={setTerm}
              autoFocus
            />
          </div>
          <Button
            size="lg"
            onClick={build}
            disabled={!term || building}
            className="bg-gradient h-12 px-6 text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            {building ? <Loader2 className="animate-spin" /> : <Sparkles />}
            Build concept
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Terms are case-sensitive, exactly as the model saw them:{" "}
          <span className="font-mono">Trumpet</span> and <span className="font-mono">trumpet</span>{" "}
          are different terms.
        </p>
        {error && (
          <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {cached && cached.length > 0 && (
          <div className="rounded-xl border border-success/30 bg-success/5 p-3 text-sm">
            <p className="font-medium">
              Already built for <span className="font-mono">{term}</span>: open one instantly.
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {cached.map((c) => (
                <li key={c.concept_id}>
                  <Link href={`/concepts/${c.concept_id}`}>
                    <Badge variant="outline" className="font-mono hover:border-primary">
                      {paramsLabel(c.params)}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" />
            Advanced parameters
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-3 flex flex-col gap-5 rounded-2xl border bg-card p-4">
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-medium">Set when the model was built</legend>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label>Reference strategy</Label>
                  <Select value={refs} onValueChange={setRefs}>
                    <SelectTrigger className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {strategies.map((s) => (
                        <SelectItem key={s} value={s} className="font-mono">
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    How the comparison terms were picked. Only the strategies built for this model
                    are offered.
                  </p>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Walk steps λ</Label>
                  <Input
                    value={model?.reference_steps[refs] ?? ""}
                    readOnly
                    disabled
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    The chosen term is walked as many steps as the comparison terms were, so their
                    distances compare.
                  </p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                The comparison terms and their walks are part of the model, so their number
                isn&apos;t a setting here.
              </p>
            </fieldset>
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-medium">
                Scoring{" "}
                <span className="font-normal text-muted-foreground">
                  · quick to change once a term has been walked: its walk is reused, only the
                  scoring is redone
                </span>
              </legend>
              <div className="grid gap-4 sm:grid-cols-3">
                <NumberField
                  label="z threshold"
                  hint="How much closer than usual a term must be to the chosen term to join, in standard deviations of its distances to the comparison terms. Lower keeps more terms."
                  value={advanced.threshold}
                  step={0.5}
                  onChange={(v) => setAdvanced({ ...advanced, threshold: v })}
                />
                <NumberField
                  label="Trim ratio R"
                  hint="Share of each term's comparison-term distances ignored as outliers (the furthest from typical) when working out its usual distance."
                  value={advanced.trim_ratio}
                  step={0.05}
                  min={0}
                  max={0.95}
                  onChange={(v) => setAdvanced({ ...advanced, trim_ratio: v })}
                />
                <NumberField
                  label="Stored terms"
                  hint="Where the ranked list is cut. Searches use each concept's top terms anyway."
                  value={advanced.stored_terms}
                  step={100}
                  min={1}
                  onChange={(v) => setAdvanced({ ...advanced, stored_terms: v })}
                />
              </div>
            </fieldset>
          </CollapsibleContent>
        </Collapsible>
      </section>
    </div>
  );
}

function NumberField(props: {
  label: string;
  hint: string;
  value: number;
  step: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{props.label}</Label>
      <Input
        type="number"
        className="tabular font-mono"
        value={props.value}
        step={props.step}
        min={props.min}
        max={props.max}
        onChange={(e) => {
          const v = e.target.valueAsNumber;
          if (!Number.isNaN(v)) props.onChange(v);
        }}
      />
      <p className="text-xs text-muted-foreground">{props.hint}</p>
    </div>
  );
}
