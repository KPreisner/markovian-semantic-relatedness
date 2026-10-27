"use client";

import { AlertTriangle, CheckCircle2, Loader2, Timer } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { ErrorEvent, Job, ProgressEvent } from "@/lib/api";
import { formatBytes, formatCount, formatSeconds, percent } from "@/lib/format";
import { cn } from "@/lib/utils";

export type LiveStatus = Job["status"];

/** A job's state for display: the row it started from, updated by its live events. */
export function liveStatus(
  job: Job,
  progress: ProgressEvent | null,
  done: boolean,
  error: ErrorEvent | null,
): LiveStatus {
  if (error) return "failed";
  if (done) return "succeeded";
  if (progress) return "running";
  return job.status;
}

const LABEL: Record<LiveStatus, string> = {
  queued: "Waiting for a worker",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
};

export function StatusBadge({ status, label }: { status: LiveStatus; label?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5 font-mono",
        status === "succeeded" && "border-success/50 text-success",
        status === "failed" && "border-destructive/50 text-destructive",
        (status === "running" || status === "queued") && "border-primary/50 text-primary",
      )}
    >
      {status === "succeeded" ? (
        <CheckCircle2 className="size-3.5" />
      ) : status === "failed" ? (
        <AlertTriangle className="size-3.5" />
      ) : (
        <span className="animate-pulse-soft size-2 rounded-full bg-current" />
      )}
      {label ?? status}
    </Badge>
  );
}

/** Seconds since `since`, ticking while `running`. */
function useElapsed(since: string | null, running: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [running]);
  return since ? Math.max(0, (now - Date.parse(since)) / 1000) : null;
}

export function JobProgress({
  job,
  progress,
  status,
  error,
}: {
  job: Job;
  progress: ProgressEvent | null;
  status: LiveStatus;
  error: ErrorEvent | null;
}) {
  const active = status === "queued" || status === "running";
  const elapsed = useElapsed(job.started_at ?? job.created_at, active);
  const step = progress?.step ?? 0;
  const total = progress?.total ?? 0;
  const pct = status === "succeeded" ? 100 : percent(step, total);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-3xl border bg-card p-6 md:p-8",
        active && "shadow-[0_0_0_1px_var(--primary),0_0_60px_var(--glow)]",
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={status} />
        <p className="text-lg font-medium">{LABEL[status]}</p>
        {active && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        <p
          className="tabular ml-auto flex items-center gap-1.5 font-mono text-sm text-muted-foreground"
          // A running clock: the server's render and the browser's differ by design.
          suppressHydrationWarning
        >
          <Timer className="size-4" />
          {status === "succeeded" || status === "failed"
            ? formatSeconds(job.compute_seconds)
            : formatSeconds(elapsed)}
        </p>
      </div>

      <div
        className="mt-6 h-3 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full bg-gradient transition-[width] duration-500",
            active && "animate-shimmer",
          )}
          style={{
            width: `${status === "queued" && !progress ? 4 : pct}%`,
            backgroundImage: active
              ? "linear-gradient(100deg, var(--primary), var(--accent), var(--primary))"
              : undefined,
          }}
        />
      </div>

      <div className="tabular mt-3 flex flex-wrap justify-between gap-2 font-mono text-sm text-muted-foreground">
        <span>
          {progress ? (
            <>
              {progress.phase} · {formatCount(step)} / {formatCount(total)}
              {progress.message && <span className="ml-2 text-foreground">{progress.message}</span>}
            </>
          ) : status === "queued" ? (
            "queued"
          ) : null}
        </span>
        {progress?.bytes_scanned !== null && progress?.bytes_scanned !== undefined && (
          <span>
            {formatBytes(progress.bytes_scanned)} scanned · {formatCount(progress.hits ?? 0)}{" "}
            matching documents
          </span>
        )}
      </div>

      {error && (
        <p className="mt-6 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span className="font-mono">{error.code}</span>: {error.message}
        </p>
      )}

      {(job.attempts > 1 || job.warnings.length > 0) && (
        <div className="mt-6 rounded-xl border border-warning/40 bg-warning/5 px-4 py-3 text-sm">
          <p className="font-medium">Attempt {job.attempts} of this job</p>
          <ul className="mt-1 list-disc pl-5 text-muted-foreground">
            {job.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
