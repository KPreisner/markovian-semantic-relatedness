// Runs once when the server starts: validate the BFF's settings so a bad value fails the start,
// not the first request.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { config } = await import("@/lib/server/config");
    config();
  }
}
