/** The web server is up (the container healthcheck). Checks nothing else, so it's prerendered. */
export function GET() {
  return Response.json({ status: "ok" });
}
