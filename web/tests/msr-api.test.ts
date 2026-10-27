import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { z } from "zod";

import { zGetJobResponse, zHealthResponse } from "@/lib/api/zod.gen";
import { resetConfig } from "@/lib/server/config";
import { HttpError } from "@/lib/server/errors";
import { callApi } from "@/lib/server/msr-api";
import { job } from "./fixtures";
import { StubApi } from "./stub-api";

const api = new StubApi();
const CID = "01a17a3a-0000-7000-8000-000000000001";

beforeAll(() => api.start());
afterAll(() => api.stop());
beforeEach(() => api.reset());

async function failure(promise: Promise<unknown>): Promise<HttpError> {
  const error = await promise.then(
    () => undefined,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(HttpError);
  return error as HttpError;
}

describe("callApi", () => {
  it("sends the correlation id and query, and returns the validated body", async () => {
    api.json("GET /jobs/x", 200, job({ status: "running" }));
    const result = await callApi({
      path: "/jobs/x",
      query: { limit: 5, empty: "", unset: undefined },
      schema: zGetJobResponse,
      correlationId: CID,
    });
    expect(result).toMatchObject({ status: 200, data: { status: "running" } });
    expect(api.seen[0].headers["x-correlation-id"]).toBe(CID);
    expect(api.seen[0].url).toBe("/jobs/x?limit=5");
  });

  it("retries a GET on 503 and network-level failures", async () => {
    let calls = 0;
    api.on("GET /jobs/x", (_req, res) => {
      calls += 1;
      if (calls < 3) res.writeHead(503).end("{}");
      else res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(job()));
    });
    await callApi({ path: "/jobs/x", schema: zGetJobResponse, correlationId: CID });
    expect(calls).toBe(3);
  });

  it("never retries a POST", async () => {
    api.json("POST /searches", 503, { error: { code: "publish_failed", message: "try again" } });
    const error = await failure(
      callApi({
        path: "/searches",
        method: "POST",
        body: {},
        schema: z.object({}),
        correlationId: CID,
      }),
    );
    expect(api.seen).toHaveLength(1);
    expect(error.status).toBe(503);
    expect(error.body.error.code).toBe("publish_failed");
  });

  it("passes the API's errors through", async () => {
    const body = { error: { code: "job_not_found", message: "no job x" } };
    api.json("GET /jobs/x", 404, body);
    const error = await failure(
      callApi({ path: "/jobs/x", schema: zGetJobResponse, correlationId: CID }),
    );
    expect([error.status, error.body]).toEqual([404, body]);
  });

  it("rejects a response that doesn't match its schema", async () => {
    api.json("GET /jobs/x", 200, { ...job(), status: "exploded" });
    const error = await failure(
      callApi({ path: "/jobs/x", schema: zGetJobResponse, correlationId: CID }),
    );
    expect([error.status, error.body.error.code]).toEqual([502, "upstream_invalid"]);
  });

  it("accepts a schema'd non-2xx status when asked (the health report's 503)", async () => {
    api.json("GET /health", 503, { status: "down" });
    const error = await failure(
      callApi({ path: "/health", schema: zHealthResponse, correlationId: CID, okStatuses: [503] }),
    );
    // Not the error shape, but not a valid report either: still checked against the schema.
    expect(error.body.error.code).toBe("upstream_invalid");
  });

  it("times out", async () => {
    process.env.MSR_API_TIMEOUT_MS = "100";
    resetConfig();
    try {
      api.on("GET /jobs/x", () => undefined); // never answers
      const error = await failure(
        callApi({ path: "/jobs/x", schema: zGetJobResponse, correlationId: CID }),
      );
      expect([error.status, error.body.error.code]).toEqual([504, "upstream_timeout"]);
      expect(api.seen).toHaveLength(3); // each attempt timed out
    } finally {
      delete process.env.MSR_API_TIMEOUT_MS;
      resetConfig();
    }
  });

  it("reports an unreachable API", async () => {
    const url = process.env.MSR_API_URL;
    process.env.MSR_API_URL = "http://127.0.0.1:9"; // discard port: refused
    resetConfig();
    try {
      const error = await failure(
        callApi({ path: "/jobs/x", schema: zGetJobResponse, correlationId: CID }),
      );
      expect([error.status, error.body.error.code]).toEqual([502, "upstream_unavailable"]);
    } finally {
      process.env.MSR_API_URL = url;
      resetConfig();
    }
  });
});
