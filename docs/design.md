# Design notes and deviations from the paper

This is where the implementation departs from
[the paper](paper/MarkovianSemanticRelatedness_april_25_2022.pdf), fills in what it leaves
unspecified, and makes engineering choices the paper doesn't cover. Section (§) and equation
numbers refer to the paper. Notation follows it: r is the root (the UI's "chosen term"), C the
co-occurrence matrix, M, S, and T the transition matrices, v a hitting-time vector, λ the walk
length, and Q the number of reference nodes (the UI's "comparison terms").

## Summary

| Topic | Paper | Here |
|---|---|---|
| [Root's distance to itself](#a-roots-distance-to-itself-is-0) | Eqs. 11–18 give it a return time | 0, the textbook hitting time |
| [Eq. 23 scaling](#eq-23-scaling) | `y / (w_r · a)`, which maps the root to 1/a | `a · y / w_r`, so the root is 100 |
| [Root's own weight](#the-roots-own-weight) | Not specified | Its own z, pinned to rank 1 and always kept |
| [Reference set](#the-reference-set) | May include the root | Root's column dropped; 51 precomputed, so Q = 50 |
| [Reference component](#the-reference-component) | Not specified | The largest component; roots elsewhere use their own |
| [σ](#population-σ) | Not specified | Population (`ddof=0`) |
| [Stop words](#stop-words) | Not mentioned | The top 100 terms by chunk frequency, dropped before C is built |
| [Bilingual bridge](#the-bilingual-bridge) | Bitext only | Bitext plus dictionary pairs as w = 100 synthetic chunks |
| [Search matching](#whole-word-and-inside-word-matching) | Tokenized term sets | Raw text: whole words by default, inside words as an option |
| [Repeated chunks](#repeated-chunks-are-stored-once) | Not addressed | Each distinct chunk text is stored once |
| [Weak results](#weak-results-are-flagged) | Not addressed | The UI says when no hit is clearly about a concept |
| [Hitting time](#the-walk-is-kept-as-printed) | Called the expected hitting time | Eqs. 11–18 as printed (not a true first-passage time) |

## The walk and the concept

### A root's distance to itself is 0

The walk (Eqs. 11–18) accumulates, for every node k, the expected number of steps for a walk from
k to reach r. Run as printed, it also gives r itself a value: the expected time for a walk that
starts at r to come back. Here that entry is set to 0, the textbook hitting time of a node to
itself. The same rule zeroes each reference node's own entry in X′, though the outlier trim
(Eq. 22) drops that entry anyway.

**Why it matters.** The root's z is the scaling weight w_r (see
[Eq. 23 scaling](#eq-23-scaling)), and z compares a node's distance to the root with its
distances to the references: `z = −(v − μ)/σ`. The root's return time is only somewhat shorter
than its distance to the references, and on short walks (the small local model, λ = 100) barely
shorter at all, so its z lands near 0 and dividing by it blows every other weight up. With a
self-distance of 0, the root's z is `μᵣ/σᵣ`, which is always positive, and the root is always the
strongest term of its own concept.

That is the more intuitive reading of a concept: the chosen term is the best evidence of itself,
and a related term is evidence for it, not a substitute. A chunk that names the root outscores one
that only names a neighbor.

**What it costs.** The tables' scale isn't reproduced. Measured on the full Simple English model
(λ = 1000) with "Hermione Granger", the concept's terms and their order match Table 1 exactly,
but the root's distances to the references sit near the λ cap (μ = 1000.66, σ = 0.18), so
w_r = μ/σ ≈ 5,650. The printed return time gives w_r ≈ 309, and Table 1 implies about 208. Every
other weight is therefore about 18× smaller than the paper's (Ron Weasley 6.0 against 114.7).
Ranking within a concept, and which terms make the cut, don't depend on w_r at all. What does is
the balance between the root and its related terms in search, and because w_r = μᵣ/σᵣ, that
balance varies from root to root with σᵣ. A clipped option (the paper's w_r, but never below the
strongest other term's z) would keep the root on top at the paper's scale; it's a candidate for
the research write-up.

### Eq. 23 scaling

The printed scaling, `y' = y / (w_r · a)` with a = 100, maps the root to 1/100. Every table in the
paper shows the root at 100, which is `y' = a · y / w_r`. The implementation uses the latter.

### The root's own weight

The paper doesn't say how the root's weight is set. Here the root's z is computed like any other
node's and used as w_r, and the root is pinned to rank 1 and always kept, even below the z
threshold. The tables show other terms above 100, so the root wasn't forced to be the maximum
there; with the self-distance of 0 it now is, in practice.

Only a component too small for the outlier trim to leave any spread still fails: the toy model's
"Bill" has three references, so Q_eff = 2 and p = 1 leave one entry and σ = 0. That concept fails
with an error rather than dividing by zero.

### The reference set

§4.3.2 computes hitting times to Q shared reference nodes, X′, instead of to every node (the full
X of Eq. 19). If the root happens to be a reference, the paper keeps its column and relies on the
outlier trim to discard the root's distance to itself.

Here the model build walks Q + 1 = 51 references once, and each concept drops one column: the
root's own if it's a reference, otherwise the weakest pick (strategies return references best
first). Every real concept uses exactly Q = 50 columns, with no extra walks, and the root's
self-distance never enters its own statistics. Small components follow the same rule:
`refs = min(Q + 1, |component|)` and `Q_eff = refs − 1`.

Reference selection is pluggable. `degree-mean` (degree closest to the component's mean, the
paper's method) is the default; `df-mean`, `random`, `stratified-logdf`, `gauss-logdf`, and
`exact` (all N nodes, small models only) are there for a planned study of how the choice and Q
affect concepts. The log-df strategies sample on log df because df is Zipf-like.

### The reference component

Hitting times to a node in another connected component are just the walk's tail value λ + 1, so
they carry no information. References come from the largest component. A root in a smaller one
gets references from its own component, walked at concept time (those components are small, so
this is cheap). The walk and every statistic are restricted to the root's component; terms
outside it have no z.

### Population σ

The paper doesn't say which standard deviation it uses for the trimmed reference row. This uses
the population σ (`ddof=0`, NumPy's default). With Q − p = 40 entries, the two conventions differ
by about 1.3% in z.

### The walk is kept as printed

The paper calls v the expected hitting time, but Eqs. 11–18 don't compute a true first-passage
time: αₙ = Sⁿ·Γᵣ is the probability of being *at* the root at step n, including walks that already
passed through it, and the β update only approximates "not arrived yet". The walk is implemented
as printed, to stay faithful to the paper's results. An absorbing variant (the root as an
absorbing state, with the same cost per step) gives the toy model the same ordering with different
values, and is a candidate parameter for later.

The first step still uses S rather than the truncated T (§4.2.3), so terms that co-occur with the
root can always reach it. The implementation never materializes S for a concept: since C is
symmetric, column r of S is `C[:, r] / (C[r, r] · rowsum(M))` with entry r zeroed, so a concept
job loads only T, C, and `rowsum(M)`.

## The model

### Stop words

The paper doesn't mention stop words, but without them the most frequent terms dominate C and the
walk. Terms are dropped by document frequency (the number of chunks a term appears in), the top
100 by default, before C is built. That keeps the rule data-agnostic, since it needs no language
knowledge, and keeps the matrix small. It's also exact: removing a term changes no other entry of
C, so filtering first equals building the whole C and deleting those rows and columns. Other rules
(`maxdf:F`, `knee`) are available, and each build writes `df_report.json` with where each rule
would cut.

Tokens and named-entity spans are treated alike: both are just terms, and the stop-word rule runs
over all of them. An earlier design protected entity spans and kept "the", "a", and "The", each
tagged as an entity in a handful of their hundreds of thousands of chunks. Bilingual models can
choose stop words per language.

### The bilingual bridge

§5.3 bridges the two languages with bitext alone. Here each pair from a bilingual dictionary
(CC-CEDICT, with Simplified and Traditional forms as separate pairs) is also added to C as a
synthetic chunk, as though it appeared w = 100 times. Because these are chunks, they add to C's
diagonal too, so M stays a valid probability. A pair is added only if both terms are in the vocab,
and only after stop words are chosen, so it never affects them. This strengthens the bridge for
terms that are rare in the bitext.

### Vocab order

The vocab is sorted by code point, which reproduces the paper's toy order (Bill, Bill G, G, cat,
…), and a term's id is its index. Matching is case-sensitive everywhere, the same as the model's
terms.

## Search

### Whole-word and inside-word matching

The paper scores chunks by the concept terms in their tokenized term sets. Here search doesn't
tokenize at all: concept terms are matched in raw text with one Aho–Corasick automaton per search,
so a corpus needs no NLP pipeline and no index, and a scan runs at about 13 MB/s per process.

The first version matched raw substrings, which also finds hits a tokenizer would miss (近地 inside
近地小行星, Table 5's rank 6). On English it turned short and common terms into noise: "muggle"
in "smuggled", "organ" in "organizations", "cor" (from "cor anglais") in "according". A search for
"Hermione Granger" on September 2026 news, which never mentions her, came back with 100 of these.

So there are two modes:

- **Whole words** (`match: "word"`, the default). A match counts only if it doesn't run on into a
  word on either side: `cat` hits "cat", "cat's", "(cat)", and "cat-like", but not "category" or
  "scat". A side is checked only where the term's own edge is a letter or digit (so `U.S.` matches
  in "U.S.A."), and only against letters and digits of scripts that put spaces between words.
  Apostrophes, hyphens, and punctuation are boundaries.
- **Inside words** (`match: "substring"`), the original behavior, as an option in the API, the UI,
  and the CLI.

**Scripts written without spaces match anywhere,** in either mode: CJK ideographs, Hiragana,
Katakana, Thai, Lao, Khmer, Myanmar, and Hangul (Korean uses spaces, but particles attach to
nouns: 학교 in 학교에서). A word boundary means nothing there, and the bilingual search depends on
it. A Latin term next to such text matches too (iPhone in 用iPhone拍).

The check runs per automaton match, so it costs nothing on documents without one, and scan speed
is unchanged. With it, the Hermione Granger search found 25 documents that really mention the
names instead of 100 noise hits, and "trumpet" went from 1,304 matched documents to 256.

**The tradeoff:** inflections no longer match their base term ("trumpeted" isn't "trumpet"). Only
forms that are concept terms of their own count, and concepts usually include the common ones.

### Scoring follows the paper

Each concept contributes its top 100 terms by default (10–1000). One concept scores a chunk by the
sum of the weights of the distinct concept terms it contains (§5.4.1), and several concepts
combine with the geometric mean `(Π (s_c + ε))^(1/m)` with ε = 1e-6 (§5.4.2), so a chunk has to be
relevant to every root. A document's score is its best chunk's. Overlapping matches all count
("Hermione", "Granger", "Hermione Granger"). Counting repeated terms, and a hard "every concept"
filter, are possible options but not implemented.

### Repeated chunks are stored once

Syndicated news prints the same paragraph in many articles, and the copies filled the top results.
The stored hits keep each distinct chunk text's best hit; the full hits file under
`data/searches/` keeps every copy.

### Weak results are flagged

A concept's long tail of weak terms ("said", "year") matches almost any chunk, so a corpus that
never mentions the subject still returns a full page of hits. The results page names each concept
for which no hit is a strong match: one that has the chosen term, or at least two of the concept's
terms in separate places. Nested matches count once, since "Cuarón" inside "Alfonso Cuarón" first
made the Hermione search look strong.

## Engineering choices

### Concepts are built once and shared

A concept is cached under `(model, root, params hash)`. The hash is the SHA-256 of the canonical
JSON of every parameter that changes the result, with defaults filled in first (so `{root: "cat"}`
and `{root: "cat", threshold: 6.0}` are the same concept), plus a `CONCEPT_VERSION` bumped whenever
the concept math changes. Model ids are never reused, so a rebuilt model can't serve stale
concepts.

- Concurrent requests for the same concept share one job and one progress stream: a single
  `INSERT … ON CONFLICT DO NOTHING` against a partial unique index over active jobs decides the
  winner, and the worker checks the cache again when it starts.
- Re-scoring reuses the walk. The walk depends only on the model, the root, and λ; the trim ratio,
  z threshold, root weight, and stored-term count only score it. Changing a scoring setting reuses
  the saved v and skips the minutes-long walk.
- Q isn't a request parameter: a root in the largest component always uses the model's 50
  precomputed columns, so a Q in the request would change the cache key without changing the
  concept.
- Failures and timeouts aren't cached.

### Model artifacts

T keeps only its top-t entries per row, compactly, so it is much smaller to load and multiply than
S. S is written only for tests and inspection (`--no-save-s` skips it). Builds are staged and
checksummed in `manifest.json`, so an interrupted build resumes at its first unfinished stage, and
the parse writes parts, so it resumes too.

### The stack

- **The API is stateless.** Concept tables and search hits live in Postgres, so the API never reads
  `data/`. The worker is the only writer of concepts and searches, and the `msr` CLI shares its
  files on disk.
- **Two queues.** Concept walks and corpus scans run on separate workers, so neither waits behind
  the other, and a search never loads a model.
- **RabbitMQ is the broker; Redis holds only progress.** Progress is a Redis stream per job,
  relayed as Server-Sent Events, so a reconnecting page replays it. Postgres is the source of
  truth for a job's status and attempts: a killed worker's job is redelivered and fails for good
  after three attempts.
- **Raw SQL, no ORM.** Migrations are plain SQL files that never change once applied, and each
  service logs in as its own Postgres role with only the privileges it needs.
- **The UI calls only its own BFF.** Next.js route handlers call FastAPI inside the stack and
  validate every response with Zod schemas generated from the API's OpenAPI schema; CI fails if
  the generated files are stale.

## Open questions

- **The root's weight scale:** the paper's w_r, the self-distance of 0, or a clipped version,
  compared on search results and on the spread of w_r across roots.
- **Reference nodes:** which strategy and Q, studied against the exact X on a reduced model, with
  real models at λ = 1000.
- **The absorbing hitting time** as an option, to see whether it changes rankings on real data.
