export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          Markovian Semantic Relatedness: an implementation of{" "}
          <a
            className="underline underline-offset-4 hover:text-foreground"
            href="/MarkovianSemanticRelatedness_april_25_2022.pdf"
            target="_blank"
          >
            the paper
          </a>
          .
        </p>
        <p>
          <a
            className="underline underline-offset-4 hover:text-foreground"
            href="https://github.com/KPreisner/markovian-semantic-relatedness"
          >
            Source on GitHub
          </a>
        </p>
      </div>
    </footer>
  );
}
