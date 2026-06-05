# Deploy Checklist — Training Sessions Module

**Preparation date:** 2026-05-06
**Target:** Render Free Tier — Oregon — Branch `main`
**Auto-deploy:** enabled on push to `main`

---

## Pre-deploy: local verification

- [ ] `alembic heads` shows exactly one head: `b2c3d4e5f6a7`
- [ ] `alembic history` shows a chain with no forks (complete chain with no "Requested revision overlaps")
- [ ] `pytest --collect-only -q` collects 669 tests with no import errors
- [ ] `pnpm build` successful (exit 0), chunk size warnings are non-blocking
- [ ] `pnpm vitest run` — 717 tests passed

---

## Deployment steps (execute in order)

### Step 1: Review repository status
```bash
git status
git diff --stat
```
Confirm that the modified files are the expected ones from the training module.

### Step 2: Stage specific files

**Backend — models, schemas, routers, services:**
```bash
git add backend/app/models/training_session.py
git add backend/app/schemas/training_session.py
git add backend/app/routers/training_sessions.py
git add backend/app/routers/monthly_reports.py
git add backend/app/routers/athletes.py
git add backend/app/services/training/
git add backend/app/services/ai/use_cases/monthly_report.py
git add backend/app/services/ai/prompts/monthly_report.j2
git add backend/app/services/ai/prompts/registry.py
git add backend/app/services/notification/template_registry.py
git add backend/app/templates/notifications/
git add backend/app/main.py
```

**Backend — migrations (includes the fork fix):**
```bash
git add backend/alembic/versions/6e189a7e1e51_agrega_tablas_training_session_session_.py
git add backend/alembic/versions/b2c3d4e5f6a7_agrega_coach_observations_a_monthly_report.py
```
> NOTE: The file `a1b2c3d4e5f6_agrega_coach_observations_a_monthly_report.py` was
> renamed to `b2c3d4e5f6a7_*` to resolve a duplicate revision ID conflict.
> Git will detect this as a rename if you use `git add -A` or as a delete+add if you add
> each file individually. Make sure the old file appears as
> deleted: `git add backend/alembic/versions/a1b2c3d4e5f6_agrega_coach_observations_a_monthly_report.py`

**Backend — tests:**
```bash
git add backend/tests/test_training_session_models.py
git add backend/tests/test_training_session_service.py
git add backend/tests/test_training_session_router.py
git add backend/tests/test_training_session_privacy.py
git add backend/tests/test_training_session_notifications.py
```

**Backend — other modified files:**
```bash
git add backend/app/models/anthropometry.py
git add backend/app/models/parent_invite.py
git add backend/app/routers/anthropometry.py
git add backend/app/schemas/anthropometry.py
git add backend/app/schemas/athlete.py
git add backend/app/services/ai/context_builders.py
git add backend/app/services/ai/prompts/phv_explainer.j2
git add backend/tests/test_ai_context_builder_privacy.py
git add backend/tests/test_ai_phv_explainer.py
git add backend/tests/test_ai_prompt_registry.py
git add backend/tests/test_ai_router.py
git add backend/tests/test_athletes.py
git add backend/tests/test_notification_changes.py
git add backend/alembic/versions/e2f3a4b5c6d7_drop_anthropometry_mesocycle.py
git add backend/alembic/versions/f3a4b5c6d7e8_add_parent_user_id_to_invites.py
```

**Frontend:**
```bash
git add frontend/src/components/athletes/
git add frontend/src/hooks/athletes/
git add frontend/src/routes/athletes/
git add frontend/src/types/anthropometry.types.ts
```

> For the training module frontend files (routes, components, api, hooks, types):
```bash
git add frontend/src/routes/training/
git add frontend/src/routes/parents/training/
git add frontend/src/components/training/
git add frontend/src/components/parents/
git add frontend/src/api/trainingSessions.ts
git add frontend/src/api/trainingSessions.test.ts
git add frontend/src/types/trainingSession.types.ts
git add frontend/src/schemas/trainingSession.schema.ts
git add frontend/src/hooks/training/
git add frontend/src/test/
```

**Docs and memory:**
```bash
git add docs/09-training-planning/
git add docs/README.md
git add CLAUDE.md
```

### Step 3: Commit

```bash
git commit -m "$(cat <<'EOF'
feat(training): implementa módulo de sesiones de entrenamiento

Agrega módulo completo de planificación, ejecución y reporte de sesiones
de entrenamiento con asistencia por estados, rúbrica 3-ejes + RPE OMNI,
upload GPX, notificación a padres y reporte mensual con resumen IA.

Backend: 3 modelos, 14 endpoints, IA use case monthly_report con guardrails
de privacidad, ~870 líneas de tests pytest (≥80% cobertura services).

Frontend: 8 páginas (coach + parent), 12 componentes, 717 tests vitest
(0 violaciones a11y), MSW handlers para integración.

Privacidad: padres NUNCA ven feedback ajeno ni reporte agregado.
Filtros RBAC backend + defensa profunda frontend.

Strava integración: solo link manual coach por ToS Nov 2024.
GPS de atletas via .gpx upload (compatible con todas las edades).

Fix: fork en cadena Alembic resuelto — revision ID duplicado a1b2c3d4e5f6
renombrado a b2c3d4e5f6a7 en migración coach_observations.

Refs: docs/09-training-planning/{design,workflow,qa}.md
EOF
)"
```

### Step 4: Push

```bash
git push origin main
```

Render will start auto-deploy automatically.

### Step 5: Monitor deployment on Render

1. Go to Render Dashboard → `mi` service → **Events** tab
2. Wait for message: `Your service is live`  (approx. 2-3 min from push)
3. Verify startup logs:
   ```
   Applying migrations...
   INFO  [alembic.runtime.migration] Running upgrade ... -> b2c3d4e5f6a7
   Starting server...
   ```

### Step 6: Smoke test in production

```bash
# Verify docs
curl -s https://mi-2yzi.onrender.com/docs | grep -o "training-sessions"

# Login
TOKEN=$(curl -s -X POST https://mi-2yzi.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"entrenador@trochyruta.com","password":"Coach2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List sessions (should return [])
curl -s -H "Authorization: Bearer $TOKEN" \
  https://mi-2yzi.onrender.com/api/v1/training-sessions | python3 -m json.tool
```

### Step 7: Verify migration in DB

Connect to the Hostinger DB and execute:
```sql
SELECT version_num FROM alembic_version;
-- Should return: b2c3d4e5f6a7

SHOW TABLES LIKE '%training%';
-- Should show: training_sessions, session_attendance

SHOW TABLES LIKE '%monthly%';
-- Should show: monthly_reports
```

---

## Rollback plan (if migration fails on Render)

### Option A: Alembic downgrade (if DB migrated partially)

1. Connect to the Render service via Shell (Dashboard → Shell)
2. Run:
   ```bash
   alembic downgrade 6e189a7e1e51   # reverts to before coach_observations
   # or to revert to before the training module:
   alembic downgrade f3a4b5c6d7e8
   ```

### Option B: Revert the git commit

```bash
git revert HEAD --no-edit
git push origin main
```
Render will re-deploy with the previous code. Alembic on startup will run the downgrade automatically if the code supports it.

> WARNING: `alembic downgrade` in production implies DROP of tables. If session
> data has already been saved, it will be lost. Evaluate whether to take a backup first.

### Option C: Manual fix if there is data

If there is already data in `training_sessions` and the migration fails halfway:
1. Fix the migration script manually
2. Apply `alembic stamp <revision>` to mark the current state without running the migration
3. Contact Hostinger support if there is a table lock

---

## Environment variables — Audit

The training module **does NOT require new environment variables**. It reuses:

| Variable | Use in training module | Status on Render |
|---|---|---|
| `NOTIFICATION_SEND_EMAILS` | Send emails to parents when planning a session | Already configured |
| `NOTIFICATION_LOG_BODIES` | Must be `false` (NEVER log emails with athlete data) | Already configured |
| `EMAIL_PROVIDER` + `RESEND_API_KEY` | Email sending backend | Already configured |
| `EMAIL_FROM_ADDRESS` | `noreply@trochyruta.com` | Already configured |
| `APP_ENV` | Controls seed and mock LLM in dev | Already configured |

AI variables (if real LLM is activated):

| Variable | Description | Configured? |
|---|---|---|
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | For `monthly_report` use case | Verify on Render |
| `AI_PROVIDER` | `openai` or `anthropic` | Verify on Render |

> If the AI variables are not configured, the monthly report endpoint will fail
> in production. With `APP_ENV=development` it uses a mock LLM with no API key needed.
