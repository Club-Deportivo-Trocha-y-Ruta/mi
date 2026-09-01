# docs/ — Documentation Index

Numbered folders by feature in chronological order. Internal files by type: `workflow.md`, `research.md`, `design.md`, `qa.md`, `reference.md`.

| # | Folder / File | Contents |
|---|---|---|
| — | [01-marco-teorico.md](01-marco-teorico.md) | Scientific foundation: LTAD, PHV, physiology, nutrition, regulations (non-negotiable reference) |
| 02 | [02-scaffolding/](02-scaffolding/) | Architecture and stack design decisions |
| 03 | [03-fase1/](03-fase1/) | Auth, roles, athlete CRUD, PHV anthropometry — workflow + QA plan |
| 04 | [04-percentiles/](04-percentiles/) | WHO/CDC percentiles: research + implementation of growth curves |
| 05 | [05-design-system/](05-design-system/) | Visual system: palette, typography, components, tokens |
| 06 | [06-parents/](06-parents/) | Parent/guardian module: backend + frontend portal |
| 07 | [07-notifications/](07-notifications/) | Notifications module: email, PDF, DOCX |
| 08 | [08-onboarding/](08-onboarding/) | Invitation-based onboarding: research + design + implementation |
| 09 | [09-training-planning/](09-training-planning/) | Training sessions: planning, attendance, rubric, monthly report with AI |
| 10 | [10-race-results/](10-race-results/) | Copa Valle XCO results: PDF ingestion, fuzzy normalization, longitudinal analytics (progression, podium gap, club ranking, projection). Extension 2026-05-26: race conditions in UI (wizard + tri-state card + PATCH) — see `upload-design.md` §14. Extension 2026-05-27: **Competitions** module (CRUD `race_events`, relocated wizard, URL-driven tabs) — see `competitions-module.md` |
| 11 | [11-informe-tecnico-mensual/](11-informe-tecnico-mensual/) | **Monthly Technical Report** (Phase 1.9): refactor of the club monthly report into a funder-style report document. 1:1 project profile, coach-editable AI narrative by blocks, podiums of the month, restricted-distribution PDF — `workflow.md` + `design.md` + `runbook.md` (coach guide) |
| 12 | [12-competitions-unification/](12-competitions-unification/) | **Unified Competitions Module** (007): consolidates `/competitions` CRUD and `/coach/race-analysis` into one module; adds results/standings read endpoints, call-up roster (`race_event_roster`), stale-analysis marking, bidirectional 1:1 calendar sync — `workflow.md` (PRD) + `implementation-notes.md` (as-built) |
| 14 | [14-tecnica-gymkana-7-15/](14-tecnica-gymkana-7-15/) | **Technique & Gymkhana Research** (source for feature 018): deep-research report on technique drills/gymkhana for ages 7–15 XCO; A–H skill taxonomy; ~24-exercise bank with circuit layouts; LTAD/PMBIA/NICA alignment; mastery-climate framing — `research.md` |
| 15 | [15-tecnica-gymkana-modulo/](15-tecnica-gymkana-modulo/) | **Technique & Gymkhana Library Module** (specs/018): module design, `technique_*` data model + `athlete_skill_progress`, `/api/technique` endpoints, session-reuse approach, per-athlete progress (coach-only, no comparison), illustrative-layout decision — `design.md` |
| 16 | [16-strava-sync/](16-strava-sync/) | **Strava Activity Sync** (specs/025): automatic ingest of athlete cycling-computer rides via Strava (webhook + reconcile fallback), coach-gated linking to training sessions, no GPS/route data ever persisted or displayed (Ley 1581) — `guia-familias.md` (family connection guide, Spanish), `guia-entrenador.md` (coach review-flow guide), `runbook-ops.md` (webhook subscription, athlete-cap upgrade, env vars) |

## Status

- [implementation-status.md](implementation-status.md) — Full per-module implementation history (step tables for every phase/spec). Summarized in `CLAUDE.md`.

## Training archive

- `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx` — 2026 macrocycle plan
