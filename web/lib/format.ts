// Display formatting shared by the screens.

const integer = new Intl.NumberFormat("en-US");

// UTC, so the server's render and the browser's agree (a local date differs near midnight).
const date = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

export function formatDate(iso: string): string {
  return date.format(new Date(iso));
}

export function formatCount(n: number): string {
  return integer.format(n);
}

/** Concept weights span 100 (the root) down to tiny values; keep a few significant digits. */
export function formatWeight(weight: number): string {
  if (weight >= 100) return weight.toFixed(1);
  if (weight >= 1) return weight.toPrecision(3);
  if (weight >= 0.001) return weight.toPrecision(2);
  return weight.toExponential(1);
}

export function formatScore(score: number): string {
  return score >= 10 ? score.toFixed(1) : score.toPrecision(3);
}

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds % 60)} s`;
}

export function percent(step: number, total: number): number {
  return total > 0 ? Math.min(100, Math.max(0, (step / total) * 100)) : 0;
}

/** The scoring settings' defaults (msr.concept.build.ConceptParams). The workbench sends a field
 * only when it differs, so identical requests share a cache key. */
export const SCORING_DEFAULTS = {
  threshold: 6,
  trim_ratio: 0.2,
  stored_terms: 5000,
  root_weight: 100,
};

/** The scoring settings that tell concepts of one chosen term apart: the z threshold always,
 * the rest only when changed. "z ≥ 4 · R 0.1". */
export function scoringLabel(params: Record<string, unknown>): string {
  const parts = [`z ≥ ${params.threshold ?? SCORING_DEFAULTS.threshold}`];
  if (params.trim_ratio !== undefined && params.trim_ratio !== SCORING_DEFAULTS.trim_ratio) {
    parts.push(`R ${params.trim_ratio}`);
  }
  if (params.stored_terms !== undefined && params.stored_terms !== SCORING_DEFAULTS.stored_terms) {
    parts.push(`${formatCount(Number(params.stored_terms))} stored`);
  }
  if (params.root_weight !== undefined && params.root_weight !== SCORING_DEFAULTS.root_weight) {
    parts.push(`root ${params.root_weight}`);
  }
  return parts.join(" · ");
}

/** Whether a concept was built with every scoring default (what a plain request builds). */
export function usesScoringDefaults(params: Record<string, unknown>): boolean {
  return (Object.keys(SCORING_DEFAULTS) as (keyof typeof SCORING_DEFAULTS)[]).every(
    (key) => params[key] === undefined || params[key] === SCORING_DEFAULTS[key],
  );
}

/** "degree-mean · λ 100 · z ≥ 6" for a cached concept's parameters, with any other changed
 * setting after it. */
export function paramsLabel(params: Record<string, unknown>): string {
  const parts = [String(params.refs ?? ""), `λ ${params.steps}`, scoringLabel(params)];
  if (params.q !== undefined && params.q !== 50) parts.push(`Q ${params.q}`);
  return parts.filter(Boolean).join(" · ");
}
