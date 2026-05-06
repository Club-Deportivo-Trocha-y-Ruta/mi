# Workflow — Capa de IA escalable (Strategy + Factory)

> Ejecutable por equipos de agentes. Cada paso es atómico, tiene tests
> propios y se valida antes de pasar al siguiente.

## Branch de trabajo
`claude/ai-research-scalable-design-RgrCl`

## Equipos de agentes sugeridos
- **fastapi-architect** — Pasos 1-4, 9 (configuración, protocols, providers, factory, dependencies)
- **data-privacy-guard** — Paso 5 (context builder + tests de privacidad), revisión final
- **sports-science-advisor** — Paso 6, 7 (guardrails + system_principles + plantilla PHV)
- **fastapi-architect** + **data-privacy-guard** — Paso 8, 10 (use case + router)

## Reglas
1. Un único PASO `in_progress` a la vez (TodoWrite).
2. Cada paso termina con `pytest backend/tests/test_ai_*.py -v` en verde.
3. Sin commits intermedios — un solo commit final por aprobación del usuario.
4. Privacidad: ningún test ni código emite datos de menores en logs.

---

## PASO 0 — Andamiaje

**Crear:**
- `backend/app/services/ai/{,providers/,prompts/,use_cases/}__init__.py`

**Modificar:**
- `backend/requirements.txt` — añadir `anthropic>=0.40` y `jinja2>=3.1`
- `backend/.env.example` — bloque `# === IA / LLMs ===`

**Verificar:** `python -c "from app.services import ai"`

---

## PASO 1 — Núcleo: models, errors, protocols

**Crear:**
- `backend/app/services/ai/models.py` — `LLMMessage`, `LLMRequest`, `LLMResponse`, `TokenUsage` (dataclasses)
- `backend/app/services/ai/errors.py` — `LLMError`, `LLMTimeoutError`, `LLMUnavailableError`, `LLMSchemaError`, `LLMConfigError`
- `backend/app/services/ai/protocols.py` — `ChatCompletion`, `StructuredOutput`, `LLMProvider` (Protocol)

**Tests:** `backend/tests/test_ai_models.py`
- Construcción válida de `LLMRequest` / `LLMResponse`.
- Validación de roles permitidos en `LLMMessage`.
- Errores son subclase de `LLMError`.

**Verificar:** `pytest backend/tests/test_ai_models.py -v`

---

## PASO 2 — Configuración

**Modificar:**
- `backend/app/config.py` — bloque IA con validators (provider permitido, api_key requerida en prod, log_prompts prohibido en prod).
- `backend/.env.example`

**Tests:** `backend/tests/test_ai_config.py`
- Settings con `AI_ENABLED=false` instancia OK sin api_key.
- `AI_PROVIDER` inválido → `ValueError`.
- En `production` con `ai_enabled=true` y sin `ai_api_key` → `ValueError`.
- En `production` con `ai_log_prompts=true` → `ValueError`.

**Verificar:** `pytest backend/tests/test_ai_config.py -v`

---

## PASO 3 — Providers (Strategy)

**Crear:**
- `backend/app/services/ai/providers/base.py` — `_BaseProvider` con logging tokens/latencia y `_safe_call()` con timeout.
- `backend/app/services/ai/providers/fake.py` — `FakeLLMProvider` determinístico para tests.
- `backend/app/services/ai/providers/anthropic_provider.py` — `AnthropicProvider` con `AsyncAnthropic`, importación lazy del SDK.

**Tests:** `backend/tests/test_ai_providers.py`
- `FakeLLMProvider.complete()` devuelve respuesta determinística.
- `FakeLLMProvider.complete_json()` devuelve dict válido.
- `FakeLLMProvider` registra prompts recibidos para inspección.
- `AnthropicProvider` se construye sin error (sin llamar a la API real).

**Verificar:** `pytest backend/tests/test_ai_providers.py -v`

---

## PASO 4 — Factory

**Crear:**
- `backend/app/services/ai/factory.py` — `create_llm_provider(settings) -> LLMProvider`.

**Tests:** `backend/tests/test_ai_factory.py`
- Cada valor permitido instancia el provider correcto.
- `AI_ENABLED=false` → `FakeLLMProvider`.
- `AI_PROVIDER` no soportado → `LLMConfigError`.

**Verificar:** `pytest backend/tests/test_ai_factory.py -v`

---

## PASO 5 — AthleteAIContextBuilder (privacidad)

**Crear:**
- `backend/app/services/ai/context_builders.py` — clase pura, allowlist explícita.

**Tests:** `backend/tests/test_ai_context_builder_privacy.py` ⚠ **bloqueante**
- Resultado contiene solo claves de la allowlist.
- Nunca contiene `first_name`, `last_name`, `birth_date` exacta, `email`, `id`.
- Se cubre rama sin mediciones, con 1, con 3 (cálculo de tendencia).

**Verificar:** `pytest backend/tests/test_ai_context_builder_privacy.py -v`

---

## PASO 6 — Guardrails

**Crear:**
- `backend/app/services/ai/guardrails.py` — `Guardrails.scrub(text)`.

**Tests:** `backend/tests/test_ai_guardrails.py`
- "suplemento", "creatina", "proteína en polvo" → reemplazo / log.
- "6 días/semana", "7 días/semana" → reemplazo a "máx 5 días".
- Cadencia "55 rpm" → corregida a "≥60 rpm".
- "potenciómetro" en grupo 10-12 → eliminada.

**Verificar:** `pytest backend/tests/test_ai_guardrails.py -v`

---

## PASO 7 — PromptRegistry

**Crear:**
- `backend/app/services/ai/prompts/registry.py` — `PromptRegistry`, `PromptSpec`.
- `backend/app/services/ai/prompts/system_principles.md` — principios no negociables.
- `backend/app/services/ai/prompts/phv_explainer.j2` — plantilla para padres.

**Tests:** `backend/tests/test_ai_prompt_registry.py`
- `system_prompt()` carga el `.md` y contiene los 9 principios.
- `validate_context()` falla con claves faltantes.
- `render()` produce el texto esperado con contexto válido.

**Verificar:** `pytest backend/tests/test_ai_prompt_registry.py -v`

---

## PASO 8 — PHVExplainerUseCase

**Crear:**
- `backend/app/services/ai/use_cases/base.py` — `BaseUseCase` (abstracto, define `run()`).
- `backend/app/services/ai/use_cases/phv_explainer.py` — `PHVExplainerUseCase`.

**Tests:** `backend/tests/test_ai_phv_explainer.py`
- Use case con `FakeLLMProvider` devuelve texto.
- El system prompt enviado contiene los principios no negociables.
- El user message no incluye PII (verificar en `FakeLLMProvider.last_request`).
- Output con violación detectada por guardrails es saneado.

**Verificar:** `pytest backend/tests/test_ai_phv_explainer.py -v`

---

## PASO 9 — Dependencies FastAPI

**Modificar:**
- `backend/app/dependencies.py` — `get_llm_provider`, `get_prompt_registry`, `get_phv_explainer_use_case` (siguiendo el patrón de `get_notification_service`).

**Tests:** `backend/tests/test_ai_dependencies.py`
- `get_llm_provider()` devuelve singleton (mismo objeto en dos llamadas).
- `get_phv_explainer_use_case()` resuelve correctamente la dependencia.

**Verificar:** `pytest backend/tests/test_ai_dependencies.py -v`

---

## PASO 10 — Router `/api/ai/`

**Crear:**
- `backend/app/schemas/ai.py` — `PHVExplanationResponse`, `AIHealthResponse`.
- `backend/app/routers/ai.py` — endpoints PHV explanation y health.

**Modificar:**
- `backend/app/main.py` — registrar router.

**Tests:** `backend/tests/test_ai_router.py`
- `GET /api/ai/health` con admin → 200 `{enabled, provider, model}`.
- `POST /api/ai/athletes/{id}/phv-explanation` con coach → 200.
- Sin auth → 401. Parent sin acceso al atleta → 403. Atleta sin mediciones → 422.
- Con `AI_ENABLED=false` → 503.

**Verificar:** `pytest backend/tests/test_ai_router.py -v`

---

## PASO 11 — Verificación end-to-end y commit

```bash
cd backend
pytest tests/test_ai_*.py -v --tb=short
pytest tests/ -v -k "not test_ai_" -x  # asegurar sin regresión
```

Commit y push solo si todos los pasos están en verde.

---

## Mapa de fases siguientes (post-MVP)

| Fase | Use case | Endpoint |
|---|---|---|
| 2 | `GrowthSpurtAnalyzerUseCase` | `POST /api/ai/athletes/{id}/growth-spurt-analysis` |
| 2 | `MonthlySummaryUseCase` | `POST /api/ai/athletes/{id}/monthly-summary` |
| 3 | `TrainingSessionDrafterUseCase` (StructuredOutput) | `POST /api/ai/training-sessions/draft` |
| 3 | `WeeklyAdaptationAdvisorUseCase` | `POST /api/ai/weekly-adaptation` |
| 4 | `CoachQAUseCase` (RAG sobre marco-teórico) | `POST /api/ai/coach-qa` |
| 4 | `PostRaceParentUseCase` | `POST /api/ai/post-race-comm/{race_id}` |
| 4 | `OpenAIProvider`, `GoogleProvider` | (demuestra OCP) |
