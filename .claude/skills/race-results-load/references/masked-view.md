# Reading `masked/view.txt`

Full format spec: `specs/044-race-history-backfill/contracts/masked-view.md`. This page is the practical companion — what you can actually get out of a run's masked view when you have it open, and, just as important, what it never gives you, no matter how hard you look.

## What the file always is

```text
# masked-view v1 · format=pdf · sha256=e80541d6
## page 1 · width=612.0 · rulings_x=[40.4, 542.9]
L001 C | @0.0 ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨N2⟩ ⟨W⟩ ⟨N4⟩
L002 S | @0.0 ⟨W⟩ : ⟨W⟩ ⟨W⟩
L003 y=70.3 C | @43.0 ⟨W⟩ | @65.5 ⟨W⟩ ° | @95.5 ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ | @365.5 ⟨W⟩ / ⟨W⟩ | @440.5 ⟨W⟩ | @508.0 ⟨W⟩
L004 y=84.0 C | @43.0 ⟨N1⟩ | @65.5 ⟨N3⟩ | @95.5 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ ⟨W⟩ | @365.5 ⟨W⟩ ⟨W⟩ | @440.5 ⟨T h:mm:ss⟩ | @508.0 ⟨N2⟩
```
(a real capture, from a synthetic builder file — see `reading-profile.md` for how it was made.)

- The header line names the format and the first 8 hex characters of the file's SHA-256 — that ties the view to a run, it is not a value about anyone.
- Each page opens with its width and `rulings_x` — the x positions `find_tables` measured. That is column geometry, safe to reason about.
- Each content/structural line has a label (`L001`, …), an optional `y=` (PDF vertical position; absent for delimited text and for lines read outside any table band), a kind marker (`S` structural, `C` content), and one or more runs.
- A run is `@<x> <tokens>` for PDF (x is the run's start position in points) or `[<column index>] <tokens>` for delimited text.

## Token classes you will actually see

| Token | Means | Ever a real value? |
|---|---|---|
| `⟨W⟩` | one word (letters only, after splitting glued digits) | Never. **This is true even on a structural (`S`) line and even for a word that is a known vocabulary word** — see "What `S` does and does not tell you" below. |
| `⟨N{k}⟩` | a run of `k` digits | Never — you only ever learn the digit count, not the value, whether it is a bib, a position, a points total or part of a date. |
| `⟨T h:mm:ss⟩` / `⟨T mm:ss⟩` | a finish time | Never the actual time — only its shape. |
| `DNF` / `DNS` / `DSQ` / `DQ` | a status | Shown **verbatim**, upper-cased. These are a closed, non-identifying set — never a person, so there is nothing to mask. |
| a lap-deficit marker (e.g. `-1 VUELTA`) | a lap deficit | Shown **verbatim** — same reasoning as status. |
| `:`, `°`, `/`, `-`, `(`, `)`, … | punctuation | Shown verbatim — it carries no identity. |

## What `S` (structural) actually tells you — and does not

A line is marked `S` when, by the contract's own rule, every word on it is a vocabulary word and it has no time, status, or 5+-digit number. In practice, in this engine, **that is the only thing the `S` marker tells you.** The rendered tokens on an `S` line are exactly the same masked forms (`⟨W⟩`, `⟨N{k}⟩`) as on a `C` line — the word tokens are not switched back to real text. So:

- `S` on a category-header line (`L002` above, which is really `CAT: PREJUVENIL A`) tells you *this text is entirely made of vocabulary words — safe, known* — not *what* those words are.
- `S` on a column-title line tells you the same: it is a title row, built from known column words, but you cannot read which columns from the view alone.
- A `C` line containing an unrecognised word (e.g. `L003` above, the builder's own column-title row, which fails structural because `N°` isn't a full vocabulary match) tells you a header word is unknown — not what it says.

**Do not ask the operator to confirm a word "because the view says `S`"** — the view never shows you the word to confirm in the first place. The only path to a real word is: `apply`'s stdout names an unrecognised category by index and row count (never its text); you tell the operator "category #k, N rows, is unrecognised — what does the printed header say?"; they read the printed file themselves and answer; if it is a category or column word, it becomes an entry in `category_aliases` (`reading-profile.md`) or a vocabulary pull request. You never derive the word from `view.txt` yourself.

## What you *can* derive, reliably, from the view

- **Column boundaries**: collect the `@x` start positions of runs across several data (`C`) lines in the same table and cluster them — that is exactly how `columns[].x_from`/`x_to` in a profile are chosen (see the worked example in `reading-profile.md`). This is geometry, not content.
- **Row shape per column**: how many `⟨W⟩` tokens a column's runs typically carry (e.g. 2–3 for a name column, 1–3 for a city or club column) — useful to sanity-check that a column boundary is in the right place, without ever reading a name.
- **Presence of a category header line**: an `S` line by itself, positioned before a run of data lines, tells you a new category starts there — you don't need its text to place `category_header` in the profile (a `{"prefix": "CAT:"}` pattern works without ever knowing which categories follow).
- **Table vs. free layout**: `rulings_x` present and table row bands used (`pdf.rows: "table_bands"`) vs. a page with no rulings, one line per text baseline (`pdf.rows: "baselines"`).
- **Delimited text row shape**: `[<index>] ⟨tokens⟩` runs tell you column count and which columns hold names/times/status, by shape alone.

## What you can never conclude, ever

- The actual text of a name, city, club, or category header/column title, no matter its length, position, or the line's `S`/`C` marking.
- A bib, position, points, or any other number's value — only its digit count.
- A finish time's value — only its shape.
- Anything from `masked/summary.json` beyond the counts it documents (pages/rows, structural/content line counts, lines per page, a run-count histogram).

## If you are tempted to "just check" the real file

Don't. Rule 2 is absolute: never open the official file with Read, `cat`, `pdftotext`, a Python one-liner, or anything else — even "just to confirm a header". If you genuinely need a word, it comes from the operator reading the printed file, in the same turn, never from you touching the source.
