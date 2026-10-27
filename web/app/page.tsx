export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Markovian Semantic Relatedness</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        The stack is running. Until the UI is built, the API and its interactive docs are here:
      </p>
      <ul className="flex flex-col gap-2">
        <li>
          <a className="text-blue-700 underline dark:text-blue-400" href="/fastapi/docs">
            API docs (Swagger UI)
          </a>
          : every endpoint, with &ldquo;Try it out&rdquo;
        </li>
        <li>
          <a className="text-blue-700 underline dark:text-blue-400" href="/fastapi/redoc">
            API reference (ReDoc)
          </a>
        </li>
        <li>
          <a className="text-blue-700 underline dark:text-blue-400" href="/api/health">
            Stack health
          </a>
        </li>
      </ul>
    </main>
  );
}
