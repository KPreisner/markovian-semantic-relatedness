/** Three terms and the edges between them, with the walker on one: the MSR mark. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <defs>
        <linearGradient id="msr-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--primary)" />
          <stop offset="1" stopColor="var(--accent)" />
        </linearGradient>
      </defs>
      <path
        d="M7 22 L16 7 L25 21 Z"
        fill="none"
        stroke="url(#msr-logo)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle
        cx="7"
        cy="22"
        r="3.2"
        fill="var(--background)"
        stroke="url(#msr-logo)"
        strokeWidth="2"
      />
      <circle
        cx="16"
        cy="7"
        r="3.2"
        fill="var(--background)"
        stroke="url(#msr-logo)"
        strokeWidth="2"
      />
      <circle
        cx="25"
        cy="21"
        r="3.2"
        fill="var(--background)"
        stroke="url(#msr-logo)"
        strokeWidth="2"
      />
      <circle cx="20.5" cy="14" r="2" fill="var(--accent)" />
    </svg>
  );
}
