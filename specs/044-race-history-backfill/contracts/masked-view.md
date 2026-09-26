# Contract — Masked layout view (amendment 2026-09-26 · FR-046 · SC-013)

The masked view is the only content of an official results file that the LLM reads. `mask` produces it locally and deterministically; no rider name, club, city, number or time survives in it. Research: R-17.

## Producer

`python -m scripts.race_results mask --file <path outside the repository>` (see `results-skill-cli.md`). The engine lives in `app/services/race/results_skill/masking.py` and exposes:

```python
def build_masked_view(file_bytes: bytes, results_ext: Literal["pdf", "csv"]) -> MaskedView
def render_masked_view(view: MaskedView) -> str          # the text written to masked/view.txt
def leak_count(rendered: str, document: ParsedResults) -> int   # R-17 leak check (used by apply)
```

The functions are pure: no database, no network, no logging of content.

## Token classes

Tokens glued across a letter/digit boundary are split before they are classified (`CLUB1:23:45` becomes `CLUB` + `1:23:45`).

| Class | Recognised by | Rendered in a structural line | Rendered in a content line |
|---|---|---|---|
| `WORD` | contains a letter | verbatim (every word is in the vocabulary, by definition) | `⟨W⟩` |
| `INT` | digits only | verbatim if ≤ 4 digits (a line with a longer one is not structural) | `⟨N{k}⟩` (k = digit count) |
| `TIME` | `h:mm:ss`, `mm:ss`, and the variants accepted by `normalizer.parse_time` | not structural | `⟨T {shape}⟩` (e.g. `⟨T h:mm:ss⟩`) |
| `STATUS` | `DNF`, `DNS`, `DSQ`, `DQ`, and lap deficits matched with `normalizer.LAP_WORD_PATTERN` | not structural | verbatim, normalised to upper case |
| `PUNCT` | anything else | verbatim | verbatim |

**Structural line**: a line with no `TIME`, no `STATUS`, no `INT` of five or more digits, and every `WORD` in the vocabulary. **Content line**: any other line.

## Vocabulary

`app/services/race/results_skill/vocabulary.py` builds the vocabulary as a frozen set of upper-case, accent-folded words:

- every word of every key of `normalizer.HEADER_TO_CODE`, plus `CAT`;
- column titles: `POS`, `POSICION`, `PUESTO`, `DORSAL`, `NUMERO`, `NO`, `NOMBRE`, `NOMBRES`, `APELLIDO`, `APELLIDOS`, `DEPORTISTA`, `CORREDOR`, `CLUB`, `EQUIPO`, `PATROCINADOR`, `CIUDAD`, `MUNICIPIO`, `TIEMPO`, `DIFERENCIA`, `DIF`, `VUELTAS`, `PUNTOS`, `PTS`, `CATEGORIA`, `EDAD`;
- document words: `RESULTADOS`, `VALIDA`, `COPA`, `CAMPEONATO`, `CLASIFICACION`, `OFICIAL`, `OFICIALES`;
- roman numerals `I` through `XII`;
- connectors: `DE`, `DEL`, `LA`, `LAS`, `LOS`, `Y`, `EN`.

Pinned by tests:
- no month or weekday name;
- no word longer than 14 letters;
- only `[A-Z0-9]` after accent folding;
- no entry outside the classes above.

Adding a word requires a pull request touched by the `data-privacy-guard` review. The skill may propose a word only when the operator has read it on the printed file and confirms that it is a category or column word, never part of a person's name.

## Output format (`masked/view.txt`)

```text
# masked-view v1 · format=pdf · pages=6 · sha256=3f9a1c2e
## page 1 · width=595.3 · rulings_x=[50.7, 76.8, 109.9, 257.4, 327.6, 466.0, 539.0, 580.2]
L001 y=62.4  S | @210.3 RESULTADOS VALIDA III
L004 y=101.8 S | @52.0 CAT: PREJUVENIL A DAMAS
L005 y=118.0 S | @52.1 POS | @78.0 DORSAL | @112.0 NOMBRE | @259.5 CIUDAD | @329.7 CLUB | @468.3 TIEMPO | @541.1 PUNTOS
L006 y=131.2 C | @63.7 ⟨N1⟩ | @91.2 ⟨N3⟩ | @112.0 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @259.5 ⟨W⟩ | @329.7 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @468.3 ⟨T h:mm:ss⟩ | @541.1 ⟨N3⟩
L007 y=143.9 C | @63.7 ⟨N1⟩ | @91.2 ⟨N3⟩ | @112.0 ⟨W⟩ ⟨W⟩ | @259.5 ⟨W⟩ ⟨W⟩ | @329.7 ⟨W⟩ ⟨W⟩⟨N1⟩ | @468.3 (-1 VUELTA) | @541.1 ⟨N2⟩
```

- `S` marks a structural line and `C` a content line.
- `@x` is the start x of a run, in PDF points. Runs are segmented by the same function the apply engine uses (`results_skill/pdf_runs.py`, R-19), so the geometry the LLM reasons about is exactly what the engine will apply.
- `sha256=` shows the first 8 hex characters of the file hash, only to tie the view to its run.
- Delimited text uses `R0001 S | [0] POS | [1] DORSAL | …` for the header and `R0002 C | [0] ⟨N1⟩ | [1] ⟨N3⟩ | …` for data rows. No geometry is shown.

`masked/summary.json` holds counts only: pages or rows, structural and content lines, lines per page, and the number of runs per content line (a histogram).

## Leak check (SC-013)

`apply` runs the leak check after extracting the real rows:

1. For every extracted row, split `name`, `club` and `city` into accent-folded words of three or more letters.
2. Count how many of those words appear as a verbatim token of a structural line in `masked/view.txt`. A content line cannot contain one by construction; a test pins that too.
3. Print only the count. If the count is greater than 0, exit with code 3. The run is then unusable, and the operator follows `runbook-ops.md` §3.5 (PII leak detected).

## Refusals

| Case | Exit | Message (Spanish, printed by the CLI) |
|---|---|---|
| File inside the repository | 2 | `El archivo debe estar fuera del repositorio.` |
| Not a PDF (magic bytes) and not UTF-8 delimited text | 2 | `Formato no admitido: se espera PDF con texto o CSV/TSV en UTF-8.` |
| PDF without a text layer (scanned) | 4 | `El PDF no tiene capa de texto (¿escaneado?). No se puede enmascarar.` |
| More than 8 MB | 2 | `El archivo supera 8 MB.` |

## Tests

`backend/tests/services/race/results_skill/test_masking.py`:
- Builder PDFs (historical overprint layout, 2026 layout, an unruled fictional layout) and synthetic CSVs: no fake name, club or city word appears anywhere in the view, and no bib, time or points value appears as a token of a content line. The line labels, `y=` and `@x` geometry are not values.
- A Hypothesis property over generated rows, including names equal to vocabulary words (`ELITE`, `MASTER`, `DAMAS`, `A`): content lines never reveal a word.
- A synthetic continuation line made only of vocabulary words is shown verbatim, and `leak_count` reports it.
- Structural detection: column titles and category headers are verbatim; a header containing an unknown word renders as content.
- Glued tokens split; lap-deficit variants from T024b stay verbatim; month names are masked.
- Vocabulary pins (above).
- Determinism: the same bytes always give the same view.
