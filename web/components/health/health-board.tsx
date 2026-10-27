"use client";

import { type ReactNode, useEffect, useState } from "react";

import type { Check, Health } from "@/lib/api";
import { formatCount, formatSeconds } from "@/lib/format";
import { cn } from "@/lib/utils";

const REFRESH_MS = 5000;

export function HealthBoard({ initial }: { initial: Health | null }) {
  const [health, setHealth] = useState(initial);
  const [checkedAt, setCheckedAt] = useState(() => new Date());
  const [unreachable, setUnreachable] = useState(initial === null);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        // A 503 still carries the report; only a missing body means the API is unreachable.
        const response = await fetch("/api/health", { cache: "no-store" });
        const body = (await response.json()) as Health | { error: unknown };
        if ("status" in body) {
          setHealth(body);
          setUnreachable(false);
        } else setUnreachable(true);
      } catch {
        setUnreachable(true);
      }
      setCheckedAt(new Date());
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  if (!health) {
    return (
      <Banner
        tone="down"
        title="The API is unreachable"
        detail="The web server couldn't get a health report."
      />
    );
  }
  const tone = unreachable ? "down" : health.status;
  return (
    <div className="flex flex-col gap-6">
      <Banner
        tone={tone}
        title={
          unreachable
            ? "The API stopped answering"
            : {
                ok: "Everything is running",
                degraded: "Degraded: no worker is running",
                down: "Down: a dependency is unreachable",
              }[health.status]
        }
        detail={
          // A clock: the server's render and the browser's differ by design.
          <span suppressHydrationWarning>
            Checked {checkedAt.toLocaleTimeString()} · refreshes every {REFRESH_MS / 1000} s
          </span>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          title="API"
          status="ok"
          metric={health.api.version}
          detail={`${health.api.instance} · up ${formatSeconds(health.api.uptime_seconds)}`}
        />
        <CheckTile title="Postgres" check={health.postgres} />
        <CheckTile title="Redis" check={health.redis} />
        <CheckTile title="RabbitMQ" check={health.broker} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-3xl border bg-card p-5">
          <h2 className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase">
            Workers
          </h2>
          <p className="tabular mt-2 font-mono text-4xl font-semibold">
            {health.workers.count ?? "?"}
          </p>
          <ul className="mt-3 flex flex-col gap-1 font-mono text-sm">
            {health.workers.nodes.map((node) => (
              <li key={node} className="flex items-center gap-2">
                <span className="animate-pulse-soft size-2 rounded-full bg-success" />
                {node}
              </li>
            ))}
            {health.workers.status === "none" && (
              <li className="text-warning">No worker answered: jobs will queue.</li>
            )}
            {health.workers.status === "unknown" && (
              <li className="text-muted-foreground">Unknown while the broker is down.</li>
            )}
          </ul>
        </section>
        <section className="rounded-3xl border bg-card p-5">
          <h2 className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase">
            Queues
          </h2>
          <table className="tabular mt-3 w-full font-mono text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="text-left font-normal">queue</th>
                <th className="text-right font-normal">waiting</th>
                <th className="text-right font-normal">consumers</th>
              </tr>
            </thead>
            <tbody>
              {health.broker.queues.map((q) => (
                <tr key={q.name} className="border-t border-border/60">
                  <td className="py-1.5">{q.name}</td>
                  <td className="py-1.5 text-right">{q.messages ?? "—"}</td>
                  <td className={cn("py-1.5 text-right", q.consumers === 0 && "text-warning")}>
                    {q.consumers ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="rounded-3xl border bg-card p-5">
          <h2 className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase">
            Active jobs
          </h2>
          {health.jobs ? (
            <dl className="tabular mt-3 grid grid-cols-2 gap-3 font-mono">
              <div>
                <dt className="text-xs text-muted-foreground">queued</dt>
                <dd className="text-3xl font-semibold">{formatCount(health.jobs.queued)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">running</dt>
                <dd className="text-3xl font-semibold">{formatCount(health.jobs.running)}</dd>
              </div>
              <div className="col-span-2 text-sm text-muted-foreground">
                oldest queued: {formatSeconds(health.jobs.oldest_queued_seconds)}
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">Unknown while Postgres is down.</p>
          )}
        </section>
      </div>
    </div>
  );
}

type Tone = "ok" | "degraded" | "down";

function Banner({ tone, title, detail }: { tone: Tone; title: string; detail: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-3xl border p-5",
        tone === "ok" && "border-success/40 bg-success/5",
        tone === "degraded" && "border-warning/40 bg-warning/5",
        tone === "down" && "border-destructive/40 bg-destructive/5",
      )}
    >
      <span
        className={cn(
          "animate-pulse-soft size-3 rounded-full",
          tone === "ok" ? "bg-success" : tone === "degraded" ? "bg-warning" : "bg-destructive",
        )}
      />
      <p className="text-lg font-medium">{title}</p>
      <p className="ml-auto text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

function CheckTile({ title, check }: { title: string; check: Check }) {
  return (
    <Tile
      title={title}
      status={check.status}
      metric={check.status === "ok" ? `${check.latency_ms ?? "?"} ms` : "down"}
      detail={check.error ?? "reachable"}
    />
  );
}

function Tile({
  title,
  status,
  metric,
  detail,
}: {
  title: string;
  status: "ok" | "down";
  metric: string;
  detail: string;
}) {
  return (
    <section
      className={cn("rounded-3xl border bg-card p-5", status === "down" && "border-destructive/50")}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn("size-2 rounded-full", status === "ok" ? "bg-success" : "bg-destructive")}
        />
        <h2 className="font-sans text-sm font-semibold tracking-widest text-muted-foreground uppercase">
          {title}
        </h2>
      </div>
      <p className="tabular mt-2 font-mono text-3xl font-semibold">{metric}</p>
      <p className="mt-1 truncate text-sm text-muted-foreground" title={detail}>
        {detail}
      </p>
    </section>
  );
}
