# web

The MSR UI and its BFF (Next.js App Router). See the root README for the tasks; Node runs only in
containers (`task web:*`).

- `app/` pages: `/` (landing), `/workbench`, `/jobs/[jobId]`, `/concepts/[conceptId]`, `/search`,
  `/searches/[searchId]`, `/health`. Each is a static shell with its data in `<Suspense>`: server
  components load through `lib/server/data.ts`; client components (in `components/`) call the
  BFF and follow jobs with `lib/client/use-job-events.ts`.
- `app/globals.css`: the design tokens (light and dark, ten concept colors) and utilities.
- `app/api/**/route.ts`: the BFF. Each handler forwards one API operation and validates the
  response with its generated Zod schema. `app/api/jobs/[jobId]/events` relays job progress (SSE).
- `app/healthz`: the container's liveness check.
- `lib/server/`: server-only code: `msr-api.ts` (the API client: timeouts, GET retries,
  correlation ids, validation), `events.ts` (the SSE relay), `route.ts` (handler plumbing),
  `config.ts` (environment, validated at startup by `instrumentation.ts`), `log.ts` (pino).
- `lib/api/`: generated from `openapi.json` by `task web:typegen` (types and Zod schemas). Don't
  edit; regenerate.
- `next.config.ts`: `output: "standalone"`, and the `/fastapi/*` rewrite to the API and its docs.
- `tests/`: Vitest against a stub API server.
