# Vector DB & Agent Notes

Design decisions for ingesting this corpus into the same vector DB as
`../rag-theology-resources`. The shared metadata contract, tradition/genre
vocabularies, and retrieval model live in that repo's `RAG-NOTES.md` —
this file records this repo's layout, the chunk payload the ingest layer
must emit, and the deltas specific to quotes/illustrations. Update both
files when the shared contract changes.

## Layout — two content tracks

```
docs/
  illustrations/      # converted books & anthologies — prose (.txt → .md)
  quotes/             # rendered quotation collections (JSONL → .md)
sources/
  *.txt               # raw anthology/book texts
  quotes/*.jsonl      # canonical normalized quote records (datasets, APIs)
tools/                # ported sibling tools + import_dataset.py
```

The directory split is load-bearing: **`form` is derived from the doc's
path at ingest** (`docs/quotes/` → `form: "quotation"`,
`docs/illustrations/` → `form: "anecdote"`). `form` distinguishes "give me
a quotable line" from "give me a story" — a real retrieval axis genre
can't carry, since both are `genre: "illustration"`.

## Doc metadata contract

```yaml
---
title: "..."
author: "..."            # compiler/editor for anthologies; dataset name
                         # for rendered quote collections
tradition: "..."         # single value — shared vocab, see sibling repo
genre: "illustration"    # default for this repo
arrangement: "topic"     # topic | author | scripture | none
covers: ["Ps"]           # only when arrangement: scripture
source: "..."
---
```

`tradition`, `genre`, `covers`, and the OSIS-heading conventions are
identical to theology-resources. `arrangement` is new: it declares what
`###` headings mean so ingest and retagging tools don't have to guess.

## Chunk payload contract

Whatever the feeder (markdown splitter on `docs/`, or a future direct
JSONL adapter), every chunk must carry:

| field | source | notes |
|---|---|---|
| `text` | chunk body | |
| `title`, `author` | frontmatter | provenance in context headers |
| `tradition` | frontmatter | filter gate — see inclusion rule below |
| `genre` | frontmatter | `illustration` for nearly everything here |
| `form` | **path-derived** | `quotation` (docs/quotes/) \| `anecdote` (docs/illustrations/) |
| `themes` | inline `[themes:]` tokens + `###` heading | **array**, multi-label — see below |
| `scripture_refs` | OSIS headings + per-entry tags | same parse as commentaries |
| `source` | frontmatter | |

Context header at ingest: `[<author> | <title> | <heading>]` — same as
sibling repo so unfiltered results show provenance.

## Required splitter features (pipeline-side deltas)

The header-aware splitter needs three things this repo relies on:

1. **Recurse `docs/**/*.md`** — the sibling's `docs/` is flat; this
   repo's is not.
2. **Derive `form` from the path** as above.
3. **Parse `[themes: a, b]` inline tokens** into a `themes` string
   array on the chunk. Token sits at the end of an entry after the
   attribution; lowercase, comma-separated. Entries without one get
   `themes: [<primary heading>]` — the heading IS the primary theme for
   `arrangement: topic` docs.

## Themes — multi-label by design

`tradition`/`genre` stay single-value (identity: "what IS this work?").
`themes` is **descriptive** — a quote about forgiving your enemy is
about forgiveness *and* justice *and* love, and multi-label costs no
precision because theme filters are opt-in `contains` checks, never
identity gates.

- Heading = primary theme (grouping, display, context header)
- `[themes: ...]` = full multi-label set → `payload.themes`
- Filters: `themes contains "justice"` (inclusion, never exclusion)
- Opt-in only, per the sibling's filtering posture: tag coverage is
  uneven across datasets — a theme-filtered query that returns thin
  results should fall back to unfiltered semantic search, which finds
  multi-theme material regardless of tags.
- No canonical theme taxonomy. Themes take the source's own vocabulary;
  embeddings handle synonymy. If a hard-filter taxonomy is ever needed,
  maintain the mapping pipeline-side (like the tradition inclusion
  lists), not by re-tagging the corpus.

## Tradition on compiled & imported works

Anthologies take the **compiler's** tradition (tag the work's editorial
frame, not the quoted authors' — same rule as the sibling repo).
Non-confessional compilations and **all dataset/API-imported quote
collections get `other`** — they have no theological frame to gate on.

Consequence the pipeline must implement: **client filter lists for
`genre: "illustration"` queries include `other`.** The sibling's
FILTERS map doesn't list it (nothing was tagged `other` there but one
SDA work). Quotes are raw material — the preacher applies the
theological lens — so for illustration-genre retrieval, widening
inclusion to `other` is the intended default. Tune per client.

## JSONL record schema (`sources/quotes/`)

Canonical form for imported quote records — normalized and deduped here,
before markdown render:

```json
{
  "id": "q_<hash8>",
  "text": "...",
  "author": "Martin Luther King Jr.",
  "themes": ["forgiveness", "justice", "love"],
  "source": {"dataset": "quotable", "work": "Strength to Love", "year": 1963},
  "scripture_refs": ["Matt 5:44"]
}
```

- `id`: hash of normalized text (lowercase, punctuation stripped) —
  dedup across datasets happens on this key.
- `themes`: full multi-label set from the source dataset; may be empty.
- `scripture_refs`: optional; datasets rarely tag it. An enrichment
  pass (manual or model-assisted) can populate it — worth doing for
  quotes that are sermonic commonplaces.
- Attribution honesty: dataset quotes are frequently misattributed.
  Where the source flags disputed attribution, carry it in the record
  (e.g. `"author": "Martin Luther King Jr. (attributed)"`) rather than
  laundering it into certainty at render time.

`docs/quotes/*.md` files are **generated artifacts** — never hand-edit;
re-render from JSONL so dedup/merge changes propagate.

## Retrieval recipes

| intent | filter |
|---|---|
| quote on a theme | `genre: "illustration"`, `form: "quotation"`, semantic query (+ opt-in `themes contains`) |
| story/anecdote on a theme | `genre: "illustration"`, `form: "anecdote"`, semantic query |
| anything illustrative | `genre: "illustration"`, unfiltered by form/themes |
| quotes on a text | `genre: "illustration"` + `scripture_refs intersects <ref>` |

Genre stays opt-in (sibling posture): default queries across the unified
DB run unfiltered by genre, tradition inclusion lists always apply —
with `other` added on the illustration path per above.

## Corpus distribution

(as of 2026-10-10)

| doc | track | tradition | entries |
|---|---|---|---|
| docs/quotes/apuritansmind-puritan-quotes.md | quotation | reformed | 156 |

(mirror the sibling's tradition/genre tables as the corpus grows —
remember `tools/build_catalog.py` needs `illustration` added to GENRES
when ported)

## Open items

- `tools/import_dataset.py` (dataset/API → JSONL → render) — not yet
  built; first candidate sources: Wikiquote dump (best attribution
  quality), then Goodreads-derived sets (heavy dedup needed).
- Splitter feature request: `[themes:]` token parse + recursive glob +
  path-derived `form` (see above).
- Client filter lists: add `other` to the illustration-genre path.
- Theme enrichment pass for anthology entries — optional, apply
  `[themes:]` only where clearly warranted.
