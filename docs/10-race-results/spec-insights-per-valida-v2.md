# Spec — Análisis IA per-válida v2 (Race Insights)

## 1. Metadatos

| Campo | Valor |
|---|---|
| Versión | v2 |
| Estado | Aprobado |
| Owner | `product-manager` |
| Aprobador (coach) | Juan Diego (Trocha y Ruta) |
| Fecha aprobación | 2026-05-25 |
| Fase | 1.9 — Análisis IA per-válida |
| Feature flag | n/a — siempre activo (gate único: `AI_ENABLED`) |
| Reemplaza | Análisis v1 (narrativa global única replicada en N filas) |
| Dependencias internas | Task #4 `head-coach` (guardrails y veto), Task #3 `data-platform` (schema, scrubbing, política privacidad), Task #5 `family-relations` (email parent, label) |
| Documentos relacionados | `docs/10-race-results/runbook-v2.md` (devops-engineer), `backend/app/services/race/prompts/race_analyst_v2.md` (fastapi-architect) |
| Memoria PM | `~/.claude/agent-memory/product-manager/project_race_analysis_v2_spec.md` |

## 2. Problema

La v1 generó una narrativa global única por análisis y la replicó como `analysis_text` en las N filas de `athlete_ai_insight` correspondientes a las N válidas del atleta. Consecuencias observadas:

- En la UI del coach, los 5 previews de un atleta mostraban texto idéntico, confundiendo al usuario sobre qué válida estaba viendo.
- El modelo de datos viola 1NF: el mismo string narrativo se almacena duplicado N veces, complicando ediciones puntuales (corregir un análisis de la Válida III obliga a reescribir las 5 filas).
- La narrativa única no podía a la vez describir cada evento, sintetizar tendencia longitudinal y proyectar hacia adelante: terminó siendo o demasiado genérica o sesgada hacia la última válida.
- El boletín mensual a padres (Fase 1.8) y el dashboard del coach quedaron acoplados a una narrativa no especializable por audiencia ni por foco temporal.

## 3. Decisión

Cada análisis IA per-atleta producirá, por cada válida cubierta en el run, **3 secciones independientes** y, opcionalmente, **1 resumen de temporada** generado on-demand:

1. **Qué pasó (Válida N)** — descriptivo del evento N.
2. **Recorrido hasta acá** — análisis tendencial V1 → N.
3. **Hacia dónde va** — prescripción accionable para válidas N+1 a fin de temporada.
4. **Resumen temporada** — síntesis ejecutiva, generada solo a petición explícita (no en cada run).

Las 4 filas existentes en `athlete_ai_insight` por atleta-temporada se conservan; cada fila almacenará las 3 secciones en columnas/JSON discretos (no refactor de schema — ver §10).

## 4. Contrato por sección

| Sección | Max palabras | Tono | Foco temporal | Prohibiciones |
|---|---|---|---|---|
| Qué pasó (válida N) | 120 | Descriptivo, objetivo | Solo evento N | Adjetivos valorativos, comparaciones entre atletas, usar "la deportista" en vez del pseudónimo |
| Recorrido hasta acá | 120 | Analítico tendencial | V1 → N | Ranking absoluto ("está N° X"), "rivaliza con", lenguaje competitivo entre atletas |
| Hacia dónde va | 120 | Prescriptivo accionable | N+1 a fin de temporada | "Objetivo podio", prescribir intervalos para <13 años, cualquier frase de la lista de veto duro (§7) |
| Resumen temporada (on-demand) | 200 | Síntesis ejecutiva | Toda la temporada | Nombres reales, comparativa entre atletas del club |

Todas las secciones aplican además los guardrails globales: sin nombres reales (usar pseudónimo `forbidden_names`), sin términos médicos sin contexto, sin recomendaciones nutricionales para menores, sin promesas de resultado.

## 5. Criterios de aceptación

| ID | Criterio | Cómo se mide |
|---|---|---|
| CA-1 | 0 narrativas idénticas entre las 3 secciones de una misma válida | `hash(text)` distinto en las 3 secciones; assertion en test de integración por cada run |
| CA-2 | 0 narrativas con similaridad ≥0.85 entre "Qué pasó" de válidas distintas del mismo análisis | Levenshtein normalizado por longitud sobre pares de secciones del mismo análisis |
| CA-3 | 100% de secciones respetan `max_words + 10%` | Conteo de palabras post-render; truncado o regeneración si excede |
| CA-4 | 0 ocurrencias de nombre real en cualquier sección | Regex contra `forbidden_names` dinámicos cargados de DB en el momento del run |
| CA-5 | "Hacia dónde va" contiene ≥1 verbo accionable (priorizar/reducir/mantener/incorporar/ajustar/consolidar) y ≥1 referencia al marco teórico (`docs/01-marco-teorico.md`) | Lint post-generación |
| CA-6 | "Recorrido hasta acá" referencia ≥N-1 válidas previas cuando N≥2 | Conteo de menciones explícitas a "Válida I/II/III/..." |
| CA-7 | p95 tiempo de análisis ≤25s en Render Free (4 válidas, 1 atleta) | Métrica en Langfuse + dashboard runbook |
| CA-8 | Guardrails del Head Coach aprobados (sample 5 análisis) | Visto bueno documentado por `head-coach` en `project_race_analysis_v2_spec.md` |
| CA-9 | Política de privacidad aprobada por Data Platform (scrubbing 180d, `pii_scrubbed_at`) | Visto bueno documentado por `data-platform` |
| CA-10 | Coach valida sample de 5 análisis pre-rollout GA | Checklist firmado por Juan Diego antes de Etapa 3 |

## 6. Cap 4 válidas por run

Cada análisis cubre **máximo 4 válidas por ejecución**, independientemente de cuántas válidas tenga la temporada del atleta.

**Justificación**:
- Cuota Gemini (`gemini-2.5-flash-lite`) en tier gratuito: la suma de tokens de prompt (estadísticas + contexto + 4 secciones objetivo) y respuesta (≈ 480 palabras + JSON envoltorio por válida) se ajusta dentro de `AI_MAX_TOKENS=8192` sin truncar.
- p95 ≤25s en Render Free solo se cumple con ≤4 válidas concurrentes en el grafo agentico.
- Si la temporada tiene >4 válidas cubiertas, el coach selecciona explícitamente cuáles entran en el run; el resto queda con la versión previa y puede regenerarse en un segundo run.

## 7. Frases de veto duro (lista literal cerrada)

Lista cerrada; cualquier ampliación requiere nueva versión del prompt (`prompt_version`). Si el modelo emite cualquiera de estas frases (matching case-insensitive y normalizado), se invalida el output de la sección y se regenera (máx 1 retry):

- "debe ganar"
- "tiene que llegar al podio"
- "necesita más horas"
- "más intensidad"
- "trabajo de potencia para superar a"

## 8. Plan de rollout (4 etapas)

v2 se despliega como always-on (sin feature flag). Rollback de emergencia: redeploy del binario anterior en Render Dashboard (ver `runbook-v2.md` §1). Si falla CA-4 (nombre real) en producción: rollback inmediato + post-mortem.

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Cuota Gemini agotada en horas pico | Cap 4 válidas/run + cola serializada por club + alerta cuando uso mensual supere 70% |
| Timeout asyncio en grafo agentico bajo carga | Timeout duro 30s por nodo + circuit breaker en `race_analyst_v2` |
| Loop infinito al regenerar por veto duro | Máx 1 retry por sección; si falla, marcar sección como `manual_review` y notificar coach |
| Migración no compatible con MySQL Hostinger 8.4 | Probar migración en clon de prod antes de Etapa 2; rollback script preparado |
| UI de padre muestra badge "v2" por error | El label visible al padre es siempre "Análisis del coach" — el badge `prompt_version` es interno y no se serializa en endpoints parent |
| Regresión silenciosa de v1 al desplegar v2 | Pruebas de contrato sobre filas v1 leídas (no escritas) durante Etapa 4 |
| `forbidden_names` con regex laxa que deje pasar variantes (mayúsculas/acentos/diminutivos) | Normalización Unicode + lista expandida con apodos conocidos cargada desde DB en cada run |

## 10. No-objetivos

- **NO** comparativa entre atletas del club en ninguna sección.
- **NO** gráficos generados por IA — se reutilizan las macros SVG ya implementadas (Fase 1.8).
- **NO** versión "para padres" del análisis: la comunicación a padres vive en el boletín mensual (Fase 1.8) con narrativa propia.
- **NO** refactor de schema `athlete_ai_insight` en este alcance: las 4 filas por atleta-temporada se mantienen; las 3 secciones viven en columnas/JSON dentro de cada fila.
- **NO** ampliar la lista de veto duro sin bump de `prompt_version`.
- **NO** envío de email parent fuera de válidas A (IV, CD, VI).

## 11. Comunicación a familias

- Email parent: se dispara únicamente para válidas **A** del calendario 2026 (IV Cali 17-may, CD Ginebra 12-jun, VI Roldanillo 12-sep).
- Label visible al padre: **"Análisis del coach"** (nunca "Análisis IA", nunca el badge `prompt_version`).
- Cualquier identificador interno (`prompt_version=race_analyst_v2`, IDs de run de Langfuse) se mantiene fuera de los payloads del rol parent.

## 12. Referencias cruzadas

- Runbook operacional: `docs/10-race-results/runbook-v2.md` (owner `devops-engineer`).
- Prompt de sistema y few-shots: `backend/app/services/race/prompts/race_analyst_v2.md` (owner `fastapi-architect`).
- Decisiones consolidadas del PM: `~/.claude/agent-memory/product-manager/project_race_analysis_v2_spec.md`.
- Marco teórico (citas para "Hacia dónde va"): `docs/01-marco-teorico.md`.
- Boletín mensual (audiencia padres): `docs/` Fase 1.8, módulo `AthleteMonthlyNewsletter`.

## 13. Calendario de implementación

Fase 1.9 — Análisis IA per-válida. Arranque tras aprobación del spec; secuencia dependerá del workflow generado por `fastapi-architect` y `devops-engineer` con base en este documento.
