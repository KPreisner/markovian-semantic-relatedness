// The paper's toy corpus as a graph (Figure 3 and matrix (1)): terms that share a chunk are
// joined. A walker leaves "cat" and wanders; the terms it reaches soonest, relative to how far
// they usually are from everything else, make up cat's concept. Bill / G / Bill G form their own
// component, which the walk can never reach.

type Node = { id: string; x: number; y: number; concept?: number };

// `concept` ranks cat's concept by weight (0 is the root), for the halos: fat 70.6, in 54.5,
// hat 45.1, the 42.3 at λ = 1000; dog, wild, lost, and child have negative z.
const NODES: Node[] = [
  { id: "cat", x: 190, y: 120, concept: 0 },
  { id: "hat", x: 132, y: 228, concept: 3 },
  { id: "fat", x: 72, y: 118, concept: 1 },
  { id: "in", x: 236, y: 292, concept: 2 },
  { id: "the", x: 318, y: 196, concept: 4 },
  { id: "dog", x: 438, y: 120 },
  { id: "wild", x: 540, y: 74 },
  { id: "lost", x: 452, y: 278 },
  { id: "child", x: 560, y: 248 },
  { id: "Bill", x: 528, y: 352 },
  { id: "G", x: 600, y: 330 },
  { id: "Bill G", x: 600, y: 392 },
];

const EDGES: [string, string][] = [
  ["cat", "fat"],
  ["cat", "hat"],
  ["cat", "in"],
  ["cat", "the"],
  ["fat", "the"],
  ["hat", "in"],
  ["hat", "the"],
  ["in", "the"],
  ["the", "dog"],
  ["the", "wild"],
  ["the", "lost"],
  ["the", "child"],
  ["dog", "wild"],
  ["dog", "lost"],
  ["lost", "child"],
  ["Bill", "G"],
  ["Bill", "Bill G"],
  ["G", "Bill G"],
];

// One walk from cat, back to cat.
const WALK = [
  "cat",
  "hat",
  "the",
  "dog",
  "wild",
  "the",
  "cat",
  "in",
  "hat",
  "the",
  "lost",
  "child",
  "the",
  "cat",
];

const at = (id: string) => NODES.find((n) => n.id === id)!;

export function WalkGraph({ className }: { className?: string }) {
  const path = WALK.map((id, i) => `${i === 0 ? "M" : "L"}${at(id).x} ${at(id).y}`).join(" ");
  return (
    <figure className={className}>
      <svg
        viewBox="0 0 660 430"
        role="img"
        aria-labelledby="walk-graph-title"
        className="h-auto w-full"
      >
        <title id="walk-graph-title">
          The paper&apos;s toy corpus as a co-occurrence graph, with a random walk starting at
          &quot;cat&quot;
        </title>
        <defs>
          <linearGradient id="walk-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--primary)" />
            <stop offset="1" stopColor="var(--accent)" />
          </linearGradient>
          <radialGradient id="walk-halo">
            <stop offset="0" stopColor="var(--primary)" stopOpacity="0.45" />
            <stop offset="1" stopColor="var(--primary)" stopOpacity="0" />
          </radialGradient>
          <filter id="walk-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>

        {EDGES.map(([a, b]) => (
          <line
            key={`${a}-${b}`}
            x1={at(a).x}
            y1={at(a).y}
            x2={at(b).x}
            y2={at(b).y}
            stroke="var(--foreground)"
            strokeOpacity="0.14"
            strokeWidth="1.5"
          />
        ))}

        {/* The walk's route, faint, and the walker on it. */}
        <path
          d={path}
          fill="none"
          stroke="url(#walk-gradient)"
          strokeOpacity="0.35"
          strokeWidth="2"
          strokeDasharray="4 6"
        />
        {/* Hidden until its motion starts, so it never flashes at the origin. */}
        <g className="motion-reduce:hidden" opacity="0">
          <set attributeName="opacity" to="1" begin="0.05s" fill="freeze" />
          <circle r="9" fill="var(--accent)" filter="url(#walk-glow)">
            <animateMotion dur="14s" repeatCount="indefinite" path={path} />
          </circle>
          <circle r="5" fill="var(--accent)">
            <animateMotion dur="14s" repeatCount="indefinite" path={path} />
          </circle>
        </g>

        {NODES.map((node) => {
          const inConcept = node.concept !== undefined;
          const root = node.concept === 0;
          return (
            <g key={node.id}>
              {inConcept && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={root ? 46 : 34 - node.concept! * 4}
                  fill="url(#walk-halo)"
                />
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={root ? 9 : 6.5}
                fill="var(--background)"
                stroke={inConcept ? "url(#walk-gradient)" : "var(--muted-foreground)"}
                strokeWidth={root ? 3 : 2}
              />
              <text
                x={node.x}
                y={node.y - (root ? 16 : 13)}
                textAnchor="middle"
                className="fill-foreground font-mono"
                fontSize={root ? 15 : 13}
                fontWeight={root ? 600 : 400}
                opacity={inConcept ? 1 : 0.7}
              >
                {node.id}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-3 text-center text-sm text-muted-foreground">
        The paper&apos;s toy corpus. Walks from{" "}
        <span className="font-mono text-foreground">cat</span> reach{" "}
        <span className="font-mono text-foreground">fat</span>,{" "}
        <span className="font-mono text-foreground">in</span>, and{" "}
        <span className="font-mono text-foreground">hat</span> unusually soon, compared with how far
        they are from the reference terms: cat&apos;s concept.
      </figcaption>
    </figure>
  );
}
