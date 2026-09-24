# Privacy audit — feature 046 (body composition by skinfolds)

Task T069 · perspective: `data-privacy-guard` · date 2026-09-24 · working tree on `main` (uncommitted, shared with feature 045).

Scope: every backend/frontend file added or changed by 046. Checked for logs, `HTTPException.detail`, AI prompts and provider requests, test fixtures, PDFs, family projections. Special focus on `family_band` (never `rojo`) across every family surface: the growth card, the newsletter PDF and the AI family text.

## Summary

```
PRIVACY AUDIT
Files reviewed: ~40 (backend and frontend 046 files plus their tests/fixtures)
Findings: 0 critical, 3 high (all fixed), 3 medium (1 fixed, 2 open), 4 low (1 fixed, 3 open / accepted)
Status: APPROVED once the open items below are tracked. Blockers fixed in this pass.
```

## Family surfaces: `family_band` never `rojo`

| Surface | Path | Result |
|---|---|---|
| Growth card (parent) | `routers/growth.py` builds `BodyCompositionFamilySummary` (`extra="forbid"`, 5 keys) only from `family_band`/`FAMILY_COPY`; `FAMILY_BAND = Literal["verde","ambar"]` | OK. Test `test_growth_summary_parent_body_composition_has_exactly_five_family_keys` |
| Coach-only endpoints | `GET …/body-composition`, referral note, `PUT/DELETE …/skinfolds` → `require_role(admin, coach)` + `verify_athlete_access` | OK. Parent gets 403, tested |
| Anthropometry list (parent) | `routers/anthropometry.py` sets `skinfolds = None` for parents | OK, tested |
| Newsletter PDF (Bitácora) | `newsletter_builder._build_body_composition_block` → `FAMILY_COPY[family_band]` + `NEWSLETTER_NOTICE`. It is PDF-only and dropped from the newsletter AI context. PDF rendered through `stage_log_builder.body_composition_annex` | OK after F2 + F4 (below) |
| AI family text (anthro v2) | `_render_body_composition_block(leaf, "family")` uses only `family_band`. The v2 family prompt forbids referral/"requiere acompañamiento". Fallback maps any non-verde to ámbar | OK after F3. Pipeline wiring is still open (F7) |
| Frontend | `FamilyBodyCompositionCard` types `FamilyBand = "verde" \| "ambar"`. The parent `GrowthTab` never calls `useBodyComposition`. `body-composition`/`growth-summary` stay out of `persistAllowList` | OK |

## Findings

### [HIGH, FIXED] F1: The referral note pasted coach copy with a clinical label and coach instructions
`backend/app/routers/body_composition.py` (`get_referral_note`) rendered `observed_pattern = COACH_REASON_COPY[band_reason_code]` into "El club ha observado …". For the only reading that normally triggers the note (rojo), the text family and professional would read was: "Patrón combinado: … Compatible con baja disponibilidad energética. No es un diagnóstico: conversa con la familia … y considera remitir a un profesional de salud." That breaks `contracts/skinfolds-api.md` §6 ("never … a label") and `research-safeguards-referral.md` §4 ("no clinical or diagnostic terms"). It also sent coach-only instructions, and `reference_extreme` sent percentile cut-offs ("≤ P5 o ≥ P95").
**Fix**: new `_REFERRAL_PATTERN_ES` with one neutral, observational noun phrase per `band_reason_code` (plus `_referral_observed_pattern`). It has no digits, no label, and no imperative. `COACH_REASON_COPY` is no longer imported by the router. The template comment was updated. **Test**: `tests/routers/test_body_composition_referral_copy.py` (covers every reason code; bans digits, `%`, `mm`, P5/P95, "disponibilidad energética", "diagnóstic", "conversa", "remit", "profesional", diet words).

### [HIGH, FIXED] F2: The newsletter family band was computed without height velocity, producing false "En observación"
`newsletter_builder._build_body_composition_block` called `build_reading(..., velocity=None)`. Without velocity, `growth_explanation` can never be `expected_pubertal_gain`/`pre_spurt_accumulation`, so a real rise in a girl around her growth peak became `sum_up_unexplained` → ámbar. The family then got "Notamos un cambio que vale la pena conversar" in the Bitácora PDF while the app card said "En su curva esperada". This is exactly the case the research warns against (spec scenario A: verde → verde; constitution Principle V). The docstring's claim that velocity is not needed for the ámbar/rojo rules was wrong.
**Fix**: one extra indexed query (only in the month of a counted set) loads the athlete's records up to the set's date. `velocity` and `previous_velocity` are computed with `growth_summary._build_velocity` against the immediately preceding record, the same inputs as `GET …/body-composition`. **Test**: `tests/services/training/test_newsletter_body_composition_velocity.py` (scenario A → verde). It failed before the fix and passes after.

### [HIGH, FIXED] F3: The family AI prompt block carried coach-only reference context
`anthro/context.py::_render_body_composition_block(leaf, "family")` sent the provider the population-reference line ("por encima de lo habitual en la referencia poblacional"), the declined-site count and the set count. The family prompt forbids mentioning any of them. Per spec clarification Q4, a reference-only ámbar is coach-only context. What the model never receives it cannot leak.
**Fix**: those three lines are rendered only for `audience == "coach"`. The family band line maps any non-`verde` value to ámbar (defense in depth). **Test**: `tests/anthro/test_body_composition_family_block_privacy.py`.

### [MEDIUM, FIXED] F4: The family newsletter PDF rendered whatever the persisted snapshot held
`stage_log_builder.body_composition_annex` returned `metrics_snapshot["pdf_only_blocks"]["body_composition"]` verbatim to the family PDF, from both the parent and the coach download routes. A legacy or tampered snapshot could carry any label.
**Fix**: the annex re-maps the block onto `FAMILY_COPY`. Only one of the two family labels is accepted. The sentence and notice always come from code. Anything else returns `None` (section omitted). The PDF sha256 is unchanged for valid snapshots. **Test**: `tests/services/training/test_body_composition_annex_hardening.py`.

### [MEDIUM, OPEN] F6: The growth-summary card uses fewer inputs than the full reading
`services/growth_summary.py::_build_body_composition` calls `build_reading` without `previous_velocity` and without the FUPRECOL reference. Its velocity also comes from the two most recent anthropometric records, not from the skinfold set's record. The reference gap cannot change `family_band` (reference-only ámbar projects to verde anyway). Missing `previous_velocity` can only suppress `velocity_low_persistent` (an under-alert). The velocity window can differ from the coach detail when a later record has no skinfolds. The family band is never `rojo`, so this is not a privacy leak, but coach detail, family card and newsletter can disagree in edge cases. **Recommendation**: extract one shared async helper, e.g. `body_composition.load_reading(db, athlete, at_record=None)`, used by the four call sites (`GET …/body-composition`, referral note, growth summary, newsletter). It must respect the T041 query-count gate.

### [MEDIUM, OPEN, accepted by spec] F8: The capture draft sits in `localStorage` with no TTL
`SkinfoldWizard` → `useFormDraft` with key `tyr:session-draft:v1:{userId}:skinfolds:{recordId}` keeps raw readings (a HIGH category of data) on the coach's device until save or discard. FR-008 and research R14 require the draft. The key holds ids only (no name) and is per user; the route is coach/admin only. **Recommendation**: add an expiry (e.g. 24 h, matching "within the same day" in spec US1 #7) and clear `tyr:session-draft:*` on logout.

### [LOW, FIXED] F5: The R14 lexicon missed plurals and conjugations
`prechecks.py` `_R14_DIET_LEXICON_PATTERN` did not match "dietas", "bajar peso", "perder de peso", "adelgace", "adelgazamiento". It now matches `\bdietas?\b`, `bajar\s+(?:de\s+)?peso`, `perder\s+(?:de\s+)?peso`, `\badelga(?:z|c)\w*`. **Test**: `tests/anthro/test_prechecks_r14_variants.py`.

### [LOW, OPEN] R13 only catches digits with units
Spelled-out forms ("18 por ciento", "treinta milímetros") are not caught. Risk is low because the context never gives the provider a skinfold, %BF or mass value. Consider extending if the golden eval ever shows it.

### [LOW, accepted] 422 validation bodies echo submitted readings
The default FastAPI `RequestValidationError` body includes `input` (the readings) and goes back to the same coach who sent them. Nothing is logged, same as every other router in the project.

### [LOW, accepted] The golden judge sees the whole leaf
`anthro/eval/judge.py` puts the whole leaf (including coach `band`) in the judge payload. It is eval-only, the golden cases are synthetic, and there are no names or numbers.

## Functional gaps found during the audit (not privacy blockers, for the orchestrator)

- **F7 (HIGH, functional)**: `context.build_context` reads `state["body_composition_reading"]`, but nothing sets it. `anthro/pipeline.py` and its caller in `routers/ai.py` never compute or pass a reading, so in production the body-composition leaf is always `None` and FR-029 is not met. From a privacy view this is safe by absence. Wiring needs the same shared helper as F6.
- **Field guide (`GET /api/body-composition/field-guide.pdf`, contract §7)**: no route exists yet in `backend/app`. Its 403 for parents is untested until it lands.

## Clean checks (no finding)

- **Logs**: no `logger`/`print` in `services/body_composition.py`, `routers/body_composition.py`, `services/reference_skinfolds.py`, the schemas or the model. The only prints are in `seed_growth_data.py` (FUPRECOL population reference row counts, no minors' data).
- **`HTTPException.detail`**: only machine codes, ids, ISO dates and fixed Spanish sentences (`athlete_too_young` does not echo the age). The domain errors carry no name.
- **Audit rows**: `skinfolds.saved` (`site_count` only), `skinfolds.deleted`, `skinfolds.referral_note_generated`. There are no values, and `site_count` is allow-listed in `services/audit.py`.
- **Referral PDF**: initials only (`T.A.`), age band, sex, neutral pattern, training hours. There is no `%`, `mm`, institution or full name (existing test with pdfplumber), and it is never stored (`generate_document_only`). The filename is `nota-remision…`.
- **Newsletter AI**: `athlete_monthly_newsletter_v2.build_context_from_metrics_v2` drops `pdf_only_blocks.body_composition`. The fake-provider test asserts no `body_composition`/`family_band`/"pliegue"/band code.
- **AI leaf**: ten qualitative keys, no `*_mm`/`*_pct`/`*_kg`, allow-listed in `context_builders.py`. The coach `band`/`band_reason_code` render only in the coach block. The critic reuses the audience-specific block.
- **Fixtures**: backend tests use "Test Atleta", "Deportista Prueba", "Otro Atleta", "Joven Atleta"; golden cases 013–018 carry no names. The frontend 046 MSW handlers and tests use synthetic data. The existing "Sebastián García Ficticio" fixtures predate 046 and are marked fictitious.
- **FUPRECOL CSV**: published population LMS reference; no individual data.
- **Frontend persistence**: `body-composition` and `growth-summary` are outside `persistAllowList` (default deny). URLs carry numeric ids only.

## Deferred verification

- `pytest -m mysql` (migration and enum alter) and `pytest -m golden` (anthro v2 with body-composition cases 013–018): not run in this session (no MySQL, no AI key).
- Playwright `body-composition.spec.ts`: not run.
- A real parent login and PDF download on production (T075): post-deploy.

## Recheck — 2026-09-24 (after T080, T081 and the field guide T057)

Perspective `data-privacy-guard`, same working tree. Every finding was checked against the current code, not the earlier fix notes. The finding IDs are the ones above. The two unlabeled LOW items are called "R13 spelled-out" and "422 echo / judge leaf" here.

| Finding | Status | Evidence in the current code |
|---|---|---|
| F1 referral note copy | **Closed, still holds** | `routers/body_composition.py::get_referral_note` now takes its reading from the shared `load_reading`. It still renders `_referral_observed_pattern` (`_REFERRAL_PATTERN_ES`), and `COACH_REASON_COPY` is still not imported by the router. `test_body_composition_referral_copy.py` passes. |
| F2 newsletter band without velocity | **Closed, now structural** | `newsletter_builder._build_body_composition_block` calls `load_reading(db, athlete, until=month_end, since=month_start)`, so velocity and previous-cycle velocity come from the same helper as the coach detail. `test_newsletter_body_composition_velocity.py` passes (scenario A → verde). |
| F3 family AI block | **Closed, still holds, and now live** | Since T080 the leaf really reaches the provider, so this was re-read with that in mind. `_render_body_composition_block(leaf, "family")` still emits only the family-band line (non-verde → ámbar), the weeks since the previous set, and the qualitative sum/growth/FFM meanings. Band, reason, reference and declined-site lines are coach-only. `AnalysisContext` (which carries `band`/`band_reason_code` for the coach audience) is never serialized into the prompt or persisted: `persist.py` stores only the insight. The critic reuses the audience-specific block. The fallback family sentence comes from `FAMILY_COPY` only. |
| F4 newsletter PDF annex | **Closed, still holds** | `test_body_composition_annex_hardening.py` passes. |
| F5 R14 variants | **Closed, still holds** | `test_prechecks_r14_variants.py` passes. |
| F6 card uses fewer inputs | **Closed by T080** | `services.body_composition.load_reading` is the single DB-backed assembler. It is used by `GET …/body-composition`, the referral note, `routers/growth.py` (growth summary: one `load_athlete_records` SELECT plus at most one FUPRECOL lookup), the newsletter block and the anthro pipeline. The parent projection in `routers/growth.py` is still the explicit 5-key `BodyCompositionFamilySummary`. `test_body_composition_load_reading.py` passes. |
| F7 AI leaf never built (functional) | **Closed by T080** | `anthro/pipeline.py::_resolve_body_composition` loads the reading anchored at `target_record.id` (never later records). On `SQLAlchemyError` it degrades to no leaf and logs only `athlete_id`. `test_pipeline_body_composition_leaf.py` passes. |
| F8 draft with no TTL | **Closed by T081** | `useFormDraft` drops and removes a draft older than 24 h on read. `auth.store.logout()` calls `clearAllDrafts()`, which removes every `tyr:session-draft:*` key. FR-008 in spec.md now says "within the same day (24 h)" and requires discarding drafts at logout. Recheck additions: (a) new test `frontend/src/store/auth.store.draft-wipe.test.ts` proves `logout()` itself wipes skinfold drafts of every user and keeps unrelated keys; before this, only `clearAllDrafts()` was tested in isolation. (b) The stale `SkinfoldWizard.tsx` header comment ("Sin límite de tiempo (FR-008)") was corrected. |
| R13 spelled-out numbers (LOW) | **Open, accepted** | Unchanged. The provider still never receives a skinfold, %BF or mass value (leaf: ten qualitative keys, allow-listed). |
| 422 echo / judge leaf (LOW) | **Accepted, unchanged** | — |
| Field guide (`GET /api/body-composition/field-guide.pdf`, contract §7) | **New surface, clean** | `field_guide_router`: `require_role([admin, coach])`, no `athlete_id`, and the context is only the six static entries of `app/data/skinfold_sites.json` plus Spanish labels. It sends `Cache-Control: private, max-age=86400` (`private` keeps shared caches out) and writes no log or audit row. The template has no athlete variable. Tests `test_field_guide_coach_happy_path_lists_six_sites_no_athlete_data` and `test_field_guide_parent_forbidden` pass. The grayscale eyeball check (T059) is still pending. |

Observation (not a finding): for a coach-side rojo `energy_availability_pattern` the family block still lists the qualitative sum and FFM trend ("una disminución real", "en descenso"). This is what `contracts/ai-body-composition-leaf.md` §2 allows (codes plus one-line meanings, `family_band` only). The family prompt, R13/R14 and the critic keep it to process language. Golden case 017 is the guard; it was not run here (no AI key).

Commands run in this recheck (offline lane):
- Backend: `tests/anthro/{test_body_composition_family_block_privacy, test_context_body_composition, test_prechecks_r14_variants, test_privacy_seam, test_pipeline_body_composition_leaf}.py`, `tests/routers/{test_body_composition, test_body_composition_referral_copy}.py`, `tests/services/test_body_composition_load_reading.py`, `tests/services/training/{test_body_composition_annex_hardening, test_newsletter_body_composition_velocity, test_newsletter_body_composition}.py`, `tests/test_newsletter_privacy.py`: all pass (101 + 32).
- `tests/test_growth_summary_latest_analysis.py`: 49 pass, 1 fails (`test_null_when_ai_disabled`, the known local-`.env` `AI_ENABLED=true` issue, not 046).
- Frontend: `src/hooks/useFormDraft.test.ts` and `src/components/athletes/body-composition/**`: 93 pass. The new `src/store/auth.store.draft-wipe.test.ts`: 1 passes.

Recheck result: **no open privacy blocker.** Still deferred: `pytest -m mysql`, `pytest -m golden` (cases 013–018 with the leaf now live), Playwright, and the post-deploy parent check (T075).
