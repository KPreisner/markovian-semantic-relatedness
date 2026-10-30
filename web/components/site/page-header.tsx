import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The band at the top of each page: eyebrow, serif title, a line of lead, and optional extras,
 * with an optional illustration beside them on wide screens.
 */
export function PageHeader({
  eyebrow,
  title,
  lead,
  children,
  aside,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="relative overflow-hidden border-b">
      <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
      <div
        className={cn(
          "relative mx-auto grid w-full max-w-6xl items-center gap-8 px-4 py-10",
          aside && "lg:grid-cols-[1fr_26rem]",
        )}
      >
        <div className="flex flex-col gap-3">
          <p className="font-mono text-xs tracking-[0.2em] text-muted-foreground uppercase">
            {eyebrow}
          </p>
          <h1 className="text-4xl md:text-5xl">{title}</h1>
          {lead && <p className="max-w-2xl text-muted-foreground">{lead}</p>}
          {children}
        </div>
        {aside}
      </div>
    </section>
  );
}
