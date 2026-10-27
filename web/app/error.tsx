"use client";

import { Button } from "@/components/ui/button";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center">
      <p className="font-mono text-sm text-muted-foreground">error</p>
      <h1 className="text-5xl">Something went wrong</h1>
      <p className="text-muted-foreground">
        {error.message || "The page couldn't be loaded."}{" "}
        {error.digest && <span className="font-mono">({error.digest})</span>}
      </p>
      <Button variant="outline" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
