# Deploy Checklist — Módulo Sesiones de Entrenamiento

**Fecha preparación:** 2026-05-06
**Target:** Render Free Tier — Oregon — Branch `main`
**Auto-deploy:** activado en push a `main`

---

## Pre-deploy: verificación local

- [ ] `alembic heads` muestra exactamente un head: `b2c3d4e5f6a7`
- [ ] `alembic history` muestra cadena sin forks (chain completa sin "Requested revision overlaps")
- [ ] `pytest --collect-only -q` recolecta 669 tests sin import errors
- [ ] `pnpm build` exitoso (exit 0), warnings de chunk size son no-bloqueantes
- [ ] `pnpm vitest run` — 717 tests passed

---

## Pasos de deploy (ejecutar en orden)

### Paso 1: Revisar estado del repositorio
```bash
git status
git diff --stat
```
Confirmar que los archivos modificados son los esperados del módulo training.

### Paso 2: Staging de archivos específicos

**Backend — modelos, schemas, routers, services:**
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

**Backend — migraciones (incluye la corrección del fork):**
```bash
git add backend/alembic/versions/6e189a7e1e51_agrega_tablas_training_session_session_.py
git add backend/alembic/versions/b2c3d4e5f6a7_agrega_coach_observations_a_monthly_report.py
```
> NOTA: El archivo `a1b2c3d4e5f6_agrega_coach_observations_a_monthly_report.py` fue
> renombrado a `b2c3d4e5f6a7_*` para resolver un conflicto de revision ID duplicado.
> Git detectará esto como rename si usás `git add -A` o como delete+add si añadís
> cada archivo individualmente. Asegurate de que el archivo antiguo aparezca como
> eliminado: `git add backend/alembic/versions/a1b2c3d4e5f6_agrega_coach_observations_a_monthly_report.py`

**Backend — tests:**
```bash
git add backend/tests/test_training_session_models.py
git add backend/tests/test_training_session_service.py
git add backend/tests/test_training_session_router.py
git add backend/tests/test_training_session_privacy.py
git add backend/tests/test_training_session_notifications.py
```

**Backend — otros archivos modificados:**
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

> Para los archivos del módulo training frontend (routes, components, api, hooks, types):
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

**Docs y memoria:**
```bash
git add docs/09-training-planning/
git add docs/README.md
git add CLAUDE.md
```

### Paso 3: Commit

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

### Paso 4: Push

```bash
git push origin main
```

Render iniciará auto-deploy automáticamente.

### Paso 5: Monitorear deploy en Render

1. Ir a Render Dashboard → servicio `mi` → pestaña **Events**
2. Esperar mensaje: `Your service is live`  (aprox. 2-3 min desde push)
3. Verificar logs de startup:
   ```
   Aplicando migraciones...
   INFO  [alembic.runtime.migration] Running upgrade ... -> b2c3d4e5f6a7
   Iniciando servidor...
   ```

### Paso 6: Smoke test en producción

```bash
# Verificar docs
curl -s https://mi-2yzi.onrender.com/docs | grep -o "training-sessions"

# Login
TOKEN=$(curl -s -X POST https://mi-2yzi.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"entrenador@trochyruta.com","password":"Coach2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Listar sesiones (debe retornar [])
curl -s -H "Authorization: Bearer $TOKEN" \
  https://mi-2yzi.onrender.com/api/v1/training-sessions | python3 -m json.tool
```

### Paso 7: Verificar migración en DB

Conectarse a la DB de Hostinger y ejecutar:
```sql
SELECT version_num FROM alembic_version;
-- Debe retornar: b2c3d4e5f6a7

SHOW TABLES LIKE '%training%';
-- Debe mostrar: training_sessions, session_attendance

SHOW TABLES LIKE '%monthly%';
-- Debe mostrar: monthly_reports
```

---

## Plan de rollback (si migración falla en Render)

### Opción A: Downgrade Alembic (si la DB migró parcialmente)

1. Conectarse al servicio de Render vía Shell (Dashboard → Shell)
2. Ejecutar:
   ```bash
   alembic downgrade 6e189a7e1e51   # vuelve a antes de coach_observations
   # o para volver a antes del módulo training:
   alembic downgrade f3a4b5c6d7e8
   ```

### Opción B: Revertir el commit en git

```bash
git revert HEAD --no-edit
git push origin main
```
Render re-deployará con el código anterior. Alembic en startup correrá el downgrade automáticamente si el código lo soporta.

> ADVERTENCIA: `alembic downgrade` en producción implica DROP de tablas. Si ya hay
> datos de sesiones guardados, se perderán. Evaluar si hacer backup antes.

### Opción C: Manual fix si hay datos

Si ya hay datos en `training_sessions` y la migración falla a mitad:
1. Corregir el script de migración manualmente
2. Aplicar `alembic stamp <revision>` para marcar el estado actual sin correr migración
3. Contactar soporte Hostinger si hay lock de tabla

---

## Variables de entorno — Auditoría

El módulo training **NO requiere variables de entorno nuevas**. Reutiliza:

| Variable | Uso en módulo training | Estado en Render |
|---|---|---|
| `NOTIFICATION_SEND_EMAILS` | Enviar emails a padres al planificar sesión | Ya configurada |
| `NOTIFICATION_LOG_BODIES` | Debe ser `false` (NUNCA loguear emails con datos atletas) | Ya configurada |
| `EMAIL_PROVIDER` + `RESEND_API_KEY` | Backend de envío email | Ya configurada |
| `EMAIL_FROM_ADDRESS` | `noreply@trochyruta.com` | Ya configurada |
| `APP_ENV` | Controla seed y mock LLM en dev | Ya configurada |

Variables de IA (si se activa LLM real):

| Variable | Descripción | ¿Configurada? |
|---|---|---|
| `OPENAI_API_KEY` o `ANTHROPIC_API_KEY` | Para `monthly_report` use case | Verificar en Render |
| `AI_PROVIDER` | `openai` o `anthropic` | Verificar en Render |

> Si las variables de IA no están configuradas, el endpoint de reporte mensual fallará
> en producción. En `APP_ENV=development` usa mock LLM sin necesidad de API key.
