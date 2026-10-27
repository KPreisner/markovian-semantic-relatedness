import Link from "next/link";

import { Logo } from "@/components/site/logo";

const LINKS = [
  { href: "/concepts", label: "Concepts" },
  { href: "/search", label: "Search" },
  { href: "/health", label: "Health" },
];

export function SiteNav() {
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
          href="/fastapi/docs"
          className="ml-auto hidden rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:block"
        >
          API docs ↗
        </a>
      </nav>
    </header>
  );
}
