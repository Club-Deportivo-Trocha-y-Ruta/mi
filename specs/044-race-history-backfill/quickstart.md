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
