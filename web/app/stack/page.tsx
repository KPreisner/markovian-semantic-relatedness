import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/site/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "The tech stack" };

// The containers, top to bottom in the order a request reaches them (compose.yaml).
type Tier = { label: string; boxes: { name: string; tech: string; note: string }[] };

const TIERS: Tier[] = [
  {
    label: "Browser",
    boxes: [{ name: "You", tech: "React 19", note: "calls only the web container" }],
  },
  {
    label: "Edge",
    boxes: [
      {
        name: "web",
        tech: "Next.js 16 · Node 24",
        note: "the UI and its BFF; the only published port",
      },
    ],
  },
  {
    label: "API",
    boxes: [
      {
        name: "api",
        tech: "FastAPI · Uvicorn · Python 3.14",
        note: "REST and Server-Sent Events; stateless",
      },
    ],
  },
  {
    label: "State",
    boxes: [
      { name: "postgres", tech: "PostgreSQL 18", note: "models, concepts, searches, jobs" },
      { name: "rabbitmq", tech: "RabbitMQ 4.4", note: "the cpu and search queues" },
      { name: "redis", tech: "Redis 8.8", note: "one progress stream per job" },
    ],
  },
  {
    label: "Workers",
    boxes: [
      { name: "worker-cpu", tech: "Celery 5.6", note: "concept walks, from the cpu queue" },
      { name: "worker-search", tech: "Celery 5.6", note: "corpus scans, from the search queue" },
    ],
  },
  {
    label: "Disk",
    boxes: [
      { name: "data/", tech: "NumPy · SciPy arrays", note: "models, corpora, concepts, searches" },
      {
        name: "builder",
        tech: "msr CLI · spaCy 3.8",
        note: "builds models and corpora, then exits",
      },
    ],
  },
];

const SERVICES = [
  {
    name: "web",
    tech: "Next.js 16, React 19, Tailwind 4, Zod",
    body: "Serves the UI and a backend-for-frontend: the browser only ever calls web's own /api/* route handlers, which call FastAPI inside the stack and validate every response against Zod schemas generated from the API's OpenAPI schema. It also proxies the API itself under /fastapi/, docs included.",
  },
  {
    name: "api",
    tech: "FastAPI, Uvicorn, psycopg 3, Pydantic 2",
    body: "Answers REST requests and streams job progress as Server-Sent Events. It holds no files and no state of its own: it reads Postgres, publishes tasks to RabbitMQ by name, and reads progress from Redis. A correlation id follows each request from the BFF through the API and into the task's message headers.",
  },
  {
    name: "postgres",
    tech: "PostgreSQL 18, raw SQL",
    body: "The source of truth: the model registry and vocabularies, concept tables, corpora, search hits, and every job's status and attempts. Plain-SQL migrations run once by a one-shot migrate container before anything else starts, and each service logs in as its own role with only the privileges it needs.",
  },
  {
    name: "rabbitmq",
    tech: "RabbitMQ 4.4, durable direct exchanges",
    body: "The Celery broker. Each queue (cpu for concept walks, search for corpus scans) is durable and bound to a direct exchange of its own name. The consumer timeout is raised to about a year, since a walk or scan can run for hours while its message stays unacknowledged.",
  },
  {
    name: "redis",
    tech: "Redis 8.8 Streams",
    body: "Holds only progress: one stream per job, which the worker appends to and the API reads. A page that reconnects sends its Last-Event-ID and replays from there. Streams are capped and expire an hour after their job ends.",
  },
  {
    name: "workers",
    tech: "Celery 5.6, NumPy, SciPy",
    body: "One task at a time per container; scale by running more containers. Concept workers mount the models read-only and walk on threads; search workers mount the corpora read-only and never load a model. Both write their results to disk and Postgres, then mark the job done in the same transaction.",
  },
  {
    name: "builder",
    tech: "the msr CLI, spaCy 3.8",
    body: "A run-and-exit container for the heavy, offline steps: downloading and parsing a dataset, counting co-occurrences, building the transition matrix and the comparison walks, and registering the model. Builds are staged and checksummed, so an interrupted one resumes where it stopped.",
  },
];

const FLOW = [
  {
    title: "Ask",
    body: "You pick a model and a term. The browser posts to web's BFF, which validates the request and forwards it to FastAPI.",
  },
  {
    title: "Cache or enqueue",
    body: "The API hashes the request's parameters into a cache key. A concept already built is returned at once. Otherwise one INSERT … ON CONFLICT against the active jobs either creates a job or joins the one already running, so two identical requests never walk twice.",
  },
  {
    title: "Publish",
    body: "A new job's task goes to RabbitMQ's cpu queue, and the page moves to the job's progress view.",
  },
  {
    title: "Walk",
    body: "A cpu worker takes the task, counts the attempt in Postgres, loads the model from disk, and runs the walk, appending progress to the job's Redis stream as it goes.",
  },
  {
    title: "Watch",
    body: "The API streams those events as Server-Sent Events, and web relays them to the browser, validated, with their ids, so a dropped connection resumes where it stopped.",
  },
  {
    title: "Store",
    body: "The worker saves the concept to disk and Postgres and marks the job succeeded in one transaction. The last event names the concept, and the page opens it.",
  },
];

const CHOICES = [
  {
    title: "Late acks, bounded retries",
    body: "A task's message stays on the broker until the task returns, so a worker killed mid-walk has its job redelivered to another. Postgres counts the attempts, and a job fails for good after three.",
  },
  {
    title: "Two queues",
    body: "Walks and scans run on separate workers, so a long walk never holds up a search, and a search worker never needs a model's worth of memory.",
  },
  {
    title: "Built once, shared",
    body: "Concepts are cached under the model, root, and a hash of every parameter that changes the result. Changing only a scoring setting reuses the saved walk and skips the minutes it took.",
  },
  {
    title: "A sealed backend",
    body: "Postgres, RabbitMQ, Redis, the API, and the workers sit on an internal Docker network with no route out. Only web is published, on localhost; only the builder can reach the internet, for its downloads.",
  },
  {
    title: "Types end to end",
    body: "Pydantic models define the API; its OpenAPI schema generates the BFF's TypeScript types and Zod validators, and CI fails if they're stale. Python is checked with strict mypy.",
  },
  {
    title: "One workspace, small images",
    body: "A uv workspace with one package per deployable part (core, nlp, db, api, worker, build) and one lockfile, so each container installs only what it runs.",
  },
];

export default function StackPage() {
  return (
    <>
      <PageHeader
        eyebrow="The tech stack"
        title={
          <>
            How it&rsquo;s <em className="text-gradient pr-1">built</em>
          </>
        }
        lead="A Python core for the walk and the search, served by FastAPI, run as jobs by Celery workers over RabbitMQ, with Postgres for state, Redis for progress, and a Next.js UI, all in Docker Compose."
      >
        <div className="mt-2 flex flex-wrap gap-3">
          <Button
            asChild
            className="bg-gradient text-primary-foreground shadow-[0_0_32px_var(--glow)]"
          >
            <Link href="/health">Stack health →</Link>
          </Button>
          <Button asChild variant="outline">
            <a href="/fastapi/docs">API docs ↗</a>
          </Button>
        </div>
      </PageHeader>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-16 px-4 py-10">
        <section aria-labelledby="map-heading" className="flex flex-col gap-6">
          <h2 id="map-heading" className="text-3xl md:text-4xl">
            The containers
          </h2>
          <ol className="flex flex-col items-stretch">
            {TIERS.map((tier, i) => (
              <li key={tier.label} className="flex flex-col items-center">
                {i > 0 && (
                  <span
                    aria-hidden
                    className="h-6 w-px bg-linear-to-b from-primary/60 to-primary/10"
                  />
                )}
                <div className="grid w-full gap-3 sm:grid-cols-[6rem_1fr] sm:items-center">
                  <span className="font-mono text-xs tracking-widest text-muted-foreground uppercase sm:text-right">
                    {tier.label}
                  </span>
                  <div
                    className={cn(
                      "grid gap-3",
                      tier.boxes.length === 2 && "sm:grid-cols-2",
                      tier.boxes.length === 3 && "sm:grid-cols-3",
                    )}
                  >
                    {tier.boxes.map((box) => (
                      <div key={box.name} className="rounded-2xl border bg-card px-4 py-3">
                        <p className="font-mono font-semibold">{box.name}</p>
                        <p className="text-xs text-primary">{box.tech}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{box.note}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="flow-heading" className="flex flex-col gap-6">
          <h2 id="flow-heading" className="text-3xl md:text-4xl">
            A concept, from click to result
          </h2>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FLOW.map((step, i) => (
              <li key={step.title} className="rounded-2xl border bg-card p-5">
                <span className="text-gradient font-heading text-4xl leading-none">0{i + 1}</span>
                <h3 className="mt-2 font-sans text-base font-semibold tracking-normal">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
              </li>
            ))}
          </ol>
          <p className="text-sm text-muted-foreground">
            A search runs the same way on the search queue: its worker reads each concept&rsquo;s
            terms from Postgres, scans the raw corpus chunk by chunk, and stores the ranked hits.
          </p>
        </section>

        <section aria-labelledby="services-heading" className="flex flex-col gap-6">
          <h2 id="services-heading" className="text-3xl md:text-4xl">
            Each service
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {SERVICES.map((s) => (
              <article key={s.name} className="rounded-2xl border bg-card p-5">
                <h3 className="font-mono text-base font-semibold tracking-normal">{s.name}</h3>
                <p className="text-xs text-primary">{s.tech}</p>
                <p className="mt-2 text-sm text-muted-foreground">{s.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="choices-heading" className="flex flex-col gap-6">
          <h2 id="choices-heading" className="text-3xl md:text-4xl">
            Choices worth knowing
          </h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CHOICES.map((c) => (
              <li key={c.title} className="rounded-2xl border bg-card p-5">
                <h3 className="font-sans text-base font-semibold tracking-normal">{c.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{c.body}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
