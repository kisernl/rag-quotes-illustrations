---
name: txt-to-md-rag
description: Convert plain-text source works (quote, anecdote, and sermon-illustration collections) in this repo to RAG-optimized Markdown, using the corpus conventions shared with rag-theology-resources
argument-hint: "<source .txt file>"
allowed-tools:
  - read
  - write
  - edit
  - exec
  - grep
  - glob
---

# Text → Markdown conversion for the RAG pipeline (quotes & illustrations)

This repo is the quotes/illustrations content store for the same RAG
pipeline / vector DB as `../rag-theology-resources`. The corpus contract
is shared: same frontmatter fields, same markdown conventions — so
header-aware splitters and contextual chunking behave identically across
both repos. This file restates the shared conventions and records the
decisions specific to quote, anecdote, and illustration collections.

Where a convention is restated, the theology-resources version
(`rag-theology-resources/RAG-NOTES.md` and its own `txt-to-md-rag`
skill) is authoritative; if the two ever disagree, fix the drift in both
places rather than letting the repos diverge.

The repo has two content tracks:

- `docs/illustrations/` — prose: converted books, anthologies, anecdote
  and illustration collections (the classic `.txt` → `.md` path)
- `docs/quotes/` — rendered quotation collections, generated from
  normalized dataset records (`sources/quotes/*.jsonl` → render →
  `.md`; see rule 13)

## Output conventions

1. **File**: converted works → `docs/illustrations/<author>-<title-
   slug>.md`; rendered quote collections → `docs/quotes/<source-or-
   compiler>-<theme-or-slug>.md`. Author surname first, no possessives;
   for anthologies, `<author>` is the *compiler/editor*
   (`spurgeon-feathers-for-arrows`, `ballou-edge-tools-of-speech`).
   **The directory is meaningful**: at ingest, `form` is derived from
   the path (`docs/quotes/` → `quotation`, `docs/illustrations/` →
   `anecdote`) — no frontmatter field needed. Sources live in
   `sources/` under the same slug; rename misplaced or misspelled
   source files to match, and keep them — they are needed for
   re-conversion and verification.

2. **YAML front matter** at the very top:

   ```yaml
   ---
   title: "..."
   author: "..."            # compiler/editor for anthologies
   tradition: "..."         # required — shared vocabulary below
   genre: "illustration"    # required — see below
   arrangement: "topic"     # required — topic | author | scripture | none
   covers: ["Ps", "Prov"]   # only when arrangement: scripture (rule 10)
   translator: "..."        # if applicable
   edition: "..."           # if applicable
   source: "<gutenberg URL or other origin>"
   ---
   ```

   **`tradition`** uses the identical controlled vocabulary as
   theology-resources — the same client-side inclusion filters must work
   across both repos:

   - `early-church` — pre-schism patristic (roughly pre-1054)
   - `medieval` — medieval Latin West, pre-Reformation
   - `catholic` — Roman Catholic
   - `orthodox` — Eastern Orthodox
   - `anglican` — Church of England / Anglican communion
   - `lutheran`
   - `reformed` — Reformed, Presbyterian, Puritan
   - `reformed-baptist` — Calvinistic/Particular Baptist
   - `baptist` — other Baptist
   - `congregationalist`
   - `arminian` — Arminian/Remonstrant (non-Wesleyan)
   - `methodist` — Wesleyan/Methodist/Holiness
   - `anabaptist`
   - `dispensationalist`
   - `restorationist` — Stone-Campbell / Disciples of Christ /
     Churches of Christ
   - `liberal-protestant`
   - `evangelical` — broad evangelical, when nothing else fits
   - `other`

   `early-church` and `medieval` remain shared-heritage era labels.
   Tagging rules carried over for this corpus:

   - **Anthologies take the compiler's tradition, not the quoted
     authors'.** Selection, arrangement, and editorial frame are the
     work's theology — the same "tag the work, not the biography" rule
     as theology-resources. A Baptist's anthology of patristic quotes is
     `baptist`; Upham's Fénelon anthology would be `catholic` only if
     the work presents Fénelon's theology as its own content.
   - Non-confessional compilations (secular quotation dictionaries,
     generic wit-and-wisdom books) → `other`. **Dataset/API-imported
     quote collections likewise → `other`** — they have no editorial
     theological frame; client filter lists for `genre: "illustration"`
     queries are expected to include `other` (see RAG-NOTES.md).
   - `other` does NOT mean low-value — it means "no theological
     frame to gate on." The quote is raw material; the preacher applies
     the lens.

   **`genre`** (same vocabulary as theology-resources; the values
   relevant here):

   - `illustration` — **default for this repo**: sermon illustration
     collections, anecdote books, pulpit quotation anthologies, and
     poetry-for-illustration collections. They share one pulpit
     function, and the retrieval layer addresses them with a single
     `genre: "illustration"` filter — do not split them into finer
     genres. The *quotation vs. story* distinction is carried by
     `form` (path-derived, rule 1), not genre.
   - `reference` — only for works with no homiletic purpose (a general
     quotation dictionary not aimed at preachers).
   - `biography` / `sermon` — narrative lives, actual sermon
     collections, in the rare case one lands here.

   **`arrangement`**: how the work groups its entries. It tells the
   ingest layer what `###` headings mean and which retrieval axis the
   work offers:

   - `topic` — entries grouped under subjects (Faith, Prayer,
     Affliction). The most common shape for illustration books, and the
     default for rendered quote collections (one `###` per theme).
   - `author` — entries grouped under the quoted author.
   - `scripture` — entries grouped under Bible passages (e.g.
     Bible-illustrator-style works). Apply the commentary convention:
     `covers` in front matter + OSIS headings (rule 10).
   - `none` — flat or miscellaneous ordering; topic/source labels live
     inline on each entry instead of in headings.

3. **Title block / Contents**: `#` title, compiler line in italics,
   edition/imprint lines in italics, then a `>` blockquote source
   attribution. Under `## Contents`, reproduce the book's own TOC or
   index of topics as a nested bullet list — for topic-arranged works
   this list doubles as the work's subject coverage map. Drop Gutenberg
   license boilerplate, `[Cover Art]`/transcriber notes, and
   back-of-book alphabetical indexes (navigation aids; the headings
   already carry the retrieval signal). If the source's only
   organization is a front index, reproduce that.

4. **Headings are the retrieval skeleton.** A query like "find an
   illustration about prayer" resolves through the chunk context
   headers, so grouping headings must be clean and consistent:

   - `##` — major divisions (parts, alphabetic letter groups, sections).
   - `###` — the entry group: `### Prayer` for topics; `### Spurgeon,
     C. H.` for author-arranged works; `### Rom 8:28` for
     scripture-arranged works. Use the book's own topic wording in title
     case — do NOT invent a canonical taxonomy; embedding similarity
     handles synonyms at retrieval time.
   - `####` — the book's own numbered sub-divisions, if any.

5. **Entries are the atomic chunk unit.** One illustration, quote, or
   anecdote per paragraph, exactly as the book divides them:

   - Preserve the book's entry numbers, bolded — `**1.**`, `**42.**`.
     Same role as section enumerals in theology-resources: citation
     anchors and preferred chunk boundaries.
   - NEVER strip per-entry attributions into a separate list. Keep the
     printed form attached to the entry (`— Longfellow`, `— Talmage`,
     `(From the French)`) — it is the provenance an agent cites in its
     answer.
   - Keep an entry's application or moral ("This illustrates...") in the
     SAME paragraph as the story — splitting them orphans the point.
   - Poetry quoted inside an entry keeps line-per-line verse format
     with two-trailing-space hard breaks; a whole poem that IS the entry
     is formatted the same way.
   - **Multi-theme entries get an inline tag**: when a quote or entry
     belongs to more than one theme, append ` [themes: a, b, c]` at the
     end of the entry, after the attribution. The `###` heading carries
     the primary theme; the token carries the full set. At ingest it is
     parsed into the chunk's `themes` payload array — filters use
     `themes contains X`, so the entry surfaces under every listed
     theme, not just its heading. Optional per entry; lowercase,
     comma-separated. Single-theme entries need nothing — the heading
     already covers them. For dataset quotes, the full theme list comes
     from the JSONL record; for anthology conversions it is an
     enrichment step (manual or model-assisted), applied only where
     clearly warranted.

     ```markdown
     **17.** Darkness cannot drive out darkness; only light can do
     that. Hate cannot drive out hate; only love can do that.
     — Martin Luther King Jr. [themes: forgiveness, justice, love]
     ```

6. **Paragraphs**: join hard-wrapped lines into one line per paragraph.
   Line-ending hyphen (`-` or `‐` U+2010) → join next line WITHOUT a
   space; otherwise join with a single space.

7. **Inline emphasis**: Gutenberg `_underscores_` are valid markdown
   italics — preserve them.

8. **Footnotes — INLINE, never a trailing section**: replace each
   in-text marker `(N)` with ` [fn. N: <footnote text>]` at the point of
   reference. Parse the footnote list first, then substitute. The `fn.`
   prefix distinguishes them from the author's own `[bracketed]`
   interpolations.

9. **Typography**: preserve Unicode as-is (curly quotes, `‐`, æ/œ,
   Greek). Do not silently "fix" apparent source typos.

10. **Scripture references**: normalize to OSIS only where the pipeline
    parses them — `covers` and heading text on `arrangement: scripture`
    works (`### Gen 3 — The Fall`, `### Ps 23`), plus per-entry
    `scripture_refs` on quote records where known. Inside entry text,
    keep the book's own citation form ("Ps. xxiii", "Romans viii. 28")
    — the text stays faithful; embedding similarity does the rest.

11. **Topic + author works**: where an anthology prints both a topic
    grouping and a quoted-author per entry, the topic is the heading and
    the author stays as the entry's inline attribution — do not
    double-tag.

12. **Themes are descriptive, not identity** — which is why they get to
    be multi-label when `tradition`/`genre` do not. A quote genuinely
    is about forgiveness *and* justice simultaneously; multi-tagging
    them costs no precision because theme filters are opt-in
    `contains` checks, never identity gates. Do NOT collapse a
    multi-theme quote's secondary tags just because its heading can
    only hold one.

13. **Dataset/API quote pipeline**: bulk quote sources (Quotable,
    Wikiquote dumps, Goodreads-derived sets) are normalized into JSONL
    records under `sources/quotes/` FIRST — dedup via a hash of
    normalized text (lowercase, punctuation stripped) happens at this
    stage, not in markdown. Each record:

    ```json
    {"id": "q_a1b2c3", "text": "...", "author": "Martin Luther King Jr.",
     "themes": ["forgiveness", "justice", "love"],
     "source": {"dataset": "quotable", "work": "Strength to Love",
                "year": 1963},
     "scripture_refs": ["Matt 5:44"]}
    ```

    (`scripture_refs` is optional — datasets rarely tag scripture; an
    enrichment pass can add it.) The records then render to
    `docs/quotes/*.md`: primary theme → `###` heading, full set →
    `[themes:]` inline, attribution → `— Author`. Rendered markdown is
    the ingest artifact; JSONL is the canonical record — never edit
    `docs/quotes/*.md` by hand, re-render instead.

14. **Tools note**: when conversion/tagging tooling is needed, port the
    sibling repo's `tools/` scripts (`fetch_ccel.py`, `convert_ccel.py`,
    `tag_frontmatter.py`, `normalize_headings.py`,
    `build_catalog.py`) rather than writing one-off converters — and add
    `illustration` to `build_catalog.py`'s GENRES/TITLES maps when
    porting it (the sibling list predates this genre being populated).
    The dataset importer (`tools/import_dataset.py`: source → JSONL →
    render) is new tooling for this repo.

15. **Bookkeeping — always re-tally**: after adding, converting, or
    re-rendering any doc, run `python3 tools/update_counts.py` to
    regenerate `COUNTS.md`. It tallies entries by track (`docs/quotes/`
    vs. `docs/illustrations/`) split religious (`tradition` ≠ `other`)
    vs. secular (`tradition: "other"`) — so a doc's `tradition` tag
    directly controls which column it lands in. Never hand-edit
    `COUNTS.md`.

## Verification checklist (always run)

- Frontmatter present: `tradition`, `genre`, `arrangement` each a single
  controlled value; `covers` present iff `arrangement: scripture`; file
  is under the correct `docs/` subdirectory for its `form`.
- Every footnote marker inlined: zero remaining `\(\d+\)` or dangling
  `\[N\]` refs; count of `[fn. N:` equals count of parsed definitions;
  numbering sequential.
- No stray `](` that could form a link (excluding intentional links and
  `[themes: ...]` tags).
- `[themes: ...]` tags well-formed: lowercase, comma-separated, parse as
  an array; primary theme matches the enclosing `###` heading.
- Entry count parity: count of bolded entry enumerals ≈ count of items
  in the source's index/TOC — no dropped or merged entries.
- Every entry retains its printed attribution (or deliberately has none
  where the source prints none).
- Heading groups match the book's index, in order, none skipped;
  scripture-arranged works show OSIS headings.
- Word count of converted body ≈ source body (± markup tokens) — no lost
  content.
- Spot-check: a topic-group boundary, the longest entry, a poetic
  excerpt, hyphen-joined words, a `[themes:]` multi-tag entry.
- `COUNTS.md` regenerated (`python3 tools/update_counts.py`) and the
  new doc's entries appear under the right track and leaning.
