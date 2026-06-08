# Session AI Assistant (Clarify & Draft) — feature 006

> Pre-wizard "Asistente IA" that asks the coach a short batch of clarifying questions and
> then pre-fills the session wizard with an editable draft. The coach reviews and edits
> every field; nothing is auto-saved. Single-round, stateless, no database changes.

## Flow

1. Coach opens **Entrenamientos → Nueva sesión → Asistente IA**
   (`/training/sessions/assistant`) and optionally types a short free-text intent.
2. Frontend calls `POST /api/clubs/{club_id}/session-assistant/clarify` →
   `SessionClarifyUseCase` returns 0–4 questions (each 2–4 options), rendered as chips
   (single/multi-select) with an optional "Otro" free-text field.
3. Coach answers; frontend calls `POST /api/clubs/{club_id}/session-assistant/draft` →
   `SessionDraftUseCase` returns an editable draft (focus, objectives, structured
   description, duration, session kind, inferable logistics, and an athlete call-up
   **criterion**).
4. Frontend maps the draft to `TrainingSessionFormValues`, resolving `athlete_call_up`
   against the local roster, and prefills the wizard via
   `reset(values, { keepDirtyValues: true })`. AI-seeded fields show a subtle "IA" marker
   that clears once the coach edits the field. The draft's `notes` (AI rationale, e.g.
   tapering guidance) is shown as a read-only, dismissible "Sugerencia de la IA" banner at
   the top of the wizard.
5. Coach edits and saves through the normal session flow.

## Endpoints

| Method | Path | Use case | RBAC |
|---|---|---|---|
| POST | `/api/clubs/{club_id}/session-assistant/clarify` | `SessionClarifyUseCase` | coach/admin + club access |
| POST | `/api/clubs/{club_id}/session-assistant/draft` | `SessionDraftUseCase` | coach/admin + club access |

Error mapping: AI disabled (`ai_enabled=false`) → **503**; LLM timeout
(`ai_timeout_seconds`) → **503**; malformed/unsafe JSON after guardrails
(`LLMSchemaError`) → **422**; non-coach/admin or no club access → **403**. All `detail`
messages are neutral español. See `specs/006-ai-session-clarify-draft/contracts/`.

## Privacy contract (Ley 1581 — minors)

- The AI receives **only aggregate, non-identifying context**: `age_mix` counts,
  `total_athletes`, `season_phase`, `days_to_next_race`, `next_race_priority`, `today`.
- `selected_athlete_ids` is consumed **server-side** to compute age-mix counts and then
  discarded — ids/names are never placed in the prompt.
- The athlete call-up is proposed as a **criterion**
  (`todos_convocados` | `grupo_10_12` | `grupo_13_15` | `ninguno`), resolved to specific
  athletes by the frontend. No name/id ever leaves to the model.
- All coach-visible AI strings are scrubbed by the shared `Guardrails` (non-negotiables:
  no supplements, cadence ≥60, no power meters <13, no calorie counting, name redaction).
- `AI_LOG_PROMPTS` stays **false** in production; logs reference counts only.

## Non-negotiable principle compliance

Both the questions and the draft respect the club principles: fun-first for 10–12 (no
structured intervals), skills before fitness, biological age over chronological, ≤5
days/week with ≥1 rest day, weekly hours ≤ athlete age, zero supplements, cadence ≥60,
RPE primary / HR secondary, no power meters <13, flexible plan. Race proximity drives
tapering guidance via the `COPA_VALLE_2026` calendar constant in
`session_assistant_context.py`.

## Reliability / UX

- Each call is bounded by `ai_timeout_seconds` (~30 s) with explicit "pensando…" and
  cold-start ("iniciando el servidor") states.
- On any failure the coach gets a recoverable message and a "continuar manualmente"
  action that opens the empty wizard with no data loss.

## Key files

- Backend: `app/routers/session_assistant.py`,
  `app/services/ai/use_cases/session_assistant.py`,
  `app/services/ai/prompts/session_clarify.j2` + `session_draft.j2`,
  `app/services/training/session_assistant_context.py`,
  `app/schemas/session_assistant.py`, DI in `app/dependencies.py`.
- Frontend: `components/training/session-wizard/ai-assistant/*`,
  `routes/training/SessionAssistantPage.tsx`, `api/sessionAssistant.ts`,
  `hooks/training/useSessionAssistant.ts`, `schemas/sessionAssistant.schema.ts`.

## Tests

- Backend: 58 (use case, router, context, privacy invariants).
- Frontend: 31 new (panel single/multi/"Otro", draft→prefill, fallback states, per-field
  markers) + a11y axe = 0 violations; full suite green (1817).

## Out of scope (possible fast-follows)

Iterative multi-round clarification, voice input, weekly/microcycle batch generation, and
provider-native structured output (current path is prompt-instructed JSON + safe parse).
