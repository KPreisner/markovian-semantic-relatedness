import { cn } from "@/lib/utils";

/** A row of small cards, each a key point in a bold few words and a line of explanation. */
export function KeyPoints({ points }: { points: { title: string; body: string }[] }) {
  return (
    <ul
      className={cn("mt-2 grid gap-3", points.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}
    >
      {points.map((point) => (
        <li key={point.title} className="rounded-2xl border bg-card/70 p-4 backdrop-blur">
          <h3 className="font-sans text-sm font-semibold tracking-normal">{point.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{point.body}</p>
        </li>
      ))}
    </ul>
  );
}
