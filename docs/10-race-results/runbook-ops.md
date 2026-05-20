# Runbook operativo — race-analyst v2 (F8A)

> **Audiencia**: coach, admin, on-call.
> **Alcance**: módulo agéntico race-results v2 (LangGraph + Gemini) en producción.
> **Default MVP**: observabilidad via audit DB (`athlete_ai_insights`, `agent_runs`,
> `agent_run_events`) + endpoint admin `/api/race-analysis/admin/ai-usage`.
> Langfuse self-hosted está diferido a F8B opcional.

---

## 1. Acceso

### 1.1 Render (backend FastAPI)

- URL dashboard: <https://dashboard.render.com>
- Servicio: `mi-2yzi` (Oregon, free tier, Docker).
- Logs en tiempo real: pestaña **Logs** del servicio (búsqueda full-text).
- Shell remoto: pestaña **Shell** (no apto para queries — usar MySQL client).
- Variables sensibles: pestaña **Environment** (todas listadas en
  `CLAUDE.md` del proyecto).

### 1.2 MySQL Hostinger (base de datos)

- Host: ver variable `MYSQL_HOST` en Render env.
- Cliente recomendado: `mysql` CLI o DBeaver con SSL.
- Credenciales: `MYSQL_USER` / `MYSQL_PASS` en Render env.
- Conexión rápida desde local:

  ```bash
  mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p "$MYSQL_DB"
  ```

> Hostinger Shared tiene IP allowlist en algunos planes; si la
> conexión falla con `Host '...' is not allowed`, el coach debe agregar
> la IP saliente desde el panel hPanel → MySQL Remoto.

### 1.3 Render — login

1. Cuenta Render: usar `juadigab@gmail.com` (compartida con admin del proyecto).
2. Si está dormido, primer request del frontend tarda ~50s en cold start.

---

## 2. Métricas clave

### 2.1 Endpoint admin

`GET /api/race-analysis/admin/ai-usage?days=30` — requiere JWT con rol `admin`.

Devuelve:

```json
{
  "window_days": 30,
  "run_count": 24,
  "cost_usd_total": 0.012,
  "latency_ms_p50": 18200,
  "latency_ms_p95": 32100,
  "fail_rate": 0.04,
  "by_prompt_version": [
    {"prompt_version": "race_analyst_v1", "run_count": 24, "cost_usd_total": 0.012}
  ]
}
```

Es la **fuente operativa principal** — coincide con la lógica del
budget guard (ambos leen `metrics_snapshot_json.aggregate.cost_usd_total`).

### 2.2 Queries SQL crudas

Costos y latencias últimos 7 días por run (drill-down):

```sql
SELECT
  generated_at,
  use_case,
  prompt_version,
  JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.cost_usd_total') AS cost_usd,
  JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') AS latency_ms,
  coach_approved
FROM athlete_ai_insights
WHERE generated_at >= NOW() - INTERVAL 7 DAY
ORDER BY generated_at DESC
LIMIT 100;
```

Runs activos / fallidos últimos 7 días:

```sql
SELECT status, COUNT(*) AS n
FROM agent_runs
WHERE started_at >= NOW() - INTERVAL 7 DAY
GROUP BY status;
```

Runs colgados (>30 min sin terminar):

```sql
SELECT external_run_id, status, started_at, requested_by_user_id
FROM agent_runs
WHERE status IN ('running', 'awaiting_hitl')
  AND started_at < NOW() - INTERVAL 30 MINUTE
ORDER BY started_at;
```

Eventos de un run específico (debugging):

```sql
SELECT seq, event_type, node_name,
       JSON_EXTRACT(payload_json, '$.error') AS error
FROM agent_run_events
WHERE run_id = (SELECT id FROM agent_runs WHERE external_run_id = 'XXX')
ORDER BY seq;
```

---

## 3. Alertas comunes

### 3.1 LLM (Gemini) caído

**Síntomas**:
- `fail_rate` en `/ai-usage` > 0.20.
- Logs de Render con muchos `agent run XXX falló: APIError` o similar.

**Diagnóstico**:
1. Verificar status de Google AI: <https://status.cloud.google.com>.
2. Confirmar que `AI_API_KEY` no expiró (Google AI Studio dashboard).
3. Si Google está OK, revisar cuotas (rate limits del modelo `gemini-2.5-flash-lite`).

**Mitigación**:
- **Disable temporal**: setear `AI_ENABLED=false` en Render → Save → auto-redeploy.
  Esto hace que `POST /runs` responda 503 con mensaje "AI no disponible" — el
  coach ve un toast claro y deja de spawn runs que fallarán.
- **Fallback**: el grafo tiene nodo `fallback.py` que genera análisis básico
  determinista si el LLM falla; los runs degradan pero no se pierden.

### 3.2 Run colgado >30 min

**Síntoma**: query del §2.2 devuelve filas.

**Causa común**:
- Worker de FastAPI fue reiniciado (Render redeploy) mientras un run
  estaba activo — el checkpointer LangGraph en SQLite local del worker
  se pierde y no hay continuación.

**Mitigación**:
1. Cancelar manualmente (impacto cero para usuarios — el coach reintenta):

   ```sql
   UPDATE agent_runs
   SET status='cancelled',
       finished_at = NOW(),
       error_message = 'manual cancel: orphaned post-restart'
   WHERE external_run_id = 'XXX' AND status IN ('running', 'awaiting_hitl');
   ```

2. Si pasa frecuentemente, considerar migrar el checkpointer a Redis
   (TODO documentado en `app/services/race/ai/runner.py`).

### 3.3 Eval falla en CI

**Síntoma**: pipeline GitHub Actions con eval framework (F7) en rojo.

**Diagnóstico**:
1. Revisar `evals/race_analyst/results/last_run.md` — muestra qué fixtures
   golden divergieron.
2. Comparar con baseline (commit anterior) para identificar el cambio
   responsable (prompt, weights, model version bump de Gemini).

**Mitigación**:
- Si la divergencia es esperada (mejora intencional): actualizar
  baseline + documentar en PR.
- Si es regresión: revertir el commit del prompt o ajustar.

### 3.4 Costo se dispara — budget guard activo

**Síntoma**:
- Coach reporta error 503 "Presupuesto mensual de IA excedido: $X de $Y".
- Logs de Render contienen `ERROR ... race_ai_budget_exceeded: ...`.

**Diagnóstico**:
1. Confirmar gasto real:

   ```bash
   curl -H "Authorization: Bearer $ADMIN_JWT" \
     "https://mi-2yzi.onrender.com/api/race-analysis/admin/ai-usage?days=30"
   ```
2. Drill-down por prompt_version para ver qué versión consume:
   ver campo `by_prompt_version` del response.

**Mitigación** (en orden de preferencia):
1. **Esperar**: si el gasto se debe a tráfico legítimo y queda poco para
   que la ventana 30d se rotule, simplemente esperar.
2. **Subir el threshold temporalmente**: setear
   `RACE_AI_BUDGET_USD_30D=40` en Render → redeploy (toma ~1 min).
3. **Investigar fuga**: si el costo subió 10x sin más usuarios, revisar:
   - ¿Hay un loop de retries por alguna feature flag?
   - ¿Aumentó `AI_MAX_TOKENS`? (verificar en env var)
   - ¿Un atleta tiene cientos de competidores por GROUP que infla el prompt?

> **Cooldown**: el guard sólo loggea/notifica 1 vez por hora aunque haya
> 100 requests rechazados. Si necesitas resetear el cooldown (debugging),
> reinicia el servicio (`Manual Deploy`).

### 3.5 PII leak detectado

> **Crítico**: datos personales de menores expuestos en cualquier output
> (logs, frontend, email, exports).

**Procedimiento**:
1. **Contención inmediata**: setear `AI_LOG_PROMPTS=false` (debe estar
   en `false` siempre en prod; el validator de Settings lo enforces).
2. **Auditar logs**: descargar logs de Render últimos 7 días y grep por
   patrones de nombre/apellido completo. Borrar logs si Render lo
   permite (free tier no permite delete — escalar a paid si necesario).
3. **Invalidar caché de insights afectados**:

   ```sql
   UPDATE athlete_ai_insights
   SET archived_at = NOW()
   WHERE athlete_id = <ID afectado>;
   ```
4. **Notificar afectados**: contactar al coach + padres del/los atleta(s)
   por canal directo (no email automático — el contenido es sensible).
5. **Post-mortem**: documentar en `docs/10-race-results/` y agregar test
   de regresión que cubra el path del leak.

---

## 4. Restart procedure

### 4.1 Producción (Render)

- **Restart limpio**: Render Dashboard → servicio `mi-2yzi` → Manual Deploy
  → "Deploy latest commit". Tarda ~3-5 min (build + migración Alembic + start).
- **Auto-deploy**: cada push a `main` dispara redeploy automático.
- **Rollback rápido**: Dashboard → Deploys → click en deploy anterior →
  "Redeploy". NOTE: Alembic migrations no se revierten automáticamente
  — si el rollback cruza una migración nueva, hay que `alembic downgrade`
  manualmente vía Shell.

### 4.2 Local (docker compose)

```bash
docker compose down
docker compose up --build
```

`entrypoint.sh` corre `alembic upgrade head` antes de arrancar uvicorn.
En entorno `development` también corre el seed.

---

## 5. Backups

### 5.1 Hostinger MySQL

- **Backup automático**: Hostinger hace backup diario completo de la DB
  (retención 7 días en plan compartido).
- **Restore**: panel hPanel → MySQL → Backups → Restore. ATENCIÓN: el
  restore reemplaza la DB completa.
- **Backup manual antes de cambios críticos**:

  ```bash
  mysqldump -h "$MYSQL_HOST" -u "$MYSQL_USER" -p \
    --single-transaction --quick \
    "$MYSQL_DB" > backup_$(date +%Y%m%d_%H%M).sql
  ```

### 5.2 Criticidad por tabla

| Tabla | Criticidad | Recuperación |
|---|---|---|
| `athlete_ai_insights` | **Alta** — datos para coach + auditoría de IA. | Restore desde backup. |
| `agent_runs` | Media — historial de runs; se puede regenerar (con costo). | Restore + advisorio al coach. |
| `agent_run_events` | **Baja (efímera)** — solo polling/SSE. Crece rápido; archivar/truncate >90d. | No requiere restore. |
| `anonymization_mappings` | Media — borrar = perder traceability. | Restore. |

### 5.3 Tarea recurrente recomendada

Truncate de `agent_run_events` >90 días, mensual:

```sql
DELETE FROM agent_run_events
WHERE created_at < NOW() - INTERVAL 90 DAY;
```

---

## 6. Smoke test post-deploy

Después de cada redeploy en Render, correr smoke E2E (script
`backend/scripts/smoke_test_prod.py`):

```bash
cd backend
source .venv/bin/activate
export RACE_SMOKE_BASE_URL=https://mi-2yzi.onrender.com
export RACE_SMOKE_TOKEN=<jwt-coach>
export RACE_SMOKE_ADMIN_TOKEN=<jwt-admin>

python -m scripts.smoke_test_prod \
  --athlete-id 17 \
  --season 2026
```

Exit codes:
- `0` — OK (run ejecutado + insight persistido + cost_usd > 0).
- `1` — fallo (timeout, error de red, validación, cost==0).

Para `--help` completo: `python -m scripts.smoke_test_prod --help`.

> En local con AI fake (`AI_PROVIDER=fake`), correr con `--skip-cost-check`
> porque el provider mock no acumula costo.

---

## 7. Glosario rápido

- **F8A**: fase 8 opción A — observabilidad audit-only via DB
  (default MVP).
- **F8B**: fase 8 opción B — Langfuse self-hosted (diferido,
  opcional, ver `v2-agentic-design.md`).
- **Budget guard**: módulo `app/services/race/ai/budget_guard.py` que
  bloquea nuevos runs si gasto 30d >= `RACE_AI_BUDGET_USD_30D`.
- **HITL**: Human-In-The-Loop — nodo `hitl_gate_review` que pausa el
  grafo esperando aprobación del coach.
- **Run colgado**: status=`running` o `awaiting_hitl` por >30 min sin
  evento nuevo en `agent_run_events`.
