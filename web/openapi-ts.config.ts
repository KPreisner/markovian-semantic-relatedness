// Types and Zod schemas for the BFF, generated from the API's OpenAPI schema (openapi.json,
// written by `python -m msr_api.openapi`). Regenerate both with `task web:typegen`.
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: { path: "./lib/api" },
  plugins: [
    "@hey-api/typescript",
    // Timestamps are UTC (`…Z`) today, but accept any offset, so a database in another time zone
    // can't make every response invalid.
    { name: "zod", dates: { offset: true } },
  ],
});
