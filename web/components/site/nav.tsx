import Link from "next/link";

import { Logo } from "@/components/site/logo";

const LINKS = [
  { href: "/concepts", label: "Concepts" },
  { href: "/searches", label: "Searches" },
  { href: "/stack", label: "Stack" },
  { href: "/health", label: "Health" },
];

export function SiteNav() {
  return (
    <>
      <PortfolioBar />
      <Header />
    </>
  );
}

/** A thin strip above the nav, back to the author's portfolio; it scrolls away with the page. */
function PortfolioBar() {
  return (
    <div className="border-b bg-muted/40">
      <div className="mx-auto flex h-8 w-full max-w-6xl items-center px-4 font-mono text-xs text-muted-foreground">
        <a href="https://karl.preisner.us" className="transition-colors hover:text-foreground">
          ← Karl Preisner · portfolio
        </a>
      </div>
    </div>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/75 backdrop-blur-md">
      <nav className="mx-auto flex h-14 w-full max-w-6xl items-center gap-3 px-4 sm:gap-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Logo className="size-7" />
          <span>MSR</span>
        </Link>
        <ul className="flex items-center gap-1 text-sm text-muted-foreground">
          {LINKS.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                className="rounded-md px-2 py-1.5 transition-colors hover:bg-muted hover:text-foreground sm:px-3"
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <a
          href="/MarkovianSemanticRelatedness_april_25_2022.pdf"
          target="_blank"
          className="ml-auto hidden rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:block"
        >
          Paper ↗
        </a>
        <a
          href="/fastapi/docs"
          className="hidden rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:block"
        >
          Explore the API ↗
        </a>
      </nav>
    </header>
  );
}
