# Implementation Plan: Race history backfill — Copa Valle 2024 and 2025 with cross-season athlete progression

**Branch**: `main` (owner decision: no dedicated branch for specification and planning) | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/044-race-history-backfill/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

> **Amendment 2026-09-26 — skill-only results loading.** The sections that follow describe the feature as implemented (2026-09-18…22). The amendment that removes every results upload and loads results only through the results skill is planned in [Amendment 2026-09-26](#amendment-2026-09-26--skill-only-results-loading) at the end of this file. Where the two disagree, the amendment wins.

## Summary

Load the fifteen historical válidas (2024: 7, 2025: 8) with the **full start list**, through the existing import path, and give each club athlete **one continuous progression across 2024–2026** that stays truthful when the athlete changes category. Planning research on three real files (inspected outside the repository, counts only) changed two premises of the spec and produced one validated design:

- **Rows are lost to overprinting, not wrapping**: a long club name overflows its column and is printed over the time; x-sorted text extraction interleaves letters and digits and the row regex fails silently. Loss is **16–25 % of every file**. Reading rows *per table-row band in content-stream order* with a relaxed regex recovered **100 %** of rows in the prototype (282/277/280, zero unparsed). The official files also contain real defects (a duplicated ordinal, a missing ordinal), so the audited acknowledgement path is a necessity.
- **Category vocabulary**: 2024 already had four master groups; the two-group masters are 2025 only; both seasons have an undivided pre-infantile girls' group; 2025 mixes `DAMAS` and `FEMENINO` for the same category. Eight season-agnostic aliases plus three inactive season-specific catalogue rows cover every observed header.
- **Most of the analytics already exist**: `field_metrics.compute_field_metrics` (feature 037) computes field size, percentile and gap to the median per season. A thin pure `history.py` reuses it and adds only thresholds, the category-change flag, the frozen label, speed and completion counts — 037's contract is untouched.

Identity moves from "one competitor per normalised name" to **signatures** (`name + club + city`, unique) with a **coach-decided review queue** that gates every commit; the ingestor never merges or splits on its own. A **structural guard** makes cross-válida data impossible for a competitor not linked to a club athlete, enforced by a test that walks the package. Families see the whole history only once a named privacy-policy version is in force. One Alembic revision from `c2314ccd7927`: three columns on `race_results`, unique→index plus `city_text` on `race_competitors`, two new tables. No new runtime dependency on either side.

## Technical Context

**Language/Version**: Python 3.13 (backend, venv `backend/.venv`); TypeScript 5 / React 19 (frontend, Vite)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), Alembic, Pydantic v2, `pdfplumber>=0.11`, `rapidfuzz>=3.14`, `unidecode`, WeasyPrint (test fixture builder only — already a runtime dependency). Frontend: shadcn/ui, Tailwind v4, TanStack Query, RHF + Zod, `recharts ^3.8.1`. **No new runtime dependency.**

**Storage**: MySQL 8.4 (Hostinger in prod). `race_results` +3 nullable columns (backfilled); `race_competitors` unique→index, `+city_text`; new `race_competitor_signatures`, `race_identity_candidates`; three inactive `race_categories` rows and two descriptive `race_points_schemes` rows by seed script; new keys inside `race_imports.parse_meta_json`. Source files stored as today (retention deferred, FR-043).

**Testing**: pytest default lane (aiosqlite; synthetic results-PDF builder on WeasyPrint; band reader also tested on hand-built char dicts; hypothesis for the completeness function and the resolver's idempotence); opt-in `-m mysql` for the unique triple with empty strings, the dropped unique and the frozen columns; structural privacy test for the lock; vitest + Testing Library + MSW; jest-axe zero violations on the card (both audiences), two pages, two dialogs; Playwright `race-history.spec.ts` on the isolated stack. `-m golden` run once to confirm no drift (no AI change).

**Target Platform**: Render free tier (backend, cold start ~50 s), Cloudflare Pages (frontend); coach on tablet, parents on mid-tier Android over 3G.

**Project Type**: Web application (FastAPI backend + React SPA), Spec Kit feature.

**Performance Goals**: `GET …/race-analysis/history` ≤ 4 statements and p95 ≤ 500 ms for ≤ 30 points; parse per file within the existing parse timeout (band reading adds one pass over `page.chars`); `POST /race-identity/rebuild` ≤ 10 s for ≈ 3 000 names, worker thread, 30 s timeout (explicit batch budget in the route docstring); progression chart in a lazy chunk with text-first rendering (LCP ≤ 3.5 s on throttled 3G for the athlete route, ≤ 150 KB gzipped per lazy route).

**Constraints**: minors' privacy (Ley 1581) — several hundred third-party minors enter the database: no name, club or city in logs, traces, AI prompts, newsletters, family responses or committed fixtures; `city` serialised only by the identity-review schemas; cross-válida data structurally impossible for unlinked competitors **before** any real load; legal basis written down; erasure and retention explicitly deferred. 2026 behaviour byte-identical (FR-007, FR-029). Single Alembic head. No new MySQL enum value on an existing column. Product copy in español neutro with diacritics; planning corpus in English. A local backend may point at the production database — the staging script never commits.

**Scale/Scope**: 15 files, ≈ 280 rows and 23–25 categories each → ≈ 4 200 results, ≈ 2 500–3 000 distinct printed names; ~20 club athletes. 1 migration, 2 tables, 4 columns; ~7 new backend modules (band reader inside the parser, completeness, import staging, identity review, identity resolver, third-party guard, history) and ~8 extended (normalizer, ingestor, imports router + schemas, analytics, standings schema, athlete race-analysis router + schemas, seeds, config); 1 new router; 1 script; ~9 new frontend components/pages + api/hooks/types/schemas, 3 surfaces extended; docs in `docs/10-race-results/` plus status/technical-notes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | Pure, separately testable units (`_band_text`, `check_completeness`, `build_candidates`, `IdentityResolver`, `build_history_points`); the router's parse body is extracted into `import_staging.py` so the script and the endpoint share one path (FR-023) instead of duplicating it; `compute_field_metrics` reused rather than re-implemented; closed reason catalogue follows the `RevisionReasonCode` precedent; named constants for every threshold (`MIN_FIELD = 5`, `SAME_PERSON_MIN_SCORE = 90`, `DIVERGENCE_MAX_SCORE = 70`); `ruff` + `tsc --noEmit`. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every contract ends with its tests. Parser: synthetic overprint fixtures + untouched 2026 oracles. Completeness, resolver and history: pure-function suites with boundary cases (4/5 finishers, even median, lapped, DNF, no time). Routers: happy + denied paths for every new route (parent 403, athlete 403, foreign coach). Privacy: structural lock test + name sweep over logs/prompts/newsletter/family output. Concurrency test for the signature unique key. `-m mysql` for the constraint semantics. vitest, jest-axe, Playwright. | PASS |
| III. UX Consistency | Reuses wizard, `Dialog`/`Sheet`, URL-driven state, ≥ 48 px targets, RHF + Zod with inline Spanish errors, designed loading/empty/error states; one neutral series colour, status colours untouched; single-axis chart with a metric toggle; table as the chart's text alternative; caveats always visible; family wording reviewed against "no comparative or discouraging language about a minor". | PASS |
| IV. Performance | History read capped at four statements (asserted) with field rows restricted to the athlete's `(event, category)` pairs — no N+1; identity rebuild off the event loop with a stated budget and blocked comparisons; lazy chart chunk, text first; no change to the 2026 read paths. The rebuild is a batch operation outside the 500 ms read budget — documented in its docstring; if it exceeds 10 s on Render it is recorded in Complexity Tracking, not silently accepted. | PASS |
| V. Youth Psych. Safeguards | Not a psychological instrument. Adjacent rules honoured: results about a minor are shown with field context and mandatory caveats; the family explainer at a category change normalises the expected dip; no ranking of club athletes against each other; relative age and maturation are explicitly *not* applied as corrections (out of scope). | N/A / respected |
| Quality gate — Privacy | Mandatory `data-privacy-guard` audit over the parser changes, staging, identity review, resolver, guard, history endpoint and both UI audiences, recorded in `privacy-audit.md` before the real load. Preliminary verdict (2026-09-18): approved with conditions — lock before load (this plan), legal basis documented (this plan), erasure + retention next feature (FR-043). Fixtures synthetic; sample files were inspected outside the repo and deleted. | PASS |
| Quality gate — Stack discipline | No new dependency; WeasyPrint reused for fixtures; no OCR, no scraping. | PASS |
| Quality gate — Security | New routes behind `require_role([admin, coach])` with club scoping; history behind `verify_athlete_access`; 403 for third-party progression; corrections validated by Pydantic (`extra="forbid"`); upload validation unchanged (size cap, magic bytes); no free text where a closed catalogue suffices. | PASS |
| Quality gate — AI features | No prompt, model or pipeline change. Regression test proves the 2026 analyst context is identical with historical data present; golden eval run once for confirmation. | PASS |
| Quality gate — Observability | Structured events with ids, counts, codes, pages and ordinals only (`race_import_category_blocked`, `race_identity_rebuild`, `race_identity_decided`, `third_party_progression_refused`); `record_audit` on corrections, acknowledgements, decisions and reversals. | PASS |
| Workflow — Branching | Specification and planning on `main` by explicit owner instruction (docs only). Implementation is expected on `feat/044-race-history-backfill` per the project convention unless the owner says otherwise. Conventional Commits, no AI mention. | PASS (noted) |

**Post-design re-check (after Phase 1)**: unchanged. Four spec-level adjustments were made during planning and are recorded in `spec.md` Assumptions: (1) row loss is caused by overprinted columns, not wrapped lines, and affects 16–25 % of each file (R-01); (2) four-group masters already existed in 2024 — the season-specific groups are 2025's `MASTER B/C` and the undivided pre-infantile girls' group of both seasons (R-03); (3) official files do contain duplicated and missing ordinals, and the acknowledgement uses a closed reason catalogue rather than free text (R-05); (4) field size follows feature 037's definition (finishers including lapped riders), with the ≥ 5 threshold applied to field size for the percentile and to timed finishers for the gap to the median (R-08). No Complexity Tracking entry is needed.

## Project Structure

### Documentation (this feature)

```text
specs/044-race-history-backfill/
├── plan.md                          # This file
├── spec.md                          # Feature specification (owner decisions of 2026-09-18 + planning adjustments in Assumptions)
├── research.md                      # Phase 0 — R-01…R-16, with measurements
├── data-model.md                    # Phase 1 — columns, two tables, seeds, JSON keys, invariants
├── quickstart.md                    # Phase 1 — validation scenarios + real-load runbook
├── contracts/
│   ├── reading-integrity.md         # parser API, completeness, corrections, acknowledgement, partial commit
│   ├── category-mapping.md          # aliases, season-specific rows, frozen labels
│   ├── third-party-lock.md          # guard, structural test, ordering rule, legal basis
│   ├── identity-review-api.md       # candidates, decisions, resolver, gate, reversal
│   ├── historical-load.md           # staging service + script, full start list, printed points, idempotence, 2026 untouched
│   ├── history-progression-api.md   # endpoint, thresholds, parent gate, budget
│   └── ui-history.md                # card, preview extensions, board, review page
├── checklists/requirements.md       # spec quality checklist
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/<rev>_race_history_backfill.py     # new, down_revision=c2314ccd7927
├── app/
│   ├── config.py                                       # + RACE_HISTORY_FAMILY_POLICY_VERSION
│   ├── models/
│   │   ├── race_result.py                              # + category_label_raw, category_age_min_raw, category_age_max_raw
│   │   ├── race_competitor.py                          # unique → index; + city_text; signatures relationship
│   │   ├── race_competitor_signature.py                # new
│   │   └── race_identity_candidate.py                  # new
│   ├── schemas/
│   │   ├── race_imports.py                             # + categories[], unreadable_rows[], corrections, acknowledge, pending_categories
│   │   ├── race_identity.py                            # new (only schema that serialises city)
│   │   ├── athlete_race_analysis.py                    # + AthleteRaceHistoryRead, HistoryPoint, SeasonCompletion
│   │   └── race_results.py                             # + category_label on stored results; standings is_calculated
│   ├── routers/
│   │   ├── race_imports.py                             # thin caller of import_staging; + corrections, acknowledge, commit-pending; gate 409
│   │   ├── race_identity.py                            # new
│   │   └── athlete_race_analysis.py                    # + GET /{athlete_id}/race-analysis/history
│   └── services/race/
│       ├── pdf_parser.py                               # band reader, ParsedResults, numerals I–XII; back-compat wrapper
│       ├── normalizer.py                               # + aliases, HEADER_ALIASES
│       ├── completeness.py                             # new
│       ├── import_staging.py                           # new (extracted from the router)
│       ├── ingestor.py                                 # IdentityResolver, frozen columns, athlete_id for linked competitors, only_categories
│       ├── identity_review.py                          # new
│       ├── identity_resolver.py                        # new
│       ├── third_party_guard.py                        # new
│       ├── analytics.py                                # guarded entry points
│       └── history.py                                  # new (reuses field_metrics + course/derived)
├── scripts/
│   ├── seed_race_categories.py                         # + 3 inactive rows
│   ├── seed_race_points_schemes.py (or existing seed)  # + 2 descriptive rows
│   └── stage_race_history.py                           # new — stages only, never commits
└── tests/
    ├── helpers/results_pdf_builder.py                  # synthetic historical-layout PDFs (fake names)
    ├── privacy/test_third_party_lock.py
    ├── services/race/test_band_reader.py · test_parser_historical_layout.py · test_completeness.py
    │                 test_identity_review.py · test_identity_resolver.py · test_history.py
    ├── routers/test_race_identity.py · test_race_imports_history.py · test_athlete_race_history.py
    └── mysql/test_race_history_models.py

frontend/src/
├── api/raceHistory.ts · api/raceIdentity.ts · types/raceHistory.types.ts · types/raceIdentity.types.ts
├── schemas/raceImportCorrections.ts · hooks/race/useAthleteRaceHistory.ts · hooks/race/useIdentityReview.ts
├── components/race/history/                            # HistoryProgressionCard (lazy), HistoryChart, HistoryTable, CaveatsNote, SeasonCompletionChips
├── components/competitions/import/                     # + CategoryMappingTable, RowCorrectionDialog, AcknowledgeGapDialog; ImportWizard extended
├── routes/competitions/history/HistoricalLoadPage.tsx · IdentityReviewPage.tsx
├── routes/athletes/AthleteDetailPage.tsx               # mounts the card (coach)
├── routes/parents/MyAthleteDetailPage.tsx              # mounts the card (family)
└── e2e/race-history.spec.ts

docs/10-race-results/history-backfill-design.md · runbook-ops.md (§11) · docs/implementation-status.md · docs/technical-notes.md
```

**Structure Decision**: existing web-application layout; everything lands inside the race module (`app/services/race/`, `components/race/`, `components/competitions/import/`) except the new identity router and the cross-cutting privacy test. Suggested implementation order, which `tasks.md` will expand: (1) migration + models; (2) reading integrity; (3) categories + frozen labels; (4) third-party lock; (5) identity review + resolver; (6) staging + partial commit; (7) history API; (8) UI; (9) privacy audit, docs, real-load runbook. Phases 2–4 are independent of each other after phase 1; phase 5 depends on 1; phase 6 on 2, 3 and 5; phase 7 on 1 and 3; phase 8 on 6 and 7.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. One watch item, not a violation: if `POST /race-identity/rebuild` exceeds its 10 s budget on Render's free tier with the real universe, the measured figure and the chosen mitigation (tighter blocking key or incremental rebuild per staged import) are recorded here.

**G4 measurement (2026-09-21, local laptop, aiosqlite).** Synthetic universe of 3 000 rows (15 staged imports × 200, 1 200 distinct synthetic riders, 5 % with a dropped surname): candidate building + persistence **0.22 s** first run (1 193 candidates), **0.09 s** idempotent re-run (0 created). The candidate core is far inside budget. What the figure excludes is the `rows_loader`: in production `load_identity_rows` re-downloads each staged PDF over SFTP and re-parses it — **0.60 s per 229-row file** measured locally for the parse alone, so a full 15-file historical stage costs ≈ 9 s of parsing plus SFTP latency, on every `/rebuild` **and** every `/commit` (the gate runs a rebuild first). On Render's free tier this will likely exceed 10 s for the historical load; for a normal 2026 commit (one staged file) it stays ≈ 1–2 s. Mitigation, assigned to W4 before the real load (see note on T061): cache the corrected parsed rows per staged import keyed by `(sha256, corrections revision)` so a rebuild reparses only imports whose file or corrections changed; until then the staging runbook stages the historical files in batches of ≤ 5 per rebuild.

**G4 mitigation implemented and re-measured (2026-09-21, same laptop, W4).** Two process-local bounded LRUs (`routers/race_imports.py`, comment above `_reload_results_document`): the raw parse keyed by `sha256` (never invalidates — a committed import's file never changes) and the corrected-categories result keyed by `(sha256, len(corrections))` (a new correction changes the key; the stale entry is simply never requested again, evicted by the LRU bound). `_reload_parsed_from_storage` now returns a 5th value (`categories`) so the commit/commit-pending gate can compute `pending_categories` without a second reload. Measured against 15 real staged imports through the actual `load_identity_rows` → SFTP-local-fallback-download → pdfplumber-parse path (synthetic PDFs, 2 categories × 15 rows = 30 rows/file, 450 rows total — smaller than the 200-rows/file scenario above, chosen to keep the local re-measurement fast; the win is architectural, not row-count-dependent, since the cache is keyed per staged import regardless of its row count): first `identity_review.rebuild` **1.513 s** (15/15 files downloaded + parsed, 0 candidates — synthetic headers don't resolve to seeded category codes, which doesn't affect the timing being measured); a second `rebuild` immediately after, same corrections revision for all 15 imports, **0.002 s** — a ≈750× reduction, confirming the mitigation eliminates the repeat-download-and-reparse cost on every `/rebuild` and `/commit` gate check. The historical-load runbook's "batches of ≤ 5" workaround is no longer needed once this ships; `runbook-ops.md` should drop that line when the real load happens.

---

## Amendment 2026-09-26 — skill-only results loading

**Date**: 2026-09-26 | **Spec**: Clarifications 2026-09-26; FR-044…FR-049; corrected FR-027; Assumptions "Planning adjustments (2026-09-26)" | **Research**: R-17…R-31 | **Planning branch**: `claude/speckit-results-skills-upload-dap0pw` (the owner decides the implementation branch)

### Summary (amendment)

Each organiser prints results differently, and a fixed parser behind an upload keeps breaking. From now on, results enter the platform only through a **skill** that the operator runs on a computer with an LLM coding assistant:

1. A local script **masks** the official file.
2. The LLM writes a declarative **reading profile** from the masked view only.
3. A tested engine **applies** the profile to the real file locally.
4. The same script **stages** the válida: into the local database by default, and into production only with an explicit target and confirmation.

The web app keeps every review screen and loses only the upload step; the coach still reviews, resolves and commits.

Planning found two facts the clarification session did not know:
- Every review step re-parses the stored file today, so staged rows must be persisted. This adds one new 1:1 table.
- The revision path is only half-built: the diff and apply logic exist, but no endpoint calls them. The amendment wires them, with identity-aware matching.

Retired along the way:
- the GENERAL sheet;
- the fixed PDF and CSV parsers;
- the `/parse` route and the old staging script;
- three settings;
- two real official files committed as test fixtures.

### Technical Context (delta)

**Language/Version**: unchanged.

**Primary Dependencies**:
- No new dependency.
- `pdfplumber` stays: it is used by the engine and by the newsletter PDF reader. `python-multipart` stays: four other routes accept uploads.
- Profiles are JSON.
- The CLI loads `backend/.env.production` with `python-dotenv` (already installed through `pydantic-settings`), as `scripts/bitacora_snapshot.py` does.

**Storage**:
- One new table, `race_import_staged_documents` (1:1 with the import, a JSON document, cascade delete). No change to the `race_imports` columns.
- Reading profiles are committed JSON files.
- The evidence file goes to Hostinger SFTP in production and to the local fallback locally.

**Testing**:
- Default pytest lane:
  - engine: masking, vocabulary pins, run primitives, profile parity, a second fictional layout, delimited text;
  - CLI: target guards, actor checks, stdout sweep;
  - staging service and loader;
  - revision wiring and the removed-results read sweep;
  - the structural upload guard.
- About 60 router tests move from HTTP `/parse` to a staging helper and keep their assertions.
- `-m mysql`: the new table and the migration round-trip.
- vitest + MSW + jest-axe: the review-only wizard and the no-upload guard.
- Playwright: `race-history.spec.ts` stages through the CLI.
- The golden eval is not affected.

**Target Platform**:
- The CLI runs on the operator's computer (backend venv) against the local MySQL (compose) or the production MySQL on Hostinger. Remote access to Hostinger needs the operator's IP on the allow-list (runbook §1.2).
- The web app is unchanged.

**Performance Goals**:
- Review routes read one row by primary key instead of downloading from SFTP and parsing.
- The identity rebuild no longer re-parses files, so the G4 concern of the original plan disappears.
- Staging a 280-row válida writes about 60 KB of JSON.
- No endpoint budget changes.

**Constraints**:
- FR-046: no rider data reaches the LLM.
- FR-047: local by default, production only when explicit.
- The CLI's stdout and logs carry no rider data, and no `.env.production` value appears in the transcript.
- Single Alembic head; no new enum value on an existing column.
- Legacy imports are never mutated by the migration.
- Product copy in español neutro; planning corpus in English.

**Scale/Scope**:
- 1 migration, 1 table.
- A new `results_skill` package (seven modules), a CLI and one product profile.
- 8 backend modules changed.
- 4 backend files deleted, plus two real fixtures.
- Frontend: wizard step 1 and 5 modules removed, 7 entry points, about 15 strings, about 20 test files.
- 1 skill with 3 references, and 6 documents updated.

### Constitution Check (amendment)

*Gate before Phase 0 and again after Phase 1: both PASS.*

| Principle | How the amendment satisfies it | Status |
|---|---|---|
| I. Code Quality | Parsing knowledge moves into one engine of pure functions (`build_masked_view`, `apply_profile`, `leak_count`) plus data files; the layout-specific parsers are deleted rather than kept beside it. Shared types move to a neutral module. The review routes replace three copies of reload, cache and connection-release code with one loader. `revision.compute_diff` and `commit_revision` are reused and adapted, not rewritten. The new public modules carry docstrings. `ruff` + `tsc --noEmit`. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every contract ends with its tests. Privacy invariants are explicit: masked-view and stdout sweeps over synthetic names, the leak check, "no router imports the engine", the structural upload guard. Denied paths: the upload route is gone for every role, and the CLI refuses non-admin/coach users and unsafe targets. The migration round-trips under `-m mysql`. Ported tests keep their assertions; only their staging changes. Unrun lanes are reported. | PASS |
| III. UX Consistency | The coach keeps the same review, category, correction, identity and commit screens. Entry points that promised an upload are removed, not left dead. The new empty and legacy states are designed in Spanish and reviewed by `ux-researcher`, with jest-axe at zero violations. The revision diff, already designed, becomes reachable. | PASS |
| IV. Performance | Review routes stop downloading and parsing a file on every request. No list query loads documents (the 1:1 table is read by id only). The bundle shrinks (code removed). | PASS |
| V. Youth Psych. Safeguards | Not a psychological instrument; unchanged. | N/A |
| Gate — Privacy | FR-046 is enforced by structure (masked view, vocabulary pins, leak check) and by procedure (skill rules, deny rules). The CLI never prints rider data. Staged documents live only in the database and are deleted on commit and discard. Privacy-audit finding A closes. Two real official files leave the tree; purging them from history is flagged to the owner. The mandatory `data-privacy-guard` audit of the engine, CLI, skill and API deltas, reviewed by `data-platform-lead`, happens before any real file is masked. | PASS |
| Gate — Stack discipline | No new dependency. The CLI reuses the app's models, services and settings. Profiles are JSON. | PASS |
| Gate — Security | The upload surface shrinks to the four reviewed non-results endpoints, pinned by a test. A production write needs an explicit target and confirmation, a schema-head match and SFTP. The acting user must be an active admin or coach. Secrets are read from git-ignored files and scrubbed from errors. Deny rules keep the private folders out of the LLM session. | PASS |
| Gate — Secrets | No `.env.production` value is printed or passed on a command line; the production confirmation names the target, not the database. | PASS |
| Gate — AI features | No product AI change (no prompt, model or pipeline). The development-time LLM that writes profiles sees only masked content: the constitution's rule on third-party prompts, applied to the operator's tooling. | PASS |
| Gate — Observability | CLI output and engine logs carry only ids, counts, codes, ordinals and pages. The audit `create` records `via = results_skill`, and each change of a revision commit is audited. | PASS |
| Workflow | Conventional Commits in Spanish, with no AI mention. The owner decides the implementation branch. | PASS |

**Post-design re-check (after Phase 1)**: unchanged. Five planning adjustments are recorded in `spec.md` Assumptions:
1. the GENERAL sheet is retired for every season;
2. race conditions leave the load;
3. the revision diff and apply are wired;
4. legacy imports are re-staged;
5. a revision applies as a whole.

### Project Structure (amendment delta)

**Documentation**:
- `spec.md` (Clarifications 2026-09-26, FR-044…FR-049, adjustments);
- `research.md` R-17…R-31;
- `data-model.md` §11;
- `contracts/`: six new files — `masked-view.md`, `reading-profile.md`, `results-skill-cli.md`, `staged-import.md`, `revision-via-skill.md`, `ui-review-only.md` — and notes added to `historical-load.md` and `reading-integrity.md`;
- `quickstart.md` §9;
- `tasks.md` Phase 11 onward.

**Source code**:

```text
backend/
├── alembic/versions/<rev>_race_import_staged_documents.py   # new; down_revision = the single head (be4595de1ad2 at planning)
├── app/
│   ├── config.py                                  # − race_max_pdf_mb, race_parse_timeout_seconds, race_pending_ttl_hours
│   ├── models/race_import_staged_document.py      # new
│   ├── routers/race_imports.py                    # − /parse, upload helpers, reload + caches; + loader, 409 restage_required, revision branches
│   ├── services/audit.py                          # − registry entry of /parse
│   └── services/race/
│       ├── staged_document.py                     # new: ResultsRow, ParsedCategory, ParsedResults, UnreadableRow; load / delete
│       ├── import_staging.py                      # stage_extracted_results (parse-free)
│       ├── completeness.py                        # types from staged_document
│       ├── ingestor.py · identity_review.py       # − GENERAL
│       ├── revision.py                            # identity-aware compute_diff; commit_revision wired; reason always required
│       ├── pdf_parser.py · csv_parser.py          # deleted
│       └── results_skill/                         # new; imported by no router
│           ├── __init__.py (ENGINE_VERSION) · vocabulary.py · masking.py · pdf_runs.py
│           └── profile.py · apply.py · target.py
├── race_reading_profiles/copa-valle-results-pdf.json          # new
├── scripts/race_results.py                        # new CLI; scripts/stage_race_history.py deleted
└── tests/
    ├── helpers/staging.py (new) · helpers/results_pdf_builder.py (+ unruled fictional layout, CLI entry)
    ├── fixtures/race/valida_iv_2026_*.pdf         # deleted (real official files)
    ├── fixtures/race_profiles/fictional-unruled.json
    ├── privacy/test_no_results_upload.py · scripts/test_race_results_cli.py
    ├── services/race/results_skill/… · test_staged_document.py · test_revision_diff_identity.py · test_deleted_results_excluded.py
    └── routers/…                                  # about 60 tests ported from HTTP /parse to stage_for_test

frontend/src/
├── App.tsx                                        # redirects without ?import
├── components/competitions/import/ImportWizard.tsx      # − step 1; RaceUploadZone.tsx deleted
├── components/competitions/imports/LoadsSection.tsx · ResumeStatusNotice.tsx · DiscardImportDialog.tsx
├── components/competitions/tabs/ResultsTab.tsx · components/calendar/EventForm.tsx
├── routes/competitions/CompetitionImportPage.tsx · CompetitionsListPage.tsx · CompetitionDetailPage.tsx
├── api/raceImports.ts · hooks/ai/useRaceImports.ts · hooks/race/useImportPrefill.ts (deleted) · types/raceImports.types.ts
└── e2e/race-history.spec.ts (stages through the CLI) · prefill-import-from-competition.spec.ts (deleted) · cup-vs-championship.spec.ts

.claude/skills/race-results-load/SKILL.md · references/{masked-view,reading-profile,manifest}.md   # new
.claude/settings.json                                # + permissions.deny for output/race-results/**/private/**
docs/10-race-results/history-backfill-design.md (addendum) · runbook-ops.md (§12 rewritten)
docs/10-race-results/upload-design.md · upload-workflow.md (superseded banner) · CLAUDE.md (race-results bullet)
docs/implementation-status.md · docs/technical-notes.md
```

**Structure decision**:
- The engine lives inside the race module (`app/services/race/results_skill/`) so it shares types, the normalizer and the tests, but no router may import it (pinned).
- The CLI follows the existing `scripts/` pattern.
- The skill follows `bitacora-pdf`.

**Implementation order**, expanded in `tasks.md`:
1. Foundations: migration, model, type move, staging test helper.
2. Engine: runs, masking, vocabulary, profile, apply, and Copa Valle parity.
3. Staging on persisted documents: service, loader, router rewiring, legacy 409, GENERAL removal, test ports.
4. CLI: target guard and evidence upload.
5. Upload removal and its guard.
6. Frontend review-only.
7. Revision wiring.
8. Skill and deny rules.
9. Docs, privacy audit and gates.
10. Owner steps.

**Dependencies**:
- Phases 2 and 3 are independent after phase 1.
- Phase 4 needs 2 and 3.
- Phase 5 needs 3.
- Phase 6 needs its backend counterparts (3, 5) for the e2e, but its component work can start once the contracts are fixed.
- Phase 7 needs 3.
- Phase 8 needs 4.
- Phase 9 needs everything.

### Complexity Tracking (amendment)

No violation. Watch items:

- **Revision wiring (R-24)** is the largest and most delicate piece, so it has its own phase. If the owner defers it, `stage` must refuse a different reading of a committed válida (`revision_not_available`, CLI exit 12) instead of staging a revision whose commit would only add rows, as the current path does. The skill's report then says the válida needs the revision phase.
- **Production writes from a laptop.** Hostinger's remote-MySQL allow-list and connection timeouts apply. The CLI stages one válida per transaction, and `--dry` exists to validate before writing.
- **Unmeasured volume**: the size of the largest real document. The estimate is about 60 KB for 280 rows, well inside MySQL's JSON and packet limits; it is re-checked on the first real válida and recorded here.
