// A stand-in for FastAPI: a real HTTP server on a free port whose routes each test sets, so the
// BFF's fetches, retries, timeouts, and streams run for real.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import { resetConfig } from "@/lib/server/config";

export type Seen = {
  method: string;
  url: string;
  headers: IncomingMessage["headers"];
  body: string;
};
export type Route = (
  req: IncomingMessage,
  res: ServerResponse,
  body: string,
) => void | Promise<void>;

export class StubApi {
  readonly seen: Seen[] = [];
  private routes = new Map<string, Route>();
  private server: Server | undefined;

  /** `key` is "METHOD /path" (the query string is ignored). */
  on(key: string, route: Route): this {
    this.routes.set(key, route);
    return this;
  }

  json(key: string, status: number, body: unknown): this {
    return this.on(key, (_req, res) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(body));
    });
  }

  async start(): Promise<void> {
    this.server = createServer(async (req, res) => {
      let body = "";
      for await (const chunk of req) body += chunk;
      this.seen.push({ method: req.method ?? "", url: req.url ?? "", headers: req.headers, body });
      const route = this.routes.get(
        `${req.method} ${new URL(req.url ?? "/", "http://x").pathname}`,
      );
      if (!route) {
        res.writeHead(500).end("no stub route");
        return;
      }
      await route(req, res, body);
    });
    await new Promise<void>((resolve) => this.server!.listen(0, "127.0.0.1", resolve));
    const { port } = this.server.address() as AddressInfo;
    process.env.MSR_API_URL = `http://127.0.0.1:${port}`;
    resetConfig();
  }

  async stop(): Promise<void> {
    this.server?.closeAllConnections();
    await new Promise<void>((resolve) => this.server?.close(() => resolve()));
  }

  reset(): void {
    this.seen.length = 0;
    this.routes.clear();
  }
}
