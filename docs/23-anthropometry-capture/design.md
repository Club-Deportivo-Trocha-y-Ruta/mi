# Guided anthropometric capture — Design

Feature `specs/048-anthropometry-capture-ux`. Reworks how the coach captures the four basic
measures (weight, standing height, sitting height, optional arm span), and adds correction of
saved records, a group measurement session and offline-safe saving. Contracts:
`specs/048-anthropometry-capture-ux/contracts/api.md` and `contracts/ui.md`. Decision record:
`specs/048-anthropometry-capture-ux/research.md` (R1–R12). If this file and a contract
disagree, the contract wins.

## Context

Basic measures feed the maturity offset and PHV phase, WHO percentiles, height velocity, growth
alerts, the anthropometry AI explanation, the newsletter and the skinfold module (feature 046).
Sitting height is the most error-prone: it is taken on a bench and the bench height must be
subtracted. Before 048 a saved record could not be corrected, the form had no plausibility
checks and no teaching aids. This feature applies the pattern already used for skinfolds
(pre-check, one step per measure, illustration with "Dónde / Cómo") to the basic measures.

## Flows

| Flow | Route (coach/admin only) | Notes |
|---|---|---|
| Single capture | `/athletes/:id/anthropometry/new` | Guided (default) or quick, switchable without losing values |
| Edit | `/athletes/:id/anthropometry/:recordId/edit` | Quick layout, pre-filled; evaluator or admin |
| Group session | `/anthropometry/session` | Picker, queue, summary; in-memory state |
| Skinfold detour | `/athletes/:id/anthropometry/:recordId/skinfolds?returnTo=…` | `returnTo` is allow-listed |

Guided mode: Preparación (pre-check reminder, not a gate) → one step per measure → Revisar
(values, plausibility warnings, plain-language PHV, save exits). Quick mode: all measures on one
screen. Both share one React Hook Form instance, so switching modes keeps the values.

## Technical decisions

Numbers refer to `research.md`.

| # | Decision | Rationale | Discarded alternative |
|---|---|---|---|
| R1 | Derivation extracted to `backend/app/services/anthropometry.py::derive_record_fields` and used by POST and PUT | Same rules on create and edit; no second inline copy | Recompute in SQL; call the POST handler from PUT |
| R2 | `can_modify_anthropometric_record` in `backend/app/services/permissions.py` (evaluator or admin); list exposes `can_modify` | Feature 041 has no per-coach assignment; RBAC stays centralized | Hide actions in the frontend only |
| R3 | Edits never send the approaching-circa-PHV notification | No persisted "sent" marker; a migration for a rare case is not justified | `circa_alert_sent_at` column; resend on crossing |
| R4 | POST returns `409 anthropometry_same_date_exists` with `existing_record_id` and `same_values`; `same_values=true` on a retry counts as saved | Covers same-date warning and retry safety with no schema change | Idempotency key column; unique DB constraint (legacy pairs would break the migration) |
| R5 | One plausibility engine in Python (`anthropometry_plausibility.py`), used by a dry-run endpoint and by the list (`plausibility_flags`, computed at read time) | The "Revisar" marker uses exactly the rules shown before saving; no TS/Python parity problem | TypeScript mirror with shared fixtures; stored flags |
| R6 | PUT deletes the record's AI explanations, recomputes skinfold estimates if weight changed, and re-checks age/interval if the date changed; DELETE removes skinfold set and explanations | Explanations assume an immutable record; 046 rules must keep holding | Leave stale explanations |
| R7 | Audit `update`/`delete` on `anthropometric_record`; field names only, values only for `evaluation_date`; dry-run registered as non-mutating | Minors' privacy; route-walk test enforces registration | Log values |
| R8 | New pages under `components/athletes/anthropometry-capture/`; no draft persistence; device preferences in `localStorage` (`tyr.anthro.captureMode`, `tyr.anthro.benchHeightCm`); session store in memory only | Online-only capture by clarification; nothing personal on the device | `useFormDraft`; persisted queue |
| R9 | `GET /api/anthropometry/roster?date=` in a bounded number of queries (test asserts ≤ 4) | Avoids the per-athlete N+1 of the athletes list | Reuse `getAthlete` per athlete |
| R10 | Basic-measure texts in `backend/app/data/anthropometry_measures.json`; frontend `measureGuides.ts` holds the same texts; a vitest parity test reads the JSON | One source for app and PDF without breaking the standalone frontend build | Serve texts from an API; cross-repo JSON import |
| R11 | Illustrations generated in the owner's browser with Gemini, using `frontend/src/assets/skinfolds/triceps.webp` as style reference; the owner approved each image before it entered the repo | Consistent style, no photos of real people | Photos; subagent-driven generation |
| R12 | E2E runs locally on the isolated stack only (`frontend/scripts/e2e-stack.sh`, API :8001, MySQL :3307) | The default local stack points at production MySQL | Default stack |

## Plausibility rules (R5)

Codes are a stable API; the Spanish copy lives in the frontend. Warnings never block saving.

| Code | Measure | Rule | Needs previous record |
|---|---|---|---|
| `height_decreased` | Standing height | Current < previous − 1.0 cm | Yes |
| `height_velocity_implausible` | Standing height | Interval ≥ 60 days and gain per year > 15 cm | Yes |
| `weight_change_large` | Weight | Absolute change / previous > 10 % | Yes |
| `sitting_ratio_atypical` | Sitting height | Sitting / standing outside [0.47, 0.57] | No |
| `arm_span_ratio_atypical` | Arm span | Arm span / standing outside [0.90, 1.10], only when present | No |

Hard validation (422) stays separate: weight 20–150 kg, standing 100–220 cm, sitting 50–120 cm,
arm span 100–220 cm, date not in the future, and net sitting / standing outside [0.40, 0.65]
(`sitting_ratio_impossible`). Velocity is skipped below 60 days because annualizing a few
millimetres of error inflates the rate.

## Session behaviour

- Each athlete is saved to the server when confirmed; the queue is never persisted.
- "Omitir por hoy" creates no record. The summary shows Medidos, Omitidos and Pendientes.
- "Seleccionar todos los visibles" skips athletes already marked "Medido hoy".
- "Abrir la existente" inside a session marks the athlete as measured with the existing record.
- The progress indicator "N de M" is `min(done + 1, total)`.

## Implementation-time findings

| Finding | Resolution |
|---|---|
| The review-step dry-run is a `mutate` fired from `useEffect` behind a `lastKeyRef` guard. Under React StrictMode (dev, used by Playwright) the simulated unmount detached the observer and the guard blocked a second call, so "Revisando las medidas…" never resolved | Effect cleanup resets the guard; StrictMode regression test added. In dev the dry-run fires twice; it writes nothing and production is unchanged |
| Same-date dialog restored focus to the previously focused element | Date-input focus runs in a 150 ms timeout (proposed cleaner fix: an `onCloseFocus` hook on `ConfirmDialog`, not done because the file was out of scope) |

## Privacy

The privacy audit of the whole change is `specs/048-anthropometry-capture-ux/privacy-audit.md`
(approved with recommendations: 0 blockers, 1 major, 3 minor). Highlights: audit and logs carry
field names only; `can_modify` and `plausibility_flags` are omitted from parent payloads; the
session store holds ids and statuses only; illustrations are faceless line art with no text and
no image metadata. Open recommendation P-1 (`notes` has no `max_length` on the backend) is
tracked in `docs/23-anthropometry-capture/qa.md`.

## References

- `specs/048-anthropometry-capture-ux/{spec,plan,research,data-model,quickstart}.md`
- `backend/app/routers/anthropometry.py`, `backend/app/routers/anthropometry_roster.py`
- `backend/app/services/anthropometry_plausibility.py`, `backend/app/services/anthropometry.py`
- `frontend/src/components/athletes/anthropometry-capture/`
- `docs/21-body-composition/` (skinfold wizard this feature links to)
