// The route handlers, called directly with Web Requests (they're plain functions), against the
// stub API.
import { validate, version } from "uuid";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { GET as health } from "@/app/api/health/route";
import { POST as requestConcept } from "@/app/api/models/[modelId]/concepts/route";
import { GET as terms } from "@/app/api/models/[modelId]/terms/route";
import { pending } from "./fixtures";
import { StubApi } from "./stub-api";

const api = new StubApi();

beforeAll(() => api.start());
afterAll(() => api.stop());
beforeEach(() => api.reset());

function params<T>(value: T) {
  return { params: Promise.resolve(value) };
}

function post(url: string, body: unknown, headers: Record<string, string> = {}) {
  return new Request(url, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("POST /api/models/[modelId]/concepts", () => {
  it("forwards the request and answers with the API's status and body", async () => {
    api.json("POST /models/simplewiki-small/concepts", 202, pending());
    const cid = "01a17a3a-0000-7000-8000-00000000000a";
    const response = await requestConcept(
      post(
        "http://web/api/models/simplewiki-small/concepts",
        { root: "trumpet" },
        { "X-Correlation-ID": cid },
      ),
      params({ modelId: "simplewiki-small" }),
    );
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual(pending());
    expect(response.headers.get("X-Correlation-ID")).toBe(cid);
    expect(JSON.parse(api.seen[0].body)).toEqual({ root: "trumpet" });
    expect(api.seen[0].headers["x-correlation-id"]).toBe(cid);
  });

  it("creates a UUIDv7 correlation id when the request has none (or a bad one)", async () => {
    api.json("POST /models/m/concepts", 202, pending());
    const response = await requestConcept(
      post("http://web/api/models/m/concepts", { root: "cat" }, { "X-Correlation-ID": "nope" }),
      params({ modelId: "m" }),
    );
    const cid = response.headers.get("X-Correlation-ID") ?? "";
    expect(validate(cid) && version(cid)).toBe(7);
    expect(api.seen[0].headers["x-correlation-id"]).toBe(cid);
  });

  it("rejects unknown fields and bad types before calling the API", async () => {
    const response = await requestConcept(
      post("http://web/api/models/m/concepts", { root: "cat", steps: "many", bogus: 1 }),
      params({ modelId: "m" }),
    );
    expect(response.status).toBe(422);
    const { error } = await response.json();
    expect(error.code).toBe("invalid_request");
    expect(error.details.map((d: { loc: string[] }) => d.loc.join("."))).toEqual(
      expect.arrayContaining(["body.steps", "body"]),
    );
    expect(api.seen).toHaveLength(0);
  });

  it("passes the API's 404 through", async () => {
    const body = { error: { code: "term_not_found", message: "'Cat' is not in model 'm'" } };
    api.json("POST /models/m/concepts", 404, body);
    const response = await requestConcept(
      post("http://web/api/models/m/concepts", { root: "Cat" }),
      params({ modelId: "m" }),
    );
    expect([response.status, await response.json()]).toEqual([404, body]);
  });
});

describe("GET routes", () => {
  it("forwards only the known query parameters", async () => {
    api.json("GET /models/m/terms", 200, []);
    await terms(
      new Request("http://web/api/models/m/terms?prefix=trump&limit=5&evil=1"),
      params({ modelId: "m" }),
    );
    expect(api.seen[0].url).toBe("/models/m/terms?prefix=trump&limit=5");
  });

  it("encodes path parameters", async () => {
    api.json("GET /models/a%2Fb/terms", 200, []);
    const response = await terms(
      new Request("http://web/api/models/a%2Fb/terms?prefix=x"),
      params({ modelId: "a/b" }),
    );
    expect(response.status).toBe(200);
  });

  it("passes the health report's 503 through with its body", async () => {
    const report = {
      status: "down",
      api: { status: "ok", version: "0.1.0", instance: "api-1", uptime_seconds: 1 },
      postgres: { status: "down", latency_ms: null, error: "OperationalError: gone" },
      redis: { status: "ok", latency_ms: 1, error: null },
      broker: { status: "ok", latency_ms: 1, error: null, queues: [] },
      workers: { status: "ok", count: 1, nodes: ["celery@w"] },
      jobs: null,
    };
    api.json("GET /health", 503, report);
    const response = await health(new Request("http://web/api/health"));
    expect([response.status, await response.json()]).toEqual([503, report]);
  });
});
