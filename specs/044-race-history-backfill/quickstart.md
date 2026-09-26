# Quickstart — validating feature 044

Prerequisites: `backend/.venv` active; for UI checks `docker compose up` (MySQL 8.4 + MailHog) and `npm run dev`. All scenarios use **synthetic** files from `tests/helpers/results_pdf_builder.py`; never place an official file inside the repository. Remember that a local backend configured with the production database writes to production.

## 1. Reading integrity (US1)

```bash
cd backend && pytest tests/services/race/test_band_reader.py tests/services/race/test_parser_historical_layout.py tests/services/race/test_completeness.py -q
pytest tests/services/race/test_parser.py tests/services/race/test_parser_edge_cases.py -q   # FR-007: unchanged and green
```

Expect: every row of the builder files recovered (including rows whose club overprints the time); an unknown header listed with its rows; a removed ordinal reported as missing; 2026 oracles untouched. Contract: [reading-integrity](contracts/reading-integrity.md).

## 2. Categories and frozen labels (US2)

```bash
pytest tests/services/race/test_normalizer.py -k "alias or season_specific" tests/services/race/test_ingestor.py -k frozen -q
pytest -m mysql tests/mysql -k "race_results_frozen or signatures" -q          # needs TEST_DATABASE_URL (…_test)
```

Expect: renames resolve to current codes; `MAS_B_2025` / `PRE_F_U` resolve to inactive categories; a catalogue edit leaves stored labels unchanged. Contract: [category-mapping](contracts/category-mapping.md).

## 3. Third-party lock (US3) — must pass before any real load

```bash
pytest tests/privacy/test_third_party_lock.py -q
```

Expect: structural test green; unlinked competitor refused for all four roles; no synthetic third-party name in logs, prompts, newsletter context or family responses. Contract: [third-party-lock](contracts/third-party-lock.md).

## 4. Identity review (US4)

```bash
pytest tests/services/race/test_identity_review.py tests/services/race/test_identity_resolver.py tests/routers/test_race_identity.py -q
```

UI: stage two synthetic seasons → **Carga histórica** shows the identity banner → **Revisión de identidad**: decide the extra-surname pair "misma persona" and the two-towns pair "personas distintas" → the commit button unlocks. Re-run *Recalcular*: nothing is asked again. Contract: [identity-review-api](contracts/identity-review-api.md).

## 5. Historical load (US5)

```bash
python scripts/stage_race_history.py --manifest /path/outside/repo/manifest.json --dry   # lists what would be staged
pytest tests/routers/test_race_imports_history.py -q
```

Expect: partial commit leaves the inconsistent category pending; `commit-pending` finishes it after a correction or an acknowledgement; re-staging an identical file creates nothing; 2026 views unchanged (`pytest tests/services/race/test_analytics_charts.py -q`).

## 6. Progression (US6, US7)

```bash
pytest tests/services/race/test_history.py tests/routers/test_athlete_race_history.py -q
cd ../frontend && npx vitest run src/components/race/history src/routes/competitions/history
```

UI: coach opens an athlete with three seasons → one series, marker at the category change, dashed gap at the skipped válida, DNF marker, "sin dato" at the four-finisher válida, caveats visible. Parent with `RACE_HISTORY_FAMILY_POLICY_VERSION` empty sees only results from the registration date on; after setting it to an effective policy version, the full history — and never a third-party row. Contracts: [history-progression-api](contracts/history-progression-api.md), [ui-history](contracts/ui-history.md).

## 7. Gates before closing the feature

```bash
cd backend && pytest -q && ruff check
cd ../frontend && npm run typecheck && npm test
npm run test:e2e -- race-history.spec.ts
```

Plus: `data-privacy-guard` audit recorded in `specs/044-race-history-backfill/privacy-audit.md`; `pytest -m golden` unchanged (no AI change expected — run once to confirm); `alembic upgrade head` then `alembic downgrade -1` clean on the `_test` database.

## 8. Real load runbook (owner, after deploy)

1. Deploy with the lock and the gate in place; smoke `/health` and one authenticated endpoint.
2. Stage the fifteen files with the manifest script (files and manifest outside the repository).
3. Resolve categories pending (correct or acknowledge), then the identity review, then commit season by season.
4. Spot-check three club athletes against the official files; confirm a parent account sees no pre-registration result.
5. Publish the privacy notice version, set `RACE_HISTORY_FAMILY_POLICY_VERSION`, re-check the parent view.

---

## 9. Amendment 2026-09-26 — skill-only loading

§5 and §8 above describe the retired upload and script path. Use this section instead. Every file here is **synthetic**; the builder and the synthetic CSVs live in `backend/tests/helpers/`. Official files and manifests always stay outside the repository.

### 9.1 Engine and privacy (default lane)

```bash
cd backend && source .venv/bin/activate
pytest tests/services/race/results_skill -q      # masking, vocabulary pins, pdf runs, apply parity, second layout, delimited
pytest tests/scripts/test_race_results_cli.py -q # subcommands, target guards, actor checks, stdout sweep
pytest tests/privacy/test_no_results_upload.py -q
```

Expected:
- The masked view of every builder file contains no fake name, club or city.
- `copa-valle-results-pdf` reproduces the retired parser's rows on the overprint and 2026 layouts.
- The fictional second layout is fully read.
- The local guard refuses a remote host and the production pair; production is refused without `--confirm`, without SFTP, or on a head mismatch.
- Only the four known file endpoints exist, and `/imports/parse` answers 404 or 405 for every role.

Contracts: [masked-view](contracts/masked-view.md), [reading-profile](contracts/reading-profile.md), [results-skill-cli](contracts/results-skill-cli.md).

### 9.2 Review API on staged documents (default lane)

```bash
pytest tests/services/race/test_import_staging.py tests/services/race/test_staged_document.py -q
pytest tests/routers/test_race_imports.py tests/routers/test_race_imports_history.py tests/routers/test_race_imports_identity_gate.py -q
pytest tests/routers/test_race_imports_revision.py tests/services/race/test_revision_diff_identity.py tests/services/race/test_deleted_results_excluded.py -q
pytest tests/test_audit_coverage.py -q
```

Expected:
- Dry-run, corrections, acknowledge, commit and commit-pending work from the staged document.
- The document is deleted on full commit and on discard, and kept on partial commit.
- A legacy import answers `409 restage_required` everywhere except GET and discard.
- A revision dry-run returns the diff, a revision commit applies it with `race_result_revisions` rows, and removed results vanish from every read.

Contracts: [staged-import](contracts/staged-import.md), [revision-via-skill](contracts/revision-via-skill.md).

### 9.3 Frontend

```bash
cd ../frontend && npm run typecheck && npx vitest run src/components/competitions src/routes/competitions src/test
npm run test:e2e -- race-history.spec.ts cup-vs-championship.spec.ts   # isolated stack; stages through the CLI
```

Expected:
- No `input[type=file]` and no «Cargar resultados», «Importar resultados» or «Cargar archivo» anywhere in the competitions area.
- `/competitions/import` without `?import` lands on the board.
- A staged import opens directly in review.
- The revision diff shows, and its reason is required.
- The legacy notice offers only *Descartar*.
- jest-axe reports zero violations.

Contract: [ui-review-only](contracts/ui-review-only.md).

### 9.4 End-to-end on the local stack (manual, synthetic file)

```bash
docker compose up -d                                   # local MySQL 8.4
cd backend && alembic upgrade head
python -m tests.helpers.results_pdf_builder --out /tmp/tyr-demo/valida.pdf   # synthetic, fake names
python -m scripts.race_results mask --file /tmp/tyr-demo/valida.pdf
python -m scripts.race_results apply --run ../output/race-results/<run> --profile copa-valle-results-pdf
python -m scripts.race_results stage --run ../output/race-results/<run> --manifest /tmp/tyr-demo/manifest.json --user-id <local coach id>
cd ../frontend && npm run dev                          # open /competitions/import?import=<id>, review, commit
```

Then stage a second, edited reading of the same válida (one time changed, one row removed). It is staged as a revision; the diff shows one update and one delete, and the commit asks for a reason.

The helper's exact CLI flags are fixed in its task; the command above shows the intent.

### 9.5 Real-infrastructure lanes (report explicitly if not run)

- `pytest -m mysql tests/mysql -k staged_document`: the new table's constraints, `ON DELETE CASCADE`, JSON round-trip, and upgrade → downgrade → upgrade of the new revision.
- Playwright on the isolated stack (9.3).
- `pytest -m golden`: not expected to change, because there is no prompt or pipeline change. Record the decision as in T088.

### 9.6 Real load (owner, after deploy) — replaces §8 step 2 and runbook §12.3

1. **Pre-deploy.** Count the imports that will become legacy (before the deploy, every open import is legacy by definition):

   ```sql
   SELECT status, COUNT(*) FROM race_imports
   WHERE status = 'pending' OR JSON_LENGTH(parse_meta_json->'$.pending_categories') > 0
   GROUP BY status;
   ```

   Each one must be discarded, or re-staged with the skill after the deploy (a committed one with pending categories comes back as a revision).

2. **Deploy.** Then smoke `/health` and one authenticated endpoint.
3. **Stage the fifteen historical válidas locally.** With the skill, one válida at a time: `mask` → profile → `apply` → `stage` against the local database. Review them in the local app.
4. **Stage them in production.** On the owner's explicit request, run `stage --target production --confirm produccion` for each válida, season by season, oldest first.
5. **Commit.** The coach resolves pending categories and the identity review, then commits in the production app (runbook §12.4–§12.5, unchanged).
6. **Spot-check and publish** (runbook §12.6, unchanged).
