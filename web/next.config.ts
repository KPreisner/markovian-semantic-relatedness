import type { NextConfig } from "next";

// The API inside the stack. Rewrites are resolved at build time, so this is a build argument of
// the image (web/Dockerfile) as well as the BFF's runtime setting.
const apiUrl = process.env.MSR_API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // The FastAPI service and its OpenAPI docs (/fastapi/docs), proxied as-is. The UI never uses
  // these; it calls its own /api/* route handlers (the BFF).
  async rewrites() {
    return [{ source: "/fastapi/:path*", destination: `${apiUrl}/:path*` }];
  },
  async redirects() {
    return [{ source: "/fastapi", destination: "/fastapi/docs", permanent: false }];
  },
};

export default nextConfig;
