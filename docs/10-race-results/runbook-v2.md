# Runbook v2 — race-analyst agentico (operacion, retencion)

> **Audiencia**: coach, admin, on-call.
> **Alcance**: cap operativo, monitoreo cuota Gemini, rollback via redeploy
> y job de retencion 180d post `deprecated_at`.
> Complementa al runbook operativo `runbook-ops.md` (alertas/metricas en vivo).

---

## 1. Activacion y operacion

v2 esta **siempre activo** (sin feature flag). El unico gate es `AI_ENABLED`
(ya existente para todos los modulos IA).

Cap operativo (acordado con engineering-lead):

- Maximo **4 validas/run** -> hasta **12 LLM calls + 1 season summary** por analisis.
- Encuadra costo esperado y permite proyectar cuota Gemini.

### Rollback de emergencia

Disparador: error 5xx > 5% en endpoints v2, costo Gemini disparado, PII leak.

- Render Dashboard -> pestana **Deploys** -> click en el deploy
  anterior estable -> **Redeploy**. Restaura el binario sin esperar build.
- Para deshabilitar IA en general (incluye v1 y v2): set `AI_ENABLED=false`
  en Environment -> Save -> auto-redeploy (~3-5 min).
- Tras rollback documentar incidente en `docs/10-race-results/` y avisar
  a engineering-lead.

> Rollback **no** borra filas en `athlete_ai_insights`. Si una fila
> publicada es problematica, marcar `archived_at = NOW()` desde MySQL
> (mismo procedimiento de `runbook-ops.md` seccion 3.5).

---

## 2. Monitoreo cuota Gemini

### 2.1 Donde mirar

- Google AI Studio dashboard: <https://aistudio.google.com/app/apikey>
  -> seleccionar la API key del proyecto -> "Usage".
- Filtrar por modelo `gemini-2.5-flash-lite` (es el unico que usa el
  modulo race-analyst v2; cualquier consumo de otro modelo es anomalia).

### 2.2 Limites tier free Gemini (referencia)

| Modelo | RPM | RPD | Tokens/dia |
|---|---|---|---|
| `gemini-2.5-flash-lite` | 15 | 1500 | 1M |

> Valores de la consola al 2026-05-25. **Confirmar en consola antes de
> dimensionar** porque Google ajusta cuotas periodicamente.

### 2.3 Estimacion vs cap operativo

- 1 analisis completo = max 12 + 1 = **13 calls**.
- Con 1500 RPD libre teorico, eso son **~115 analisis/dia** antes de
  topar limite del free tier.
- **El gate practico es el budget guard** (`RACE_AI_BUDGET_USD_30D`,
  ver `runbook-ops.md` seccion 3.4), no la cuota Gemini per se.

### 2.4 Alerta operativa: 80% de cuota

**Disparador**: consumo diario supera **1200 calls / dia** (80% de 1500
en tier free) **durante 2 dias consecutivos**.

**Accion**:

1. Revisar `/ai-usage` (drill-down por `prompt_version`) — ver si hay
   regresion o feature nueva consumiendo de mas.
2. Cap temporal: bajar `RACE_AI_BUDGET_USD_30D` para frenar nuevas
   ejecuciones, o reducir allowlist canary.
3. Si el consumo es legitimo y sostenido: **plan migracion a tier pago
   Gemini** ("Pay-as-you-go") — coordinar con engineering-lead. El cambio
   se hace en Google Cloud Console; la API key existente funciona,
   solo cambia la facturacion.
4. Post-migracion, subir `AI_MAX_TOKENS` si hace falta y documentar
   nuevo costo unitario en `runbook-ops.md` seccion 3.4.

### 2.5 Polling manual rapido

```bash
curl -H "Authorization: Bearer $ADMIN_JWT" \
  "https://mi-2yzi.onrender.com/api/race-analysis/admin/ai-usage?days=7"
```

Si `run_count` x 13 calls/dia se acerca a 1200, alerta.

---

## 3. Retencion 180d post `deprecated_at`

### 3.1 Politica

- Filas en `athlete_ai_insights` con `deprecated_at` (insight superado
  por una version mas reciente) conservan su contenido por **180 dias**
  para auditoria.
- A los 180 dias el script `retention_ai_insights.py` redacta el campo
  `summary_text` y marca `pii_scrubbed_at = NOW()` (idempotente: filas
  ya scrubeadas se ignoran).
- Las filas **no se borran** — quedan registros de "que se publico y
  cuando", con su contenido textual ofuscado.

### 3.2 Script

`backend/scripts/retention_ai_insights.py` (CLI Typer).

**Dry-run (default, seguro)**:

```bash
cd backend
source .venv/bin/activate
python -m scripts.retention_ai_insights
```

Imprime tabla de filas que se redactarian (sin ejecutar UPDATE).

**Aplicar**:

```bash
python -m scripts.retention_ai_insights --apply
```

Idempotente: filtra por `pii_scrubbed_at IS NULL`, asi correrlo dos
veces no doble-redacta.

**Override del threshold (debugging)**:

```bash
# Forzar 90d en vez de 180d (uso interno, no operativo):
python -m scripts.retention_ai_insights --days 90 --apply
```

### 3.3 Programacion (Render Free no tiene cron nativo)

Render Free tier no expone cron jobs. Tres opciones, en orden de
preferencia operativa:

**A. GitHub Actions schedule (recomendado)**

Workflow `.github/workflows/retention-cron.yml` con `schedule: cron: '0 5 1 * *'`
(mensual, primer dia 05:00 UTC) que:

1. Checkout del repo.
2. Setup Python + venv.
3. Lee secret `DATABASE_URL` desde GitHub Secrets.
4. Corre `python -m scripts.retention_ai_insights --apply`.

> A definir cuando engineering-lead apruebe el workflow. Requiere
> agregar `MYSQL_*` o `DATABASE_URL` como GitHub Secrets.

**B. Endpoint admin protegido**

Exponer `POST /api/race-analysis/admin/retention/run` (RBAC admin)
que importe el script como funcion. Disparado desde cron externo
(cron-job.org, uptime monitor). Ventaja: no expone credenciales DB
fuera de Render. Desventaja: requiere desarrollo backend adicional.

**C. Manual mensual**

Coach o devops corre el script desde su maquina con credenciales
del .env de produccion el primer dia de cada mes. Aceptable como
puente hasta que A o B esten implementados. Anotar en bitacora cada
corrida.

### 3.4 Validacion post-corrida

```sql
-- Filas elegibles que aun no fueron scrubeadas (deberia ser 0
-- inmediatamente despues de --apply):
SELECT COUNT(*)
FROM athlete_ai_insights
WHERE deprecated_at < NOW() - INTERVAL 180 DAY
  AND pii_scrubbed_at IS NULL;

-- Filas scrubeadas recientemente (verifica que el job corrio):
SELECT id, athlete_id, deprecated_at, pii_scrubbed_at
FROM athlete_ai_insights
WHERE pii_scrubbed_at >= NOW() - INTERVAL 1 DAY
ORDER BY pii_scrubbed_at DESC
LIMIT 20;
```

---

## 4. Checklist rapido por situacion

| Situacion | Pasos |
|---|---|
| Activar v2 para 1 atleta canary | Env -> `V2_ENABLED=true`, `V2_ATHLETE_ALLOWLIST=<id>` -> Save -> smoke -> avisar coach |
| Quitar atleta del canary | Editar CSV en `V2_ATHLETE_ALLOWLIST` removiendo el id -> Save |
| Rollback emergencia | `V2_ENABLED=false` o redeploy del deploy anterior estable |
| Cuota Gemini 80% | Revisar `/ai-usage`, bajar `RACE_AI_BUDGET_USD_30D`, plan migrar a tier pago |
| Retencion mensual | `python -m scripts.retention_ai_insights --apply` (o esperar a cron) |
| PII leak | Ver `runbook-ops.md` seccion 3.5 — protocolo separado |

---

## 5. Referencias

- `runbook-ops.md` — alertas, queries y procedimientos generales.
- `v2-agentic-design.md` — diseno tecnico del pipeline LangGraph.
- `backend/scripts/retention_ai_insights.py` — script de retencion.
- `backend/app/models/athlete_ai_insight.py` — modelo con
  `deprecated_at`, `pii_scrubbed_at`, `summary_text`.
- Google AI Studio: <https://aistudio.google.com/app/apikey>.
