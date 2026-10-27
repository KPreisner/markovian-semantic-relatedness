import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="text-5xl">
        Nowhere to <em className="text-gradient pr-1">walk</em>
      </h1>
      <p className="text-muted-foreground">
        That model, concept, search, or job doesn&apos;t exist (or no longer does).
      </p>
      <Button asChild variant="outline">
        <Link href="/workbench">Back to the workbench</Link>
      </Button>
    </div>
  );
}
