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

/** "degree-mean · λ 100 · z ≥ 6" for a cached concept's parameters. */
export function paramsLabel(params: Record<string, unknown>): string {
  const parts = [String(params.refs ?? ""), `λ ${params.steps}`, `z ≥ ${params.threshold}`];
  if (params.q !== 50) parts.push(`Q ${params.q}`);
  if (params.trim_ratio !== 0.2) parts.push(`R ${params.trim_ratio}`);
  return parts.filter(Boolean).join(" · ");
}
