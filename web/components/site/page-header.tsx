import type { ReactNode } from "react";

/** The band at the top of each page: eyebrow, serif title, a line of lead, and optional extras. */
export function PageHeader({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="relative overflow-hidden border-b">
      <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
      <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-10">
        <p className="font-mono text-xs tracking-[0.2em] text-muted-foreground uppercase">
          {eyebrow}
        </p>
        <h1 className="text-4xl md:text-5xl">{title}</h1>
        {lead && <p className="max-w-2xl text-muted-foreground">{lead}</p>}
        {children}
      </div>
    </section>
  );
}
