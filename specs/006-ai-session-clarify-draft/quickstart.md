# Quickstart: AI Session Clarify & Draft

## What this feature adds
A pre-wizard "Asistente IA" for session creation: it asks 2–4 clarifying questions
(selectable chips + free-text "Otro"), then pre-fills the existing session wizard with an
editable draft. Coach reviews/edits and saves through the normal flow. No DB changes.

## Prerequisites / env
Backend AI must be enabled (otherwise endpoints return 503 and the UI falls back to the
manual wizard — which is acceptable and tested):

```
AI_ENABLED=true
AI_PROVIDER=google            # or anthropic
AI_MODEL=gemini-2.5-flash-lite
AI_API_KEY=<key>
AI_MAX_TOKENS=8192
AI_TIMEOUT_SECONDS=30
AI_TEMPERATURE=0.4
AI_LOG_PROMPTS=false          # MANDATORY false (minors privacy)
```

For deterministic local/dev/test runs without a real key, set `AI_PROVIDER=fake` — but note
the assistant endpoints intentionally return 503 when AI is disabled/fake, so to exercise
the happy path in tests use `FakeLLMProvider` injected with a canned JSON fixture (see
backend tests), not the global fake gate.

## Run

```bash
# Backend
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev
```

## Manual smoke (happy path)
1. Log in as coach (`entrenador@trochyruta.com` / `Coach2026!`).
2. Go to **Entrenamientos → Nueva sesión → Asistente IA** (`/training/sessions/assistant`).
3. Type: *"salida de 90 min en La Cumbre, bajadas técnicas, grupo 13-15, faltan 12 días para la válida"* → **Continuar**.
4. Answer the 2–4 chip questions (try a single-select, a multi-select, and an "Otro").
5. **Generar borrador** → the wizard opens at Step 1 pre-filled; fields show a subtle "IA" marker.
6. Edit any field (marker clears), pick athletes, save. Confirm the saved session reflects your edits.

## Fallback smoke
- Set `AI_ENABLED=false`, repeat step 2–3: assistant shows "no disponible", a "continuar
  manualmente" action opens the empty wizard with no data loss.
- Simulate slowness/timeout: UI shows "pensando…"/"iniciando el servidor", then a
  recoverable error — never an unbounded spinner.

## Tests
```bash
# Backend (targeted)
cd backend && pytest tests/services/ai/test_session_assistant_use_case.py \
  tests/routers/test_session_assistant.py \
  tests/privacy/test_session_assistant_privacy.py -q

# Frontend (targeted)
cd frontend && npx vitest run src/components/training/session-wizard/ai-assistant
```

Expected coverage: clarify/draft happy paths, auth-denied (parent → 403), AI-disabled →
503 + UI fallback, malformed JSON → 422, timeout → 503, **privacy invariants** (no
id/name in prompt context or logs), and frontend a11y (axe = 0 violations).

## Key files
- Backend: `app/routers/session_assistant.py`, `app/services/ai/use_cases/session_assistant.py`,
  `app/services/ai/prompts/session_clarify.j2` + `session_draft.j2`,
  `app/services/training/session_assistant_context.py`, `app/schemas/session_assistant.py`.
- Frontend: `components/training/session-wizard/ai-assistant/*`,
  `routes/training/SessionAssistantPage.tsx`, `api/sessionAssistant.ts`,
  `hooks/training/useSessionAssistant.ts`.
