# Race Results v2 — Rediseño Agéntico

**Proyecto:** Club Deportivo Trocha y Ruta — XCO juvenil
**Módulo:** `services/race/` (Fase 1.7 → 1.8)
**Fecha:** 2026-05-20
**Autor:** System Architect agent
**Estado:** Diseño técnico — pendiente aprobación coach
**Audiencia:** entrenador (operación), arquitecto/dev (implementación)

---

## 1. Resumen ejecutivo

### 1.1 Problema

La v1 de race-results (Fase 1.7) entrega un pipeline determinista CLI-only que ingesta PDFs oficiales Copa Valle, normaliza nombres/clubes, persiste resultados en MySQL y expone cuatro analíticas tabulares (`athlete_progression`, `podium_gap`, `club_ranking`, `projection`). Funciona — pero **el entrenador todavía traduce los DataFrames a narrativa** y compara mentalmente cada métrica con principios LTAD del marco teórico. El bottleneck no es el cómputo, es la interpretación.

### 1.2 Solución

Rediseño **híbrido determinista + agéntico**:

- **Capa determinista (intacta):** parsing, normalización, matching, ingest, queries analíticas. Los 339 tests verdes se preservan.
- **Capa agéntica (nueva):** un workflow **LangGraph** orquesta los pasos cualitativos — anonimización, retrieval del marco teórico, llamada LLM con memoria por atleta, gates HITL para revisión del coach, persistencia de insights y notificación. La salida es un dashboard markdown renderizado + PDF descargable + chat consultivo.
- **UI nueva:** ruta `/coach/race-analysis` en el SPA React 19 existente. Polling cada 2 segundos vía **TanStack Query**.
- **Observability:** **Langfuse self-hosted** (Postgres + ClickHouse + server) capturando cada trace, costo, latencia y prompt version.
- **Eval:** golden dataset versionado + LLM-as-judge, bloqueante en CI antes de promover cambios de prompt.

### 1.3 Decisiones cerradas (resumen)

| # | Decisión | Valor |
|---|---|---|
| 1 | Modo | Híbrido: determinista para ETL, agéntico para análisis |
| 2 | Framework agente | LangGraph 1.2.x + Langfuse self-hosted |
| 3 | LLM | Google Gemini 2.5 Flash Lite via `langchain-google-genai` |
| 4 | UI | React 19 + shadcn dentro del SPA actual, ruta `/coach/race-analysis` |
| 5 | Streaming | Polling HTTP cada 2s → TanStack Query con refetchInterval |
| 6 | Memoria | Tabla `athlete_ai_insights` (recall N=3) |
| 7 | Privacy | Anonimización determinista antes del LLM, re-hidratación en frontend |
| 8 | HITL | Gates en parse-quality, match TyR <85, antes de email |
| 9 | Output | Dashboard md + PDF (weasyprint) + chat — sin email a padres en MVP |
| 10 | Eval | Golden dataset + LLM-as-judge bloqueante en CI |
| 11 | Modo aprendizaje | Toggle global, mensajes pedagógicos por nodo |
| 12 | Refactor | In-place, strangler-fig dentro de `services/race/` |
| 13 | RAG | ChromaDB local sobre `docs/01-marco-teorico.md` |
| 14 | Notificación | Resend email al coach al terminar análisis |
| 15 | Prompts | Archivos `.md` versionados en git, render con Jinja2, PR review obligatorio |

### 1.4 ROI estimado (asunciones)

Asunción: el coach hoy invierte ~45-60 min por válida (4-5 atletas × 10 min de análisis manual cruzando 4 dashboards).

| Métrica | Hoy (v1 CLI) | Meta v2 | Δ |
|---|---|---|---|
| Tiempo por atleta análisis cualitativo | 10-12 min | 1-2 min (review HITL) | -85 % |
| Tiempo por válida (5 atletas) | 50-60 min | 8-12 min | -80 % |
| Trazabilidad decisiones | ninguna | Langfuse + `athlete_ai_insights` | +∞ |
| Reutilización contexto entre válidas | manual | automática (memoria) | +∞ |
| Calidad pedagógica para el coach | depende | modo `explain` integrado | nuevo |
| Riesgo violación principios LTAD | medio (mente del coach) | bajo (guardrails + RAG) | ↓ |

Costo Gemini Flash Lite estimado: ~USD 0.002 por análisis de atleta (input ~3k tokens, output ~1.2k). 7 válidas × 8 atletas × 4 corridas/temporada ≈ **USD 0.45/temporada**. Despreciable.

### 1.5 Diagrama de alto nivel

```mermaid
flowchart LR
    subgraph "Coach"
        UI["React 19 SPA<br/>/coach/race-analysis"]
    end
    subgraph "Backend FastAPI"
        ROUTER["routers/race_analysis.py<br/>(polling endpoints)"]
        GRAPH["LangGraph<br/>(state machine)"]
        DET["Capa v1 determinista<br/>(pdf_parser, ingestor, analytics)"]
        RAG["ChromaDB<br/>marco-teorico"]
        MEM["athlete_ai_insights<br/>(MySQL)"]
        ANON["anonymization_mapping<br/>(in-memory + audit)"]
    end
    subgraph "LLM Provider"
        LLM["Gemini 2.5 Flash Lite<br/>via langchain-google-genai"]
    end
    subgraph "Observability"
        LF["Langfuse self-hosted<br/>(Postgres + ClickHouse)"]
    end
    subgraph "Storage"
        DB[(MySQL Hostinger)]
    end

    UI -->|HTTP polling cada 2s| ROUTER
    UI -->|HITL approvals POST| ROUTER
    ROUTER --> GRAPH
    GRAPH --> DET
    DET --> DB
    GRAPH --> RAG
    GRAPH --> MEM
    MEM --> DB
    GRAPH --> ANON
    GRAPH -->|prompts + datos anonimizados| LLM
    GRAPH -.tracing.-> LF
    LLM -.cost + latency.-> LF
    GRAPH -->|email Resend| UI
```

---

## 2. Arquitectura del sistema completo

### 2.1 Diagrama de capas (Mermaid detallado)

```mermaid
flowchart TB
    classDef ui fill:#e0f2fe,stroke:#0284c7
    classDef api fill:#ecfeff,stroke:#06b6d4
    classDef agent fill:#fef3c7,stroke:#d97706
    classDef tools fill:#dcfce7,stroke:#16a34a
    classDef data fill:#fce7f3,stroke:#db2777
    classDef obs fill:#ede9fe,stroke:#7c3aed

    subgraph BROWSER ["Browser — React 19 + shadcn"]
        DASH["RaceAnalysisDashboard"]:::ui
        TIMELINE["AnalysisRunTimeline<br/>(consume polling)"]:::ui
        HITL_UI["HITLApprovalCard"]:::ui
        REPORT["MarkdownReportViewer"]:::ui
        CHAT["ChatConsole"]:::ui
        EXPLAIN["ExplainModeBanner"]:::ui
    end

    subgraph FASTAPI ["FastAPI — routers/race_analysis.py"]
        EP_POST["POST /runs"]:::api
        EP_STATUS["GET /runs/{id}/status (polling)"]:::api
        EP_HITL["POST /runs/{id}/hitl/{step}"]:::api
        EP_CHAT["POST /chat"]:::api
        EP_PDF["GET /runs/{id}/pdf"]:::api
        EP_INSIGHTS["GET /athletes/{id}/insights"]:::api
    end

    subgraph LANGGRAPH ["LangGraph state machine"]
        N1[validate_input]:::agent
        N2[load_race_data]:::agent
        N3[anonymize]:::agent
        N4[compute_metrics]:::agent
        N5[retrieve_principles<br/>RAG]:::agent
        N6[recall_memory]:::agent
        N7["analyst_agent<br/>(LLM)"]:::agent
        N8["critic_agent<br/>(LLM, opcional)"]:::agent
        N9[hitl_gate_review]:::agent
        N10[persist_insight]:::agent
        N11[rehydrate_names]:::agent
        N12[render_outputs]:::agent
        N13[notify_coach]:::agent
        CKPT[(SqliteSaver<br/>checkpoint)]:::data
    end

    subgraph TOOLS ["Tools y helpers (sin LLM)"]
        QUERIES["queries.py<br/>(extraídas de analytics)"]:::tools
        ANON_SVC["anonymizer.py<br/>(pseudonyms)"]:::tools
        RAG_SVC["rag/retriever.py<br/>(ChromaDB)"]:::tools
        MEM_SVC["memory/insights.py"]:::tools
        PDF_REND["pdf_renderer.py<br/>(weasyprint)"]:::tools
        EMAIL["notification/sender.py<br/>(Resend)"]:::tools
        V1["v1 services<br/>(pdf_parser, ingestor)"]:::tools
    end

    subgraph DATA ["Persistencia"]
        MYSQL[(MySQL Hostinger<br/>race_* + athlete_ai_insights + agent_runs)]:::data
        CHROMA[(ChromaDB<br/>./data/chroma)]:::data
    end

    subgraph OBS ["Observability"]
        LF_HOST["Langfuse server<br/>(:3001)"]:::obs
        LF_PG[(Langfuse Postgres)]:::obs
        LF_CH[(ClickHouse)]:::obs
    end

    DASH --> EP_POST
    DASH --> EP_STATUS
    TIMELINE -.polling 2s.-> EP_STATUS
    HITL_UI --> EP_HITL
    CHAT --> EP_CHAT
    REPORT --> EP_PDF
    DASH --> EP_INSIGHTS

    EP_POST --> N1
    EP_HITL -.resume.-> CKPT
    EP_CHAT --> RAG_SVC
    EP_CHAT --> MEM_SVC

    N1 --> N2 --> N3 --> N4 --> N5 --> N6 --> N7 --> N8 --> N9
    N9 -->|approved| N10
    N9 -->|edit| N7
    N9 -->|reject| N13
    N10 --> N11 --> N12 --> N13
    LANGGRAPH <-.checkpoint.-> CKPT

    N2 --> QUERIES
    N3 --> ANON_SVC
    N5 --> RAG_SVC
    N6 --> MEM_SVC
    N7 --> LF_HOST
    N10 --> MEM_SVC
    N12 --> PDF_REND
    N13 --> EMAIL

    QUERIES --> MYSQL
    MEM_SVC --> MYSQL
    RAG_SVC --> CHROMA
    V1 --> MYSQL

    LF_HOST --> LF_PG
    LF_HOST --> LF_CH
```

### 2.2 Stack consolidado (versiones mínimas)

> Versiones validadas con Context7 (mayo 2026) y release notes de cada proyecto. Pin con `>=` permite minor updates compatibles.

| Capa | Tech | Versión mínima | Justificación |
|---|---|---|---|
| **Orquestación** | `langgraph` | `>=1.2.0,<2.0` | 1.0 estabilizó la API en oct/2025; 1.2 (mayo 2026) trae `interrupt()` v2 |
| **Checkpointer** | `langgraph-checkpoint-sqlite` | `>=2.0.5` | Para state machine entre HITL gates; SQLite local en `./data/langgraph/checkpoints.sqlite` |
| **LLM client** | `langchain-google-genai` | `>=2.0.0` | Soporta `gemini-2.5-flash-lite`, `thinking_budget`, structured output. Asunción: ya en deps tras esta PR |
| **LangChain core** | `langchain-core` | `>=0.3.40` | Requerido por langgraph 1.x; ya transitivo |
| **Observability** | `langfuse` | `>=3.0.0` | SDK 3.x (2026) cambió a `@observe` y `CallbackHandler` separado |
| **Langfuse server** | `langfuse/langfuse:3` | Docker image tag `3` | Self-hosted compose: server + Postgres 16 + ClickHouse 24 (~2 GB RAM) |
| **Vector store** | `chromadb` | `>=0.5.20` | `PersistentClient` estable; volumen `./data/chroma/` |
| **Embeddings** | `sentence-transformers` | `>=3.0.0` | Modelo `paraphrase-multilingual-MiniLM-L12-v2` (español, 384 dims, ~120 MB) — Asunción ver §6 |
| **PDF render** | `weasyprint` | `>=62.3` | ya en deps |
| **Template** | `jinja2` | `>=3.1` | ya en deps; prompts y reportes |
| **Frontend polling** | `@tanstack/react-query` | `^5.0` | ya en deps; `refetchInterval: 2000` para polling, se detiene cuando `state ∈ {done, error}` |
| **Frontend markdown** | `react-markdown` | `^10.1.0` | ya en deps; render del reporte |
| **Frontend charts** | `recharts` | `^3.8.1` | ya en deps; visualización gap-podio y proyección |

### 2.3 Boundaries v1 (determinista) vs v2 (agéntica)

| Responsabilidad | Capa | Componente | ¿Toca LLM? |
|---|---|---|---|
| Parse PDF | v1 | `pdf_parser.py` | No |
| Normalize nombres/clubes | v1 | `normalizer.py` | No |
| Match fuzzy atletas | v1 | `matcher.py` | No |
| Ingest transaccional | v1 | `ingestor.py` | No |
| Queries SQL longitudinales | v1 → v2 | `queries.py` (extraído de analytics) | No |
| Cómputo gaps/deltas/proyección | v1 | `analytics.py` | No |
| Anonimización pre-LLM | v2 | `services/race/ai/anonymizer.py` | No |
| Retrieval marco teórico | v2 | `services/race/rag/retriever.py` | No (sólo embeddings) |
| Recall memoria por atleta | v2 | `services/race/ai/memory.py` | No |
| Análisis cualitativo + recomendaciones | v2 | `analyst_agent` (LangGraph node) | Sí |
| Crítica del análisis (opcional) | v2 | `critic_agent` (LangGraph node) | Sí |
| HITL approval | v2 | `hitl_gate_review` (interrupt) | No |
| Persist insight | v2 | `persist_insight` | No |
| Re-hidratación nombres | v2 | `rehydrate_names` | No |
| Render markdown + PDF | v2 | `render_outputs` + `pdf_renderer.py` | No |
| Notify coach | v2 | `notification/sender.py` (existente) | No |
| Chat consultivo | v2 | endpoint separado, mismo RAG + memoria | Sí |

**Regla:** la v1 NUNCA llama a la v2. La v2 LLAMA a la v1 (como tool/función determinista). Si v2 falla, v1 sigue operando vía CLI. Esto preserva los 339 tests sin cambios.

### 2.4 Layout de archivos

```
backend/
├── app/
│   ├── models/
│   │   ├── ai_explanation.py           # (existente)
│   │   ├── athlete_ai_insight.py       # NUEVO — memoria agente por atleta
│   │   ├── agent_run.py                # NUEVO — un registro por ejecución de grafo
│   │   ├── agent_run_event.py          # NUEVO — un registro por evento de polling emitido
│   │   ├── anonymization_mapping.py    # NUEVO — auditoría pseudonym ↔ real
│   │   ├── race_*.py                   # (existente, sin cambios)
│   │   └── __init__.py                 # MODIFICADO — exportar nuevos
│   ├── schemas/
│   │   ├── race.py                     # (existente)
│   │   └── race_ai.py                  # NUEVO — schemas Pydantic agéntico
│   ├── routers/
│   │   ├── race_analysis.py            # NUEVO — endpoints REST + polling
│   │   └── ...
│   ├── services/
│   │   ├── ai/                         # (existente, no se toca)
│   │   └── race/
│   │       ├── pdf_parser.py           # (existente)
│   │       ├── csv_parser.py           # (existente)
│   │       ├── normalizer.py           # (existente)
│   │       ├── matcher.py              # (existente)
│   │       ├── ingestor.py             # (existente)
│   │       ├── analytics.py            # (existente, eventualmente extraído)
│   │       ├── queries.py              # NUEVO — queries determinísticas reutilizables
│   │       ├── ai/                     # NUEVO subpaquete
│   │       │   ├── __init__.py
│   │       │   ├── state.py            # TypedDict del estado del grafo
│   │       │   ├── graph.py            # Construcción del StateGraph
│   │       │   ├── nodes/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── validate_input.py
│   │       │   │   ├── load_race_data.py
│   │       │   │   ├── anonymize.py
│   │       │   │   ├── compute_metrics.py
│   │       │   │   ├── retrieve_principles.py
│   │       │   │   ├── recall_memory.py
│   │       │   │   ├── analyst_agent.py
│   │       │   │   ├── critic_agent.py
│   │       │   │   ├── hitl_gate_review.py
│   │       │   │   ├── persist_insight.py
│   │       │   │   ├── rehydrate_names.py
│   │       │   │   ├── render_outputs.py
│   │       │   │   └── notify_coach.py
│   │       │   ├── anonymizer.py       # estrategia pseudonym estable
│   │       │   ├── memory.py           # recall_recent_insights + persist
│   │       │   ├── chat_agent.py       # agente conversacional (reusa RAG+mem)
│   │       │   ├── prompts/
│   │       │   │   ├── system_principles.md  # extracto del marco teórico
│   │       │   │   ├── analyst_v1.md
│   │       │   │   ├── critic_v1.md
│   │       │   │   ├── chat_v1.md
│   │       │   │   ├── explain_mode/
│   │       │   │   │   ├── analyst_v1.md
│   │       │   │   │   └── ...
│   │       │   │   └── eval/
│   │       │   │       └── judge_v1.md
│   │       │   └── pdf_renderer.py     # weasyprint + template Jinja2
│   │       └── rag/
│   │           ├── __init__.py
│   │           ├── ingest.py           # chunking + indexado marco-teorico
│   │           ├── retriever.py        # API consultar_marco_teorico
│   │           └── citations.py        # Citation dataclass
│   ├── observability/                  # NUEVO
│   │   ├── __init__.py
│   │   └── langfuse.py                 # init cliente + decoradores helpers
│   └── config.py                       # MODIFICADO — settings Langfuse + ChromaDB
├── alembic/versions/
│   └── 7a8b9c0d1e2f_add_agentic_race_tables.py  # NUEVO — revision 7a8b9c0d1e2f
│                                                  # down_revision: 64c263edd07f
├── scripts/
│   ├── ingest_race.py                  # (existente CLI)
│   ├── rag_reindex.py                  # NUEVO — reindexa marco-teórico
│   └── eval_race_analyst.py            # NUEVO — runner golden dataset
├── evals/
│   └── race_analyst/
│       ├── golden/
│       │   ├── case_001_thiago_progresion.json
│       │   ├── case_002_inf_a_gap_podio.json
│       │   └── ...                     # 10-20 casos
│       ├── judge_prompt_v1.md          # symlink a prompts/eval/
│       └── runner.py
├── data/                               # NUEVO — gitignored
│   ├── chroma/                         # ChromaDB persistente
│   └── langgraph/
│       └── checkpoints.sqlite
└── tests/
    ├── services/
    │   ├── race/
    │   │   └── ai/
    │   │       ├── test_state.py
    │   │       ├── test_anonymizer.py
    │   │       ├── test_anonymizer_zero_leak.py  # propiedad: 0 nombres reales
    │   │       ├── test_memory.py
    │   │       ├── test_graph_smoke.py
    │   │       ├── test_nodes_individually.py
    │   │       └── test_hitl_resume.py
    │   └── race/rag/
    │       ├── test_chunking.py
    │       └── test_retriever.py
    └── routers/
        └── test_race_analysis_router.py

frontend/
├── src/
│   ├── api/
│   │   └── raceAnalysis.ts             # NUEVO — fetch + polling con TanStack Query
│   ├── routes/
│   │   └── coach/
│   │       └── race-analysis/
│   │           ├── index.tsx           # NUEVO — page entry
│   │           ├── RunDetailPage.tsx
│   │           └── InsightsHistoryPage.tsx
│   ├── components/
│   │   └── race-analysis/
│   │       ├── RaceAnalysisDashboard.tsx
│   │       ├── AnalysisRunTimeline.tsx
│   │       ├── HITLApprovalCard.tsx
│   │       ├── MarkdownReportViewer.tsx
│   │       ├── ChatConsole.tsx
│   │       ├── ExplainModeBanner.tsx
│   │       └── ProgressionChart.tsx    # recharts existente
│   └── store/
│       └── explainMode.ts              # zustand toggle

docker-compose.yml                      # MODIFICADO — añade langfuse + chroma volume
docker-compose.langfuse.yml             # NUEVO — compose dedicado opcional
.env.example                            # MODIFICADO — vars Langfuse + ChromaDB

docs/10-race-results/
├── design.md                           # (existente, v1)
├── v2-agentic-design.md                # ESTE DOCUMENTO
├── learning-plan.md                    # NUEVO — ejercicios progresivos §15
└── eval-baseline.md                    # NUEVO — golden dataset + scores
```

---

## 3. Modelo de datos (deltas)

### 3.1 Tabla `athlete_ai_insights` (NUEVA — memoria agente)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | autoincrement |
| `athlete_id` | int FK→`athletes.id ON DELETE CASCADE` | atleta sujeto del insight |
| `competitor_id` | int FK→`race_competitors.id` NULL | mapping al competitor de la carrera (NULL si insight cross-temporada) |
| `season` | smallint | temporada (ej. 2026) |
| `valida_num` | tinyint NULL | válida que dispara el insight (NULL si es síntesis fin de temporada) |
| `event_id` | int FK→`race_events.id` NULL | evento puntual (NULL si síntesis) |
| `use_case` | varchar(32) | `race_progression`, `race_podium_gap`, `race_projection`, `race_season_summary` |
| `agent_run_id` | int FK→`agent_runs.id` NULL | trazabilidad al run que lo generó |
| `summary_text` | text | narrativa final aprobada por coach (post-HITL) |
| `recommendations_json` | JSON | `[{action, why, priority, principle_refs:[citation_ids]}]` |
| `metrics_snapshot_json` | JSON | snapshot de inputs determinísticos (gaps, posiciones) — para reproducibilidad |
| `principles_cited_json` | JSON | `[{doc, section, chunk_id, relevance_score}]` |
| `confidence` | enum(`low`,`medium`,`high`) | heredado de `analytics.projection` + heurística agente |
| `model` | varchar(128) | `gemini-2.5-flash-lite` |
| `prompt_version` | varchar(32) | `analyst_v1`, `analyst_v2`, ... |
| `coach_approved` | bool | true si pasó HITL gate |
| `coach_edits_count` | smallint default 0 | cuántas iteraciones de edición tuvo |
| `generated_at` | datetime | timestamp generación |
| `approved_at` | datetime NULL | timestamp aprobación coach |
| `generated_by_user_id` | int FK→`users.id` | coach que disparó el run |
| `archived_at` | datetime NULL | soft-delete para insights >2 temporadas |
| `created_at`, `updated_at` | datetime | auditoría |

**Índices:**
- `ix_insights_athlete_season (athlete_id, season DESC, valida_num DESC)` — para `recall_recent_insights(athlete_id, n=3)`
- `ix_insights_event (event_id)` — análisis por válida
- `ix_insights_use_case (use_case, generated_at DESC)` — métricas Langfuse cross-atleta

**Justificación columnas:**
- `competitor_id` separado de `athlete_id`: un atleta puede tener varios competitor_ids históricos por re-matching.
- `recommendations_json` con `principle_refs`: cada recomendación cita la fuente RAG → auditabilidad.
- `metrics_snapshot_json`: si el LLM cambia, podemos re-correr con mismos inputs y comparar.
- `prompt_version`: necesario para A/B y para que Langfuse agrupe runs comparables.
- `coach_approved` + `coach_edits_count`: feedback loop — alto edit count en una versión de prompt → señal de degradación.
- `archived_at`: soft-delete (GDPR/Ley 1581 — el padre puede pedir borrado).

### 3.2 Tabla `agent_runs` (NUEVA — ejecuciones de grafo)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | bigint PK | |
| `external_run_id` | varchar(64) UNIQUE | UUID expuesto al cliente para polling/HITL — nunca el PK interno |
| `graph_name` | varchar(64) | `race_analyst_v1` (permite múltiples grafos coexistiendo) |
| `prompt_version` | varchar(32) | `analyst_v1` activo en el momento |
| `started_at` | datetime | |
| `finished_at` | datetime NULL | NULL si en progreso o crashed |
| `status` | enum(`running`,`awaiting_hitl`,`completed`,`rejected`,`failed`,`cancelled`) | |
| `input_json` | JSON | parámetros de entrada (athlete_id, season, valida_nums) |
| `final_output_json` | JSON NULL | snapshot del state al `END` (incluye insight_id si committed) |
| `error_message` | text NULL | si `status=failed` |
| `langfuse_trace_id` | varchar(128) NULL | link al trace en Langfuse para drill-down |
| `requested_by_user_id` | int FK→`users.id` | coach que disparó |
| `checkpoint_thread_id` | varchar(64) | thread_id pasado a LangGraph SqliteSaver |
| `explain_mode` | bool default false | si modo aprendizaje estuvo activo |
| `cost_usd` | decimal(8,5) NULL | reportado por Langfuse, denormalizado para queries rápidas |
| `created_at`, `updated_at` | datetime | |

**Índices:**
- `ix_agent_runs_user_started (requested_by_user_id, started_at DESC)`
- `ix_agent_runs_status (status)`
- `uq_agent_runs_external (external_run_id)`

**Justificación:** `agent_runs` es el "header" de cada análisis. `external_run_id` evita exponer el autoincrement (mejor práctica seguridad URL). `checkpoint_thread_id` es la clave para resumir desde HITL.

### 3.3 Tabla `agent_run_events` (NUEVA — log de eventos de polling)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | bigint PK | |
| `run_id` | bigint FK→`agent_runs.id ON DELETE CASCADE` | |
| `seq` | int | orden monotónico dentro del run (1..N) |
| `event_type` | enum(`node_start`,`node_end`,`hitl_request`,`hitl_response`,`explain`,`token`,`error`,`done`) | |
| `node_name` | varchar(64) NULL | nodo emisor (NULL para eventos a nivel grafo) |
| `payload_json` | JSON | datos del evento (snapshot del state delta, mensaje pedagógico, error...) |
| `created_at` | datetime | |

**Índices:**
- `ix_run_events_run_seq (run_id, seq)`
- `ix_run_events_type (event_type)`

**Justificación:** persistimos eventos por dos razones — (1) el cliente que pollinguea puede solicitar `?since=42` y recibir solo eventos nuevos sin replay completo; (2) auditoría retrospectiva y debugging sin abrir Langfuse.

### 3.4 Tabla `anonymization_mappings` (NUEVA — auditoría privacy)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | bigint PK | |
| `run_id` | bigint FK→`agent_runs.id ON DELETE CASCADE` | |
| `pseudonym` | varchar(64) | `Atleta-PJUV-A-F-001` |
| `real_competitor_id` | int FK→`race_competitors.id` | mapping inverso (sólo lectura interna) |
| `real_athlete_id` | int FK→`athletes.id` NULL | si está confirmado match TyR |
| `salt_used` | varchar(16) | sal para hash si se usa estrategia determinista |
| `created_at` | datetime | |

**Índices:**
- `uq_anon_run_pseudonym (run_id, pseudonym)`
- `ix_anon_run_athlete (run_id, real_athlete_id)`

**Justificación:** la tabla NO se expone vía API. Sirve para (1) re-hidratar nombres después del LLM call, (2) auditar que ninguna respuesta del LLM contiene PII, (3) cumplir requerimientos Ley 1581 — un padre puede pedir "qué datos de mi hijo fueron enviados a un LLM externo" y respondemos con esta tabla.

⚠️ **Decisión requerida:** mantener la tabla persistente vs solo in-memory por run. Persistente da trazabilidad pero acumula PII enlazada a pseudonyms. **Propuesta:** persistente con TTL de 90 días + scheduled cleanup. Asunción: 90 días es suficiente ventana para auditorías retroactivas sin acumular indefinidamente.

### 3.5 Migración Alembic

```
revision: 7a8b9c0d1e2f
down_revision: 64c263edd07f
description: Tablas para módulo agéntico race-results (insights, runs, events, anonymization)
```

**Operaciones up:**

1. `CREATE TABLE agent_runs` (con `external_run_id UNIQUE`)
2. `CREATE TABLE agent_run_events` (FK a agent_runs)
3. `CREATE TABLE athlete_ai_insights` (FK a athletes, agent_runs)
4. `CREATE TABLE anonymization_mappings` (FK a agent_runs)
5. Crear índices listados arriba.

**Operaciones down:** drop en orden inverso (events → runs → insights → mappings).

**Validación post-migración:** script `scripts/verify_agentic_schema.py` que hace `SELECT 1` de cada tabla y valida FKs (sin tocar datos).

---

## 4. Workflow LangGraph — el corazón

### 4.1 Diagrama del grafo

```mermaid
stateDiagram-v2
    [*] --> validate_input
    validate_input --> load_race_data : input válido
    validate_input --> [*] : input inválido (error)

    load_race_data --> anonymize : datos cargados
    anonymize --> compute_metrics
    compute_metrics --> retrieve_principles
    retrieve_principles --> recall_memory
    recall_memory --> analyst_agent

    analyst_agent --> critic_agent : output OK
    analyst_agent --> hitl_gate_review : output con warnings

    critic_agent --> hitl_gate_review : revisión OK
    critic_agent --> analyst_agent : retry (max 2)

    hitl_gate_review --> persist_insight : approved
    hitl_gate_review --> analyst_agent : edited (vuelve con feedback)
    hitl_gate_review --> notify_coach : rejected (skip persist)

    persist_insight --> rehydrate_names
    rehydrate_names --> render_outputs
    render_outputs --> notify_coach
    notify_coach --> [*]

    note right of hitl_gate_review
        interrupt() pausa el grafo.
        El coach aprueba/edita/rechaza
        vía POST /runs/{id}/hitl/{step}.
        Resume con Command(resume=...).
    end note
```

### 4.2 State schema (TypedDict)

```python
# services/race/ai/state.py
class RaceAnalystState(TypedDict, total=False):
    # ---- Input determinístico ----
    run_id: int                         # FK agent_runs.id
    external_run_id: str                # UUID
    athlete_id: int
    season: int
    valida_nums: list[int]              # ej [3, 4] para analizar V-III + V-IV
    explain_mode: bool

    # ---- Datos cargados ----
    competitor_id: int | None
    category_id: int | None
    race_results_raw: list[dict]        # rows de race_results para el atleta
    podium_context_raw: list[dict]      # podium times por evento/categoría
    series_meta: dict

    # ---- Anonimización ----
    anonymization_map: dict[int, str]   # {competitor_id: pseudonym}
    reverse_map: dict[str, int]         # {pseudonym: competitor_id}
    salt: str

    # ---- Métricas computadas (determinístico) ----
    progression_df: list[dict]
    podium_gap_df: list[dict]
    projection: dict

    # ---- RAG + memoria ----
    principles_retrieved: list[dict]    # [{chunk_id, content, score, source}]
    recent_insights: list[dict]         # últimos N insights del atleta

    # ---- LLM outputs ----
    analyst_draft: dict | None          # JSON parsed, antes del crítico
    critic_feedback: list[str]          # observaciones del crítico
    critic_pass: bool
    retry_count: int                    # límite 2

    # ---- HITL ----
    hitl_action: str | None             # 'approve'|'edit'|'reject'
    hitl_edits: dict | None             # coach reemplaza campos del draft
    hitl_at: str | None                 # ISO datetime

    # ---- Output final ----
    final_insight: dict                 # snapshot pre-render
    rendered_markdown: str
    pdf_path: str | None
    email_sent: bool

    # ---- Trazabilidad ----
    langfuse_trace_id: str
    errors: list[dict]                  # acumulador de fallos no fatales
    pedagogical_messages: list[dict]    # generados si explain_mode=True
```

**Decisión sobre `total=False`:** permite que cada nodo escriba sólo su slice del estado sin tener que inicializar todos los campos. LangGraph mergea automáticamente (last-write-wins por defecto; reducers custom si fuese necesario, ej. `pedagogical_messages: Annotated[list, operator.add]`).

### 4.3 Lista de nodos — IO esperado

| # | Nodo | Lee del state | Escribe al state | Llama tools | LLM | Pedagogical |
|---|---|---|---|---|---|---|
| 1 | `validate_input` | `athlete_id`, `season`, `valida_nums` | `errors` si falla | `queries.athlete_exists` | No | "Verifico que el atleta exista y tenga resultados..." |
| 2 | `load_race_data` | `athlete_id`, `season`, `valida_nums` | `race_results_raw`, `series_meta`, `competitor_id`, `category_id` | `queries.fetch_results_for_athlete`, `queries.fetch_podium_context` | No | "Cargo resultados desde MySQL — sin LLM aún..." |
| 3 | `anonymize` | `race_results_raw`, `podium_context_raw`, `athlete_id` | `anonymization_map`, `reverse_map`, `salt` | `anonymizer.generate_mapping`, persist a `anonymization_mappings` | No | "Reemplazo nombres por pseudónimos antes de hablar con LLM externo..." |
| 4 | `compute_metrics` | `race_results_raw`, `series_meta` | `progression_df`, `podium_gap_df`, `projection` | `analytics.athlete_progression`, `analytics.podium_gap`, `analytics.projection` | No | "Calculo gaps determinísticamente — el LLM no inventa números..." |
| 5 | `retrieve_principles` | `progression_df`, `athlete_id` (→ edad → grupo LTAD) | `principles_retrieved` | `rag.retriever.consultar_marco_teorico` con queries derivadas | No (embeddings sí) | "Busco principios LTAD relevantes para este grupo de edad..." |
| 6 | `recall_memory` | `athlete_id`, `season` | `recent_insights` | `memory.recall_recent_insights(athlete_id, n=3)` | No | "Recupero los 3 últimos insights de este atleta para no repetirme..." |
| 7 | `analyst_agent` | TODO (datos anonimizados + principios + memoria) | `analyst_draft` | LLM Gemini Flash Lite, prompt `analyst_v1` | Sí | "Pido al LLM que sintetice análisis. Le doy SOLO pseudónimos..." |
| 8 | `critic_agent` | `analyst_draft`, `principles_retrieved` | `critic_feedback`, `critic_pass` | LLM con prompt `critic_v1` | Sí (opcional) | "Otro LLM revisa que el análisis cite principios reales y no contradiga LTAD..." |
| 9 | `hitl_gate_review` | `analyst_draft`, `critic_feedback` | `hitl_action`, `hitl_edits`, `hitl_at` | `interrupt()` LangGraph | No | "Pauso aquí — el coach revisa antes de persistir..." |
| 10 | `persist_insight` | `analyst_draft`, `hitl_edits`, `run_id` | `final_insight` | `memory.persist_insight` | No | "Guardo el insight aprobado para que el próximo análisis lo recuerde..." |
| 11 | `rehydrate_names` | `final_insight`, `reverse_map` | `final_insight` actualizado con nombres reales | `anonymizer.rehydrate_text` | No | "Reemplazo pseudónimos por nombres reales — esto NO va al LLM..." |
| 12 | `render_outputs` | `final_insight`, `progression_df`, etc. | `rendered_markdown`, `pdf_path` | `pdf_renderer.render` | No | "Genero markdown + PDF con weasyprint..." |
| 13 | `notify_coach` | `run_id`, `email_destination` | `email_sent` | `notification.send_race_analysis_ready` (template Resend) | No | "Te envío un email cuando todo termina." |

### 4.4 Checkpointing

**Decisión:** `langgraph-checkpoint-sqlite` (no Postgres, no MySQL).

**Razones:**
- MySQL no tiene saver oficial (sólo Postgres). Crearlo es over-engineering para single-coach uso.
- SQLite local en volumen Docker `./data/langgraph/checkpoints.sqlite` es suficiente (<100 runs/mes).
- Aislamiento del estado del grafo del estado de negocio — el grafo puede corromperse sin afectar `race_*` tables.

**Thread strategy:**
- `checkpoint_thread_id = external_run_id` (UUID). Garantiza unicidad y permite resume vía `Command(resume=...)`.
- Persistencia indefinida hasta `status in (completed, rejected, failed)`. Cleanup job mensual borra checkpoints terminados >30 días.

**Tabla SQLite generada por LangGraph:** `checkpoints` con columnas `(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)`. No la tocamos directamente.

### 4.5 Error handling

| Tipo de error | Estrategia | Donde se maneja |
|---|---|---|
| Validation error (input inválido) | abort temprano, status=`failed`, mensaje claro al frontend | `validate_input` |
| DB read timeout (load_race_data) | retry exponencial 3x (200ms, 1s, 5s); si falla → status=`failed` | tenacity decorator en `queries.py` |
| ChromaDB no responde | fallback: `principles_retrieved = []` + warning al coach; continuar | `retrieve_principles` |
| Gemini rate limit (429) | backoff exponencial 4x con jitter; si persiste 5 min → fallback `gemini-2.0-flash` (modelo previo) | wrapper en `analyst_agent`, `critic_agent` |
| Gemini timeout (>30s) | abort nodo, marcar `analyst_draft=None`, ir a `hitl_gate_review` con mensaje "LLM caído — coach decide manualmente" | wrapper |
| Guardrails rechazan output | retry 1x con `critic_feedback` inyectado; si vuelve a fallar → HITL con draft crudo + warning | `analyst_agent` |
| HITL timeout (>24h sin respuesta del coach) | status=`awaiting_hitl` persistente, no se cancela. Email recordatorio a las 4h | scheduled job `agent_runs_reaper.py` |
| Persist insight FK violation | rollback, status=`failed`, alerta Sentry | `persist_insight` |
| PDF render falla (weasyprint) | continuar con sólo markdown + warning; coach descarga PDF luego | `render_outputs` |

**Dead-letter:** si un run queda `failed` >7 días, se archiva con `error_message` completo y se notifica al coach vía email con link al trace Langfuse.

---

## 5. Sistema de agentes: single vs multi

### 5.1 Recomendación: **multi-agent con supervisor implícito (lineal)**

No un supervisor pattern formal (que añadiría un nodo extra de routing LLM), sino una composición lineal con tres roles LLM:

1. **`analyst_agent`** — produce el análisis cualitativo + recomendaciones a partir de datos + principios + memoria.
2. **`critic_agent`** — revisa el output del analyst: ¿cita principios reales? ¿contradice LTAD? ¿incluye nombres reales (PII leak)? ¿menciona números no provistos?
3. **`chat_agent`** — agente conversacional separado (NO parte del grafo de análisis), expone endpoint `/chat`. Reusa el RAG + memoria del atleta.

### 5.2 Trade-offs evaluados

| Opción | Pros | Cons | Riesgo |
|---|---|---|---|
| **A) Single-agent** (sólo analyst) | Simple, 1 LLM call por run, $ mínimo | Sin segunda opinión → riesgo alucinación pasa al coach | Medio |
| **B) Multi-agent lineal** (analyst + critic) | +1 LLM call captura inconsistencias antes del HITL → menos churn de edits del coach | 2x costo (~$0.004 vs $0.002 por análisis) | Bajo |
| **C) Supervisor pattern formal** (LLM enruta nodos) | Máxima flexibilidad, exploración | Sobre-ingeniería para flujo conocido; latencia +2-3s por decisión de routing | Alto |
| **D) Multi-agent con handoff explícito** (analyst delega a especialistas por tema) | Alta calidad si tópicos son ortogonales | Coordinación compleja, latencia, $ alto | Alto |

**Recomendación final:** **B (multi-agent lineal)** para MVP. El `critic_agent` se puede DESACTIVAR vía feature flag `RACE_AGENT_CRITIC_ENABLED=false` si en eval baseline el critic no aporta valor diferencial >5 % en score golden.

⚠️ **Decisión requerida del coach:** ¿activar critic desde el MVP o esperar a baseline? **Propuesta:** activarlo, evaluar después de 5-10 runs reales.

### 5.3 Chat consultivo (`chat_agent`)

- Endpoint separado `POST /chat` — NO comparte grafo con el flujo de análisis.
- Sesión conversacional por `session_id` (no thread_id de LangGraph), persistida en memoria del proceso (Redis si escala; para MVP, dict in-memory con TTL 1h).
- Tools del agente:
  - `consultar_marco_teorico(query)` (RAG)
  - `obtener_insights_atleta(athlete_id, n=5)` (memoria)
  - `fetch_results(athlete_id, season)` (queries.py)
- Anonimización: si el coach pregunta "¿cómo va Thiago?", el agente internamente convierte `Thiago` → `competitor_id`, anonimiza datos, llama LLM, re-hidrata respuesta.
- **No HITL** — chat es directo. Coach corrige en próximo turn si quiere.

Asunción: chat no requiere persistencia post-sesión en MVP. Si se quiere historial cross-sesión, escalar después.

---

## 6. Capa RAG sobre marco teórico

### 6.1 Estrategia chunking

| Parámetro | Valor | Razón |
|---|---|---|
| Estrategia | `RecursiveCharacterTextSplitter` (LangChain) o equivalente nativo | Respeta jerarquía markdown (#, ##, ###, párrafo) |
| Tamaño chunk | 800 tokens | Balance entre contexto suficiente y precisión retrieval |
| Overlap | 100 tokens | Evita perder frases que cruzan boundaries |
| Separadores | `["\n## ", "\n### ", "\n\n", "\n", ". "]` | Prioriza headings |
| Metadata por chunk | `{doc, h1, h2, h3, chunk_id, source_path, lines}` | Citation tracking |

**Documentos a indexar (Fase MVP):**
- `docs/01-marco-teorico.md` (290 líneas, ~6k tokens) — ~10-15 chunks
- Asunción: marco teórico hoy es 1 archivo monolítico. Si en futuro se divide en subdocs (`marco-teorico/`), reindexar todos.

### 6.2 Embeddings — selección de modelo

| Modelo | Dim | Tamaño | Idioma | Costo | Recomendación |
|---|---|---|---|---|---|
| `text-embedding-3-small` (OpenAI) | 1536 | API | multilingüe (ok español) | $0.02 / 1M tokens | Buena calidad pero +1 vendor |
| `gemini-embedding-001` (Google) | 768 | API | multilingüe | ~free tier | Consistencia con Gemini LLM; **recomendado** |
| `paraphrase-multilingual-MiniLM-L12-v2` (HuggingFace) | 384 | 120 MB local | multilingüe | $0 (local) | Más simple, sin red para indexar |
| `intfloat/multilingual-e5-large` | 1024 | 2.2 GB local | multilingüe top-tier | $0 | Mejor calidad local pero pesado |

**Recomendación:** **`gemini-embedding-001`** via `langchain-google-genai.GoogleGenerativeAIEmbeddings`. Ventajas:
- Consistencia con el LLM (mismo provider, misma cuenta).
- Multilingüe robusto en español.
- Costo despreciable (texto fuente <10k tokens, una sola indexación + queries esporádicas).

⚠️ **Fallback si no se quiere depender de Google para embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` local (sentence-transformers). Decidir según preferencia coach por minimizar vendor lock-in.

### 6.3 ChromaDB persistencia

```
data/chroma/
  chroma.sqlite3
  <collection_uuid>/
    ...
```

- Volumen Docker: `./data/chroma:/data/chroma` (gitignored).
- `PersistentClient(path="./data/chroma")`.
- Collection: `marco_teorico` (1 sola; futuras: `glosario_xco`, `historial_clinico_agregado`...).
- HNSW config default (M=16, ef_construction=200) — suficiente para <1000 vectores.

### 6.4 Reindexado

| Trigger | Estrategia | Implementación |
|---|---|---|
| Manual (coach edita marco-teórico) | CLI `scripts/rag_reindex.py [--doc=marco-teorico]` | Lee → chunkea → upsert por `chunk_id` determinístico (hash del contenido) |
| CI hook | GitHub Action en push a `docs/01-marco-teorico.md` → corre reindex en deploy | Asunción: Render deploy script lo dispara |
| Programado | No (docs cambian raro) | n/a |

**Idempotencia:** `chunk_id = sha256(doc_path + chunk_idx + content)[:16]`. Si el contenido no cambia, upsert es no-op.

### 6.5 Tool del agente

```python
# services/race/rag/retriever.py
def consultar_marco_teorico(
    query: str,
    top_k: int = 3,
    filter_h1: Optional[str] = None,
) -> list[Citation]:
    """
    Retorna chunks relevantes con metadata para citation.
    Citation = {chunk_id, doc, section_path, content, score, source_lines}
    """
```

Uso en `analyst_agent`:
- Queries generadas dinámicamente según contexto (ej. si `athlete.age < 13` → query "principios entrenamiento 10-12 años"; si `gap_to_p1_pct > 30` → "técnica antes que potencia").
- Top-3 por query, max 2-3 queries por análisis → ~6-9 chunks en context window.
- Cada cita devuelta tiene `chunk_id` que se persiste en `principles_cited_json` → trazabilidad coach-side.

---

## 7. Memoria por atleta

### 7.1 Modelo `AthleteAIInsight` (sección 3.1)

### 7.2 Función `recall_recent_insights`

```python
# services/race/ai/memory.py
async def recall_recent_insights(
    db: AsyncSession,
    athlete_id: int,
    n: int = 3,
    exclude_archived: bool = True,
) -> list[InsightMemoryItem]:
    """
    Retorna los últimos N insights aprobados (coach_approved=True)
    ordenados por (season DESC, valida_num DESC, generated_at DESC).
    Excluye archived_at IS NOT NULL si exclude_archived=True.
    """
```

**InsightMemoryItem (Pydantic):**
```python
class InsightMemoryItem(BaseModel):
    insight_id: int
    season: int
    valida_num: int | None
    use_case: str
    summary_text: str           # narrativa que el LLM verá
    key_recommendations: list[str]  # extraídas top-3 de recommendations_json
    generated_at: datetime
    confidence: str
```

**Inyección en prompt:**
- El prompt `analyst_v1.md` tiene una sección `{% if recent_insights %}` que renderiza un bloque:
  ```
  ## Memoria del atleta (insights previos)
  {% for ins in recent_insights %}
  - Válida {{ins.valida_num}} ({{ins.season}}): {{ins.summary_text[:300]}}...
    Recomendaciones: {{ins.key_recommendations | join(', ')}}
  {% endfor %}
  ```
- El LLM tiene instrucción: "evita repetir literalmente recomendaciones previas; si el patrón persiste, recoméndalo como urgente".

### 7.3 Persist insight

```python
async def persist_insight(
    db: AsyncSession,
    run_id: int,
    payload: AnalystOutput,
    coach_approved: bool,
    coach_edits_count: int,
) -> AthleteAIInsight:
    """
    Inserta nuevo registro. Hace flush + commit.
    Si coach_approved=False, igualmente persiste pero con flag para análisis posterior.
    """
```

### 7.4 Garbage collection / archive

- Job mensual `scripts/archive_old_insights.py`:
  - Marca `archived_at = NOW()` insights con `season < current_year - 1` y NO citados en últimos 90 días.
  - No borra (auditoría); solo excluye de recall.
- Coach UI: tab "Historial completo" muestra archivados con tag.

⚠️ **Decisión requerida:** ¿borrado físico tras X años o solo archive indefinido? **Propuesta:** archive indefinido, físico borrado solo si padre solicita explícitamente (Ley 1581 derecho de supresión).

---

## 8. Anonimización (privacy by design)

### 8.1 Estrategia elegida: **persistente por run + determinística por hash**

**Híbrido:**
- Para cada run, generamos pseudónimos basados en `salt = run.external_run_id` + `competitor_id` → hash determinístico → sufijo formateado.
- Formato pseudónimo: `Atleta-{CATEGORY_CODE}-{HASH_3DIGITS}` ej. `Atleta-PJUV-A-F-001`.
- **Salt distinto por run** → mismo competitor tiene pseudónimo distinto entre runs → minimiza correlación cross-run en logs LLM.
- **Determinístico dentro del run** → si el grafo retry o resume, mapping persiste.

### 8.2 Implementación (alto nivel — sin código)

`anonymizer.generate_mapping(run_id, competitor_ids, category_code) -> dict[int, str]`:
1. Para cada `competitor_id`, computa `hash_id = hmac_sha256(run.salt, str(competitor_id))[:3]`.
2. Genera `pseudonym = f"Atleta-{category_code}-{hash_id.upper()}"`.
3. Inserta filas en `anonymization_mappings` (transaction).
4. Retorna `{competitor_id: pseudonym}` + `{pseudonym: competitor_id}`.

`anonymizer.anonymize_payload(data, mapping) -> dict`:
1. Recorre el payload dict/list recursivamente.
2. Reemplaza cualquier `competitor_id` o `display_name` por pseudónimo.
3. Si encuentra texto libre (ej. `notes`), aplica regex de nombres conocidos.
4. Retorna payload "limpio".

`anonymizer.rehydrate_text(llm_output, reverse_map) -> str`:
1. Recorre el texto markdown.
2. Reemplaza cada pseudónimo encontrado por `display_name` real.
3. Retorna texto re-hidratado (sólo para UI; NUNCA se reenvía al LLM).

### 8.3 Test propiedad: zero leak

`tests/services/race/ai/test_anonymizer_zero_leak.py`:

- Generar un payload sintético con 5 atletas (nombres reales + apellidos colombianos comunes).
- Anonimizar con la función.
- **Aserción de propiedad:** ningún string del listado original (full name, first name, last name, apodo si existe) aparece en el payload anonimizado.
- Repetir con 1000 inputs random (property-based test con `hypothesis`).
- Si en algún input la propiedad falla → test rojo → bloquea merge.

Adicional:
- Test que captura `httpx`/`requests` mocks: ningún POST al endpoint Gemini contiene nombres reales (intercept layer).

### 8.4 Auditoría runtime

- Middleware FastAPI en endpoint `/api/race-analysis/runs` registra en log estructurado: `{run_id, anonymized=True, mapping_count=N}`.
- Logs NUNCA incluyen el mapping ni nombres reales (sólo conteos).
- Langfuse: prompt y completion se envían con pseudónimos. Si Langfuse fuera externo (no lo será — self-hosted), igual cumple PII compliance.

---

## 9. API REST (FastAPI endpoints)

> Todos los endpoints requieren auth JWT (header `Authorization: Bearer ...`). RBAC: salvo indicación, **coach** + **admin**. Parents NO acceden a este módulo (sus datos los reciben filtrados vía otros módulos).

### 9.1 `POST /api/race-analysis/runs` — iniciar análisis

**Body (Pydantic):**
```python
class StartRunRequest(BaseModel):
    athlete_id: int
    season: int = Field(ge=2020, le=2100)
    valida_nums: list[int] = Field(min_length=1, max_length=8)
    use_case: Literal["race_progression","race_podium_gap","race_projection","race_season_summary"]
    explain_mode: bool = False
```

**Response 201:**
```python
class StartRunResponse(BaseModel):
    run_id: str             # external_run_id (UUID)
    status: Literal["running"]
    started_at: datetime
    status_url: str         # ej "/api/race-analysis/runs/{run_id}/status"
    estimated_seconds: int  # heurística: 15 + 5*len(valida_nums)
```

**Errores:**
- `400` athlete no existe o no es TyR confirmado
- `400` season sin eventos
- `403` user no es coach/admin
- `409` ya hay un run activo para (athlete, use_case) (evita concurrencia)
- `429` >10 runs en cola del usuario (rate limit)

**Side effects:** crea fila `agent_runs`, dispara LangGraph en background task (`asyncio.create_task` + tracking en in-memory registry), retorna inmediatamente.

### 9.2 `GET /api/race-analysis/runs/{run_id}/status` — polling

> **Decisión 2026-05-20:** descartado SSE en favor de polling — más simple, funciona en cualquier provider (Render free tier, proxies), sin validar timeouts. Trade-off aceptado: ~2s de lag en UI vs realtime. Aceptable para análisis de ~30s.

**Query params:**
- `since` (opcional, int): retorna solo eventos con `seq > since` (evita replay completo en cada poll)

**Auth:** requerido (coach owner del run o admin)

**Response 200:**
```json
{
  "run_id": "uuid",
  "state": "parsing|matching|analyzing|critic|hitl_pending|done|error",
  "progress_pct": 45,
  "current_node": "agent_analyst",
  "started_at": "2026-05-20T10:30:00Z",
  "estimated_seconds_remaining": 12,
  "new_events": [
    {"seq": 23, "node": "parser", "type": "node_complete", "data": {}, "ts": "..."},
    {"seq": 24, "node": "anonymize", "type": "explain", "data": {"message": "Reemplazo nombres..."}, "ts": "..."}
  ]
}
```

**Comportamiento cliente:**
- Pollinguea cada 2 segundos con `?since=<last_seq_visto>`.
- Para de pollinguear cuando `state ∈ {done, error}`.
- Pattern TanStack Query: `refetchInterval: state === 'done' || state === 'error' ? false : 2000`.

**RBAC:** sólo el `requested_by_user_id` puede leer. Admin puede leer cualquiera.

**Optimización:** si el state no cambió desde el último poll, el servidor puede retornar `304 Not Modified` con ETag basado en el último `seq` emitido.

### 9.3 `POST /api/race-analysis/runs/{run_id}/hitl/{step_id}` — HITL response

**Body:**
```python
class HITLResponseBody(BaseModel):
    action: Literal["approve","edit","reject"]
    edits: dict | None = None        # si action=edit, parcial del analyst_draft
    rejection_reason: str | None = None
```

**Response 200:**
```python
class HITLResponseAck(BaseModel):
    run_id: str
    step_id: str
    accepted: bool
    next_step: str | None            # ej "persist_insight" o None si rejected
```

**Errores:**
- `404` run o step no existe
- `409` run no está en estado `awaiting_hitl`
- `422` edits no validan contra schema del draft

**Side effects:** invoca `graph.update_state(...)` + `graph.invoke(Command(resume=...))`. Persiste evento `hitl_response` en `agent_run_events` (visible en próximo poll).

### 9.4 `GET /api/race-analysis/runs/{run_id}/result` — JSON final

**Response 200:**
```python
class RunResult(BaseModel):
    run_id: str
    status: Literal["completed","rejected","failed"]
    insight_id: int | None
    final_insight: dict | None
    rendered_markdown: str | None
    pdf_available: bool
    error: str | None
    cost_usd: float | None
    duration_seconds: float
    langfuse_trace_url: str | None   # solo si user es admin
```

### 9.5 `GET /api/race-analysis/runs/{run_id}/pdf` — descarga PDF

**Response 200:** `application/pdf` binario. Filename `analisis_<athlete_id>_<season>_v<valida>_<run_id_short>.pdf`.
**404:** si `pdf_available=false` o aún no completado.

### 9.6 `POST /api/race-analysis/chat` — chat consultivo

**Body:**
```python
class ChatRequest(BaseModel):
    session_id: str | None = None    # null → crea nueva
    message: str = Field(min_length=1, max_length=2000)
    context_athlete_id: int | None = None  # opcional, ata sesión a un atleta
```

**Response 200:** respuesta completa cuando el LLM termina (no streaming). `{full_text, citations, session_id}`. El cliente usa `useQuery` con `refetchInterval` mientras `state === 'pending'`.

**RBAC:** coach/admin.

### 9.7 `GET /api/race-analysis/athletes/{athlete_id}/insights` — historial

**Query params:**
- `season` (opcional)
- `use_case` (opcional)
- `include_archived` (default false)
- `limit` (default 20, max 100)

**Response:**
```python
class InsightsList(BaseModel):
    athlete_id: int
    insights: list[InsightSummary]
    total: int
```

**RBAC:** coach/admin. Parent NO ve (sus datos los recibe vía otros módulos filtrados).

---

## 10. Frontend componentes (React)

### 10.1 Layout y rutas

```
/coach/race-analysis                  → RaceAnalysisDashboard (tabs)
/coach/race-analysis/runs/:runId      → RunDetailPage
/coach/race-analysis/insights         → InsightsHistoryPage
```

### 10.2 Componentes

#### `RaceAnalysisDashboard` (`routes/coach/race-analysis/index.tsx`)
- Layout principal con `Tabs` shadcn:
  - **Iniciar análisis** — formulario (athlete, season, valida_nums, use_case, explain_mode toggle) → `POST /runs`
  - **Runs activos** — lista con badge status (running/awaiting_hitl/completed/failed) — auto-refresh cada 5s
  - **Insights históricos** — link a `InsightsHistoryPage`
- Banner permanente `ExplainModeBanner` con toggle global (zustand).

#### `AnalysisRunTimeline` (componente reutilizable)
- Props: `runId: string`
- Hook: `useQuery` con `refetchInterval: 2000` apuntando a `/api/race-analysis/runs/${runId}/status?since=<last_seq>`. Se detiene al llegar `state ∈ {done, error}`.
- Renderiza vertical timeline (shadcn `Stepper` o custom):
  - Cada `node_end` → step ✅
  - `node_start` sin `node_end` aún → step ⏳ (spinner)
  - `hitl_request` → step ⏸️ con `HITLApprovalCard` embebido
  - `error` → step ❌ rojo
- Si `explainMode=true`, debajo de cada step muestra el `explain` message (panel expandible).
- Cuando llega `done` → muestra `MarkdownReportViewer` + botón descargar PDF.

#### `HITLApprovalCard`
- Props: `runId`, `stepId`, `draft`, `criticFeedback`, `principlesCited`
- UI:
  - Renderiza el `draft.summary_text` en markdown (read-only inicial)
  - Botón "Editar" → switch a `Textarea` editable
  - Sección colapsable "Crítico LLM dice:" → lista `criticFeedback`
  - Sección "Principios citados:" → cards con chunk + score
  - Tres botones: **Aprobar**, **Aprobar con cambios**, **Rechazar**
- `onAprove`/`onEdit`/`onReject` → `POST /runs/:id/hitl/:step` con TanStack mutation.

#### `MarkdownReportViewer`
- Props: `markdown: string`, `progressionData?: ...`, `podiumGapData?: ...`
- Render: `react-markdown` con plugins (`remark-gfm` para tablas).
- Inyección de visualizaciones inline: si markdown contiene `<chart data-type="progression">...`, sustituye por `<ProgressionChart />` (recharts).
- Footer: botones "Descargar PDF", "Copiar link", "Compartir vía email".

#### `ChatConsole`
- Layout split: chat history (scroll virtualizado) + input bottom.
- Persistencia sesión: localStorage por `coach_id`, máximo última conversación.
- Respuesta completa: hook `useChatSend` (mutation TanStack Query) que hace POST y espera respuesta JSON completa. Muestra spinner mientras `isPending`.
- Cada mensaje del bot muestra "citations" (chunks RAG usados) en footer expandible.
- Si pregunta nombra atleta, captura `context_athlete_id` y se mantiene en próximos turns.

#### `ExplainModeBanner`
- Sticky top banner amarillo claro.
- Toggle `🏫 Modo aprendizaje` con tooltip "Activa explicaciones pedagógicas por cada paso del agente".
- Estado en zustand `useExplainModeStore`, persistido en localStorage.

### 10.3 TanStack Query hooks

```typescript
// frontend/src/api/raceAnalysis.ts
useStartRun()                          // mutation POST /runs
useRunStatus(runId)                    // query polling GET /runs/:id/status
useRunResult(runId)                    // query GET /runs/:id/result
useRunPdfUrl(runId)                    // memoized URL
useApproveStep(runId, stepId)          // mutation POST /hitl
useChatSend(sessionId)                 // mutation POST /chat (respuesta completa)
useAthleteInsights(athleteId, opts)    // query con paginación
```

### 10.4 Polling pattern (`useRunStatus`)

```typescript
// frontend/src/api/raceAnalysis.ts
function useRunStatus(runId: string) {
  const [lastSeq, setLastSeq] = useState(0)
  return useQuery({
    queryKey: ['run-status', runId, lastSeq],
    queryFn: () => fetchRunStatus(runId, lastSeq),
    refetchInterval: (query) => {
      const state = query.state.data?.state
      if (state === 'done' || state === 'error') return false
      return 2000
    },
    onSuccess: (data) => {
      if (data.new_events.length > 0) {
        setLastSeq(data.new_events.at(-1)!.seq)
      }
    },
  })
}

---

## 11. Observability (Langfuse self-hosted)

### 11.1 Setup docker-compose

Servicios nuevos en `docker-compose.langfuse.yml` (perfil opcional):

```yaml
services:
  langfuse-postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: ${LANGFUSE_DB_PASS}
      POSTGRES_DB: langfuse
    volumes: [langfuse_pg_data:/var/lib/postgresql/data]
    networks: [backend]

  langfuse-clickhouse:
    image: clickhouse/clickhouse-server:24.8-alpine
    environment:
      CLICKHOUSE_DB: langfuse
      CLICKHOUSE_USER: langfuse
      CLICKHOUSE_PASSWORD: ${LANGFUSE_CH_PASS}
    volumes: [langfuse_ch_data:/var/lib/clickhouse]
    networks: [backend]

  langfuse-server:
    image: langfuse/langfuse:3
    depends_on: [langfuse-postgres, langfuse-clickhouse]
    ports: ["3001:3000"]
    environment:
      DATABASE_URL: postgresql://langfuse:${LANGFUSE_DB_PASS}@langfuse-postgres:5432/langfuse
      CLICKHOUSE_URL: http://langfuse-clickhouse:8123
      CLICKHOUSE_USER: langfuse
      CLICKHOUSE_PASSWORD: ${LANGFUSE_CH_PASS}
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET}
      SALT: ${LANGFUSE_SALT}
      ENCRYPTION_KEY: ${LANGFUSE_ENCRYPTION_KEY}
      NEXTAUTH_URL: http://localhost:3001
    networks: [backend]

volumes:
  langfuse_pg_data:
  langfuse_ch_data:
```

**RAM estimada:** ~2 GB total (Postgres 200 MB, ClickHouse 700 MB, Server 800 MB, headroom 300 MB).

**Producción:** mismo compose deployable en VPS (no Render free tier, no aguanta). Para MVP self-hosted en máquina del coach o droplet pequeño.

### 11.2 Inicialización en backend

`app/observability/langfuse.py`:
- `init_langfuse()` lazy singleton.
- Lee env vars: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.
- Si `LANGFUSE_ENABLED=false` → no-op (FakeLangfuse).
- Hook FastAPI lifespan: `flush()` al shutdown.

### 11.3 Instrumentación

- **Decorador `@observe(as_type="agent", name="<node_name>")`** en cada nodo LangGraph.
- **`CallbackHandler`** pasado a cada `ChatGoogleGenerativeAI.ainvoke(..., config={"callbacks": [handler]})`.
- Trace ID = `external_run_id` (mismo del run), para correlación cross-system.

### 11.4 Tags por trace

| Tag | Fuente | Uso |
|---|---|---|
| `valida_num` | input | filtrar runs por válida |
| `athlete_id` | input (sin nombre) | drill-down sin PII |
| `prompt_version` | config | A/B y regresión |
| `coach_id` | request user | atribución |
| `use_case` | input | comparar costo por tipo de análisis |
| `explain_mode` | input | latencia con/sin |
| `critic_enabled` | feature flag | impacto crítico en calidad |

### 11.5 Cost tracking

Langfuse 3.x captura tokens automáticamente desde `usage_metadata` que `langchain-google-genai` setea. Costo se calcula contra tabla de pricing actualizable en UI Langfuse. Para Gemini Flash Lite asunción precio ~$0.075 / 1M input + $0.30 / 1M output (mayo 2026).

### 11.6 Alertas

- Budget alert: si `cost_usd_last_30d > $20` → email coach (configurable en Langfuse UI).
- Latency alert: si `p95_latency > 60s` → email DevOps.
- Eval score drop: si `judge_score_last_5_runs < 0.70` → bloquea próximos deploys (CI integration).

---

## 12. Eval framework

### 12.1 Estructura golden dataset

```
evals/race_analyst/golden/
├── case_001_thiago_progresion_baseline.json
├── case_002_inf_a_gap_podio.json
├── case_003_proyeccion_n3_low_confidence.json
├── ...
└── case_020_season_summary_15atletas.json
```

**Schema cada caso:**
```json
{
  "case_id": "case_001",
  "use_case": "race_progression",
  "input": {
    "athlete_id": 9001,
    "season": 2026,
    "valida_nums": [1,2,3,4],
    "explain_mode": false
  },
  "fixtures": {
    "race_results": [...],
    "marco_teorico_chunks_mocked": [...]
  },
  "expected": {
    "must_include_themes": [
      "habilidad técnica",
      "categoría pre-juvenil",
      "ventana entrenabilidad"
    ],
    "must_cite_principles": ["chunk_id_ltad_pjuv"],
    "forbidden_terms": [
      "potenciómetro",
      "suplementos",
      "creatina",
      "7 días por semana"
    ],
    "forbidden_pii": ["Thiago Duque", "Duque"],
    "max_words": 600,
    "min_recommendations": 2
  },
  "ideal_output": "# Análisis V-IV — Atleta-PJUV-A-001\n..."
}
```

### 12.2 Runner

`scripts/eval_race_analyst.py`:
- Para cada caso: invoca el grafo con `input + fixtures`, captura output.
- Aplica checks rule-based (themes, forbidden, word count) → `rule_score 0-1`.
- Llama LLM-as-judge con prompt `judge_v1.md` → `judge_score 0-1`.
- `final_score = 0.4 * rule_score + 0.6 * judge_score`.
- Output: `evals/race_analyst/results/<git_sha>_<timestamp>.json` + tabla resumen en stdout.

### 12.3 LLM-as-judge prompt (`prompts/eval/judge_v1.md`)

Estructura:
- System: "Eres un evaluador experto de análisis deportivo XCO juvenil. Evalúa rigor, alineación con principios LTAD, claridad pedagógica."
- User template: ideal_output + actual_output → asigna scores de 0-10 en dimensiones (precisión, principios, accionabilidad, tono, longitud), promedio normalizado.

### 12.4 CI integration

- GitHub Action `.github/workflows/eval-race-analyst.yml`:
  - Trigger: cambios en `services/race/ai/prompts/**` o manual.
  - Pasos: install deps → run `eval_race_analyst.py --golden` → fail if `avg(final_score) < 0.75`.
- Resultado en PR como check status + comment con tabla scores por caso.

### 12.5 Promoción de prompt versions

Workflow:
1. Crear `prompts/analyst_v2.md` (nueva versión).
2. Eval local: `python scripts/eval_race_analyst.py --prompt-version v2`.
3. Comparar contra baseline (`v1`) → ¿v2 mejora ≥5 %?
4. Si sí: PR cambia default `RACE_AGENT_PROMPT_VERSION=analyst_v2`.
5. CI corre eval con v2 → si pasa threshold → merge.

---

## 13. Modo aprendizaje (explain mode)

### 13.1 Diseño

- Toggle global UI → guarda en localStorage + zustand store.
- Cuando coach inicia run con toggle ON → frontend envía `explain_mode: true` en `POST /runs`.
- Backend: `RaceAnalystState.explain_mode = true`.
- Cada nodo del grafo tiene atributo `pedagogical_message` opcional (lista de mensajes en español, ej. tabla en §4.3).
- Cuando un nodo se ejecuta y `state.explain_mode=true`, antes/después de su lógica core persiste un evento en `agent_run_events`:
  ```json
  {"seq": N, "node": "...", "type": "explain", "data": {"phase": "before|after", "message": "..."}}
  ```
  El cliente lo recibe en el próximo poll vía `new_events`.
- Frontend renderiza en panel lateral colapsable (no interrumpe el flujo principal).

### 13.2 Generación de mensajes

- **Mensajes core estáticos:** definidos en cada `nodes/<name>.py` como constante. Cubren el "qué hace este nodo".
- **Mensajes dinámicos (futuro fase 2):** un mini-LLM call con prompt "explica al coach por qué este paso devolvió este output" — añade ~1s latencia, $$. **No en MVP.**

### 13.3 Tour interactivo (propuesta adicional)

> No está en las decisiones cerradas. Propuesta adicional: primer uso del módulo dispara un tour guiado (librería `intro.js` o `react-joyride`) que dispara explain mode automáticamente. Justificación: onboarding más suave para coach que no es ingeniero. Decidir si incluir en MVP o fase 2.

---

## 14. Migración v1 → v2 (refactor in-place)

### Fase 0 — Infra base (0.5 día, paralelizable)

**Cambios:**
- `requirements.txt` += `langgraph`, `langgraph-checkpoint-sqlite`, `langchain-google-genai`, `chromadb`, `sentence-transformers` (si fallback), `langfuse`.
- `alembic/versions/7a8b9c0d1e2f_add_agentic_race_tables.py` con las 4 tablas (§3).
- `docker-compose.langfuse.yml` + `data/chroma`, `data/langgraph` añadidos a `.gitignore`.
- `.env.example` añadidas vars Langfuse + Chroma + AI_MAX_TOKENS=8192.
- `app/config.py` campos nuevos `langfuse_*`, `chroma_path`, `race_agent_*`.

**Criterio éxito:** `alembic upgrade head` aplica limpio. `docker compose up langfuse-server` levanta UI en :3001. `pytest backend/tests/` sigue 339 verdes (no se tocó código v1).

**Rollback:** `alembic downgrade -1`.

### Fase 1 — Extracción `queries.py` (1 día)

**Cambios:**
- Crear `services/race/queries.py` con funciones puras: `fetch_results_for_athlete(db, athlete_id, season, valida_nums)`, `fetch_podium_context(db, category_id, event_id)`, `athlete_exists(db, athlete_id)`, etc.
- Refactor `analytics.py` para usar `queries.py` internamente (mismo output, sin cambio funcional).

**Criterio éxito:** 339 tests verdes. Coverage `queries.py` >= 95 %. CLI sigue funcionando.

**Rollback:** revert commit, `analytics.py` queda como antes.

### Fase 2 — Capa RAG (1 día)

**Cambios:**
- `services/race/rag/{ingest.py, retriever.py, citations.py}`.
- `scripts/rag_reindex.py` ejecutable.
- Primer indexado de `docs/01-marco-teorico.md`.
- Tests `tests/services/race/rag/`.

**Criterio éxito:** `python scripts/rag_reindex.py` genera ChromaDB en `data/chroma/`. `consultar_marco_teorico("ventana entrenabilidad 12 años")` retorna chunks relevantes con score >0.6.

**Rollback:** borrar `services/race/rag/` y `data/chroma/`.

### Fase 3 — Agentes core (2-3 días)

**Cambios:**
- `services/race/ai/{state.py, anonymizer.py, memory.py}`.
- `services/race/ai/nodes/*` (13 nodos).
- `services/race/ai/prompts/{analyst_v1.md, critic_v1.md, system_principles.md}`.
- Tests smoke grafo con mock LLM.
- Test smoke: `tests/services/race/ai/test_graph_smoke.py` invoca el grafo end-to-end con fixtures, sin LLM real (mock `FakeLLMProvider`).

**Criterio éxito:** grafo compila, smoke test verde, `test_anonymizer_zero_leak.py` verde con 1000 inputs.

**Rollback:** borrar `services/race/ai/`. Sin impacto en v1.

### Fase 4 — Grafo + checkpointing (1 día)

**Cambios:**
- `services/race/ai/graph.py` ensambla `StateGraph` con nodos + edges.
- Configurar `SqliteSaver(path="./data/langgraph/checkpoints.sqlite")`.
- Test HITL resume: `test_hitl_resume.py` interrupt → update_state → continue.

**Criterio éxito:** interrupt funciona, resume reanuda desde checkpoint.

### Fase 5 — Endpoints FastAPI + polling (0.5 días)

**Cambios:**
- `app/routers/race_analysis.py` con 7 endpoints (incluyendo `GET /runs/{id}/status` para polling).
- `app/schemas/race_ai.py` con Pydantic.
- Background task launcher + tracking registry.
- Tests `tests/routers/test_race_analysis_router.py`.

**Criterio éxito:** `curl http://localhost:8000/api/race-analysis/runs/<id>/status` retorna JSON con estado actualizado. POST/GET retornan códigos correctos. RBAC funciona (parent recibe 403).

### Fase 6 — Frontend UI (3-4 días)

**Cambios:**
- Componentes `frontend/src/components/race-analysis/*`.
- Rutas `frontend/src/routes/coach/race-analysis/*`.
- `useRunStatus` hook (TanStack Query + polling) + `raceAnalysis.ts` API client.
- Tests vitest + accessibility (jest-axe).

**Criterio éxito:** coach puede iniciar run, ver timeline, aprobar HITL, descargar PDF, usar chat — todo desde UI. Tests vitest >= 90 % coverage en código nuevo.

### Fase 7 — Eval + golden dataset (2 días)

**Cambios:**
- `evals/race_analyst/golden/` con 10-20 casos baseline.
- `scripts/eval_race_analyst.py` runner.
- GitHub Action CI.
- Documentación `docs/10-race-results/eval-baseline.md`.

**Criterio éxito:** runner ejecuta, scores baseline registrados. Threshold inicial 0.75.

### Fase 8 — Producción Langfuse + observability (1 día)

**Cambios:**
- Deploy Langfuse server (VPS coach o Hetzner droplet).
- Configurar `LANGFUSE_HOST` apuntando al server.
- Alertas configuradas en UI Langfuse.

**Criterio éxito:** primer run en staging genera trace visible en Langfuse, costo reportado correctamente.

### Resumen timeline

| Fase | Estimado | Acumulado |
|---|---|---|
| 0 — Infra base | 0.5 día | 0.5 |
| 1 — queries.py | 1 día | 1.5 |
| 2 — RAG | 1 día | 2.5 |
| 3 — Agentes core | 3 días | 5.5 |
| 4 — Grafo + checkpoint | 1 día | 6.5 |
| 5 — Endpoints + polling | 0.5 días | 7 |
| 6 — Frontend | 3.5 días | 10.5 |
| 7 — Eval | 2 días | 12.5 |
| 8 — Langfuse prod | 1 día | 13.5 |
| **Total** | **~14 días-dev** (3 semanas a tiempo parcial) | |

Asunción: dev solitario, ~5h/día. Coach revisa al final de cada fase.

---

## 15. Plan de aprendizaje en paralelo

> Objetivo: que el usuario (que aspira a AI developer) aprenda LangGraph/LLM agents construyendo este módulo. Cada ejercicio se hace ANTES de la fase correspondiente, en un repo sandbox separado.

### Ej1 — Hello-world LangGraph (1h)

**Prompt para Claude Code:**
> Crea un script Python que use LangGraph 1.2 con 3 nodos: `greet` (retorna "hola"), `enrich` (añade nombre), `farewell` (retorna mensaje final). State es TypedDict con `name: str`, `message: str`. Compila el grafo, ejecútalo con input `{"name": "Coach"}` y print del state final.

**Criterio aprendizaje:** entender StateGraph, nodes, edges, compile/invoke.

### Ej2 — Agregar HITL gate (1h)

**Prompt:**
> Toma el grafo del Ej1. Inserta un nodo `confirm` entre `enrich` y `farewell` que use `interrupt()` con mensaje "¿continuar con farewell?". Configura `SqliteSaver` con `./data/ej2.sqlite`. Demuestra el flujo: invoke → recibes interrupt → llama `Command(resume='yes')` → completa.

**Criterio:** entender interrupt, checkpointing, resume.

### Ej3 — Memory in-memory (1.5h)

**Prompt:**
> Crea un grafo de 2 nodos: `recall` (lee de un dict in-memory, devuelve últimas 3 entradas) y `record` (escribe al dict). Usa `Annotated[list, operator.add]` como reducer del state. Ejecuta 5 invocaciones con el mismo thread_id, demuestra que `recall` ve histórico.

**Criterio:** entender reducers, persistencia state.

### Ej4 — RAG con ChromaDB (2h)

**Prompt:**
> Crea script que indexe `docs/01-marco-teorico.md` en ChromaDB local usando `langchain-google-genai` para embeddings (o `paraphrase-multilingual-MiniLM-L12-v2` si no quieres API key). Después invoca queries como "principios para 10-12 años" y print top-3 chunks con score. Implementa idempotencia por chunk_id hash.

**Criterio:** entender chunking, embeddings, vector search, idempotencia.

### Ej5 — Langfuse tracing (1.5h)

**Prompt:**
> Toma el grafo del Ej4. Añade `@observe` decorator a cada función. Inicializa Langfuse cliente apuntando a `http://localhost:3001` (levanta Langfuse self-hosted con `docker compose -f docker-compose.langfuse.yml up`). Ejecuta 3 queries distintas, abre Langfuse UI, identifica el trace de cada una y screenshot.

**Criterio:** entender tracing, costo tracking, observability.

### Ej6 — Multi-agent supervisor (2-3h)

**Prompt:**
> Crea un grafo con dos agentes LLM (`writer` y `editor`) y un supervisor que enruta. Supervisor (otro LLM call) lee el último mensaje y decide si retorna al writer o termina. Implementa edge condicional con `add_conditional_edges` basado en el output del supervisor. Test: input "Escribe un haiku sobre ciclismo y refínalo 2 veces" → supervisor delega writer → editor → writer → END.

**Criterio:** entender supervisor pattern, conditional edges, handoffs.

### Ej7 — Eval framework (2h)

**Prompt:**
> Toma el grafo del Ej6. Crea 5 casos golden en JSON con input + ideal_output. Implementa runner que ejecuta cada caso, calcula similitud BLEU/ROUGE vs ideal (o LLM-as-judge si tienes API key). Output: tabla CSV con scores. Threshold: avg score ≥0.7.

**Criterio:** entender eval, golden dataset, judge prompt.

### Ej8 — TanStack Query polling pattern (1h, útil para fase 5+6)

**Prompt:**
> Crea endpoint FastAPI `/status/{job_id}` que retorna `{state, progress_pct, new_events}`. Crea componente React con `useQuery` + `refetchInterval: 2000` que muestra progreso en tiempo real y se detiene cuando `state === 'done'`. Simula un job que tarda 10 pasos × 1s.

**Criterio:** entender polling con TanStack Query, manejo de `refetchInterval` dinámico, acumulación de eventos incrementales.

### Total tiempo estimado

~12-14 horas de aprendizaje activo + ~30h implementación supervisada = ~45h. Asunción: 4-5 semanas calendario a tiempo parcial.

---

## 16. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Costo LLM explota (loop infinito, retries) | Media | Alto | Cap `retry_count <= 2` en state; budget alert Langfuse <$20/mes; hard limit en `max_tokens` |
| R2 | Gemini rate limits (Tier 1 free) | Alta | Medio | Exponential backoff 4x; fallback `gemini-2.0-flash`; queue de runs cliente-side (max 10 concurrentes) |
| R3 | LangGraph state corruption | Baja | Alto | Checkpointing SQLite; tests de propiedad sobre invariantes del state; rollback en `persist_insight` |
| R4 | Privacy leak (nombre real en log Gemini) | Baja | Crítico | Test sentinela en CI (`test_anonymizer_zero_leak`); middleware intercept request body; Langfuse self-hosted |
| R5 | Coach no entiende output del agente | Media | Alto | Modo aprendizaje + onboarding; primer run guiado; UI con citation tooltips |
| R6 | Vendor lock-in Gemini | Media | Medio | Capa abstracción LangChain → cambio provider 1 línea; misma API `ChatModel` para Anthropic/OpenAI |
| R7 | Polling overhead bajo carga | Baja | Bajo | ~15 requests/30s por run × N runs concurrentes. Mitigación: límite 10 runs concurrentes; ETag/304 si state no cambió |
| R8 | Marco teórico cambia, RAG desactualizado | Media | Bajo | Reindex automático en CI hook + manual CLI; chunk_id por hash invalida changes |
| R9 | LLM alucina números | Media | Alto | `analyst_agent` recibe métricas pre-calculadas determinísticamente; `critic_agent` revisa que no haya números inventados |
| R10 | Coach corrige drásticamente cada vez | Media | Medio | `coach_edits_count` métrica; si >2 promedio → reevaluar prompt; eval mejora prompt antes de redeploy |
| R11 | ChromaDB index corrupt | Baja | Bajo | `scripts/rag_reindex.py` reconstruye en <30s; backup volumen en docker |
| R12 | Langfuse server cae | Baja | Bajo (no bloqueante) | SDK Langfuse falla silently si server unreachable; el grafo sigue ejecutando |
| R13 | Migración Alembic FK violation con datos existentes | Baja | Alto | Migración solo crea tablas nuevas (no toca existentes); test de migración up/down en CI |
| R14 | Coach espera demasiado el resultado (>60s) | Media | Medio | Polling timeline da feedback cada 2s; `estimated_seconds_remaining` en cada respuesta; fallback "te aviso por email" |
| R15 | Gemini cambia precios | Alta | Medio | Cost monitoring Langfuse; budget alert; abstracción permite swap |

---

## 17. Criterios de éxito MVP

### 17.1 Métricas técnicas

| Métrica | Target | Verificación |
|---|---|---|
| p50 latencia análisis 1 atleta (1 use_case) | <30 s | Langfuse dashboard, query p50 |
| p95 latencia | <60 s | Langfuse |
| Coverage tests código nuevo (`services/race/ai/`, `services/race/rag/`, `routers/race_analysis.py`) | >=90 % | `pytest --cov` |
| Eval golden dataset avg score | >=0.80 | `scripts/eval_race_analyst.py` |
| 0 PII leaks | 100 % | `test_anonymizer_zero_leak` 1000 inputs verdes |
| Tests existentes (v1) | 339 verdes (sin regresión) | pytest CI |
| UI cross-browser | Chrome + Safari + Firefox | Playwright E2E |
| Lighthouse mobile score | >=85 perf, >=95 a11y | npm run lighthouse |

### 17.2 Métricas de adopción

| Métrica | Target (mes 1 post-launch) | Medición |
|---|---|---|
| Runs ejecutados | >=10 | `agent_runs` count |
| % runs `completed` (vs `rejected/failed`) | >=80 % | `agent_runs.status` |
| Avg `coach_edits_count` por insight | <=1.5 | media de `athlete_ai_insights.coach_edits_count` |
| Tiempo medio coach por análisis | <12 min | tracking UI o self-report |
| Costo total LLM | <$5/mes | Langfuse cost dashboard |

### 17.3 Validación funcional (end-to-end)

Checklist coach completa sin tocar terminal:
- [ ] Login → llega a `/coach/race-analysis`
- [ ] Click "Nuevo análisis" → form aparece
- [ ] Selecciona atleta + season + valida(s) + use_case → submit
- [ ] Timeline aparece, se actualiza cada 2s vía polling
- [ ] HITL gate dispara → ve draft, edita opcional, aprueba
- [ ] Reporte markdown se renderiza
- [ ] Botón "Descargar PDF" produce PDF abrible
- [ ] Email "✅ Análisis listo" llega a inbox del coach
- [ ] Próximo análisis del mismo atleta muestra "memoria reciente" inyectada
- [ ] Chat console responde preguntas con citaciones del marco teórico

### 17.4 Observabilidad

- [ ] Langfuse muestra trace de cada run con todos los nodos
- [ ] Cost por trace reportado correctamente
- [ ] Tags `valida_num`, `prompt_version`, `coach_id` filtrables
- [ ] Eval CI bloquea PR con score <0.75

---

## 18. Próximos pasos

### 18.1 Acciones inmediatas (esta semana)

1. **Validar decisiones cerradas con coach** — revisar §1.3 línea por línea, confirmar o ajustar (especialmente: persistencia `anonymization_mappings`, activar `critic_agent` desde MVP, modelo embeddings Gemini vs local).
2. **Resolver decisiones requeridas marcadas en el doc:**
   - §3.4 — TTL anonymization_mappings (propuesta: 90 días)
   - §5.2 — critic agent en MVP (propuesta: sí, eval después de 5 runs)
   - §6.2 — embeddings Gemini vs local (propuesta: Gemini)
   - §7.4 — borrado físico insights vs archive (propuesta: archive)
   - §13.3 — tour interactivo onboarding (propuesta: fase 2)
3. **Reservar API key Gemini** con cuota adecuada (Tier 1 free → 15 RPM Flash Lite es suficiente para MVP).
4. **Decidir host Langfuse:** VPS Hetzner (~$5/mes) o máquina coach.
5. **Aprobar timeline 14 días** o ajustar prioridades (ej. saltar critic_agent → -2 días adicionales).

### 18.2 Kickoff de implementación

Ejecutar:
```
/sc:workflow docs/10-race-results/v2-agentic-design.md
```

Esto generará el plan estructurado paso a paso, dispará agentes especializados (backend-architect, quality-engineer, security-engineer, data-analyst, etc.) y producirá los artifacts de cada fase.

### 18.3 Hitos sugeridos para review

| Hito | Cuándo | Entregable |
|---|---|---|
| H1: Infra + RAG funcionando | Fin Fase 2 | demo CLI `consultar_marco_teorico("...")` |
| H2: Grafo end-to-end con fake LLM | Fin Fase 4 | demo CLI invoca grafo, llega a `notify_coach` |
| H3: Polling funcionando con Gemini real | Fin Fase 5 | demo `watch -n 2 curl http://localhost:8000/api/race-analysis/runs/<id>/status` ve estado actualizarse cada 2s |
| H4: UI completa | Fin Fase 6 | demo coach hace análisis full sin terminal |
| H5: Eval baseline establecido | Fin Fase 7 | tabla scores golden, threshold 0.75 acordado |
| H6: Producción lista | Fin Fase 8 | trace en Langfuse cloud/self-hosted, dashboard activo |

### 18.4 Métricas a monitorear post-launch

- Semana 1: estabilidad (0 crashes), latencia p95
- Semana 2-4: adopción coach, avg edits, costo real vs estimado
- Mes 2: re-ejecutar eval golden con prompt v2 si hay edits frecuentes
- Mes 3: análisis ROI vs estimación §1.4

---

## Apéndice A — Tabla de versiones consolidada para `requirements.txt`

```
# Nuevas dependencias para v2 agéntico
langgraph>=1.2.0,<2.0
langgraph-checkpoint-sqlite>=2.0.5
langchain-core>=0.3.40
langchain-google-genai>=2.0.0
chromadb>=0.5.20
sentence-transformers>=3.0.0   # opcional, sólo si embeddings local
langfuse>=3.0.0

# Existentes (no cambian)
fastapi>=0.115
uvicorn[standard]>=0.40
sqlalchemy[asyncio]>=2.0
weasyprint>=62.3
jinja2>=3.1
google-genai>=1.0   # ya presente
```

## Apéndice B — Variables de entorno nuevas

```
# === LangGraph / Agentic ===
RACE_AGENT_ENABLED=true
RACE_AGENT_PROMPT_VERSION=analyst_v1
RACE_AGENT_CRITIC_ENABLED=true
RACE_AGENT_MAX_RETRIES=2
LANGGRAPH_CHECKPOINT_PATH=./data/langgraph/checkpoints.sqlite

# === Gemini (override existentes) ===
AI_PROVIDER=google
AI_MODEL=gemini-2.5-flash-lite
AI_MAX_TOKENS=8192       # ↑ desde 1024 para narrativa
AI_TEMPERATURE=0.3       # ↓ desde 0.4 para reproducibilidad

# === Langfuse ===
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_DB_PASS=changeme
LANGFUSE_CH_PASS=changeme
LANGFUSE_NEXTAUTH_SECRET=<openssl rand -hex 32>
LANGFUSE_SALT=<openssl rand -hex 32>
LANGFUSE_ENCRYPTION_KEY=<openssl rand -hex 32>

# === ChromaDB ===
CHROMA_PERSIST_PATH=./data/chroma
CHROMA_COLLECTION_MARCO=marco_teorico
RAG_EMBEDDING_PROVIDER=gemini   # gemini | sentence-transformers
RAG_EMBEDDING_MODEL=gemini-embedding-001
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=100
RAG_TOP_K=3
```

## Apéndice C — Asunciones acumuladas (para validar)

- **A1** El coach hoy invierte 45-60 min por válida en análisis manual (base para ROI).
- **A2** Gemini Flash Lite tier free aguanta carga del MVP (15 RPM, 1500 RPD).
- **A3** 90 días TTL para `anonymization_mappings` es suficiente para auditoría.
- **A4** Embeddings vía Gemini API es preferible a local (consistencia provider).
- **A5** Archive indefinido de insights (no borrado físico) cumple Ley 1581 a menos que padre solicite.
- **A6** SqliteSaver es suficiente para <100 runs/mes (no requiere Postgres).
- **A7** Coach no necesita acceso shell — toda interacción vía UI web.
- **A8** Langfuse self-hosted en VPS pequeño (~$5/mes) o máquina coach es viable.
- **A9** 1 docente-dev solitario, 5h/día → 14 días = ~3 semanas calendario.
- **A10** ~~TanStack Query no necesario para SSE~~ — **Decisión 2026-05-20:** se usa TanStack Query `refetchInterval` para polling. No se usa EventSource. Trade-off: ~2s lag vs complejidad SSE eliminada.
- **A11** Marco teórico cambia <1 vez/mes (no requiere reindex automático periódico).
- **A12** Padres NO acceden a este módulo. Sus datos van filtrados vía módulos existentes.
- **A13** Critic agent activado desde MVP (eval decide si mantener).
- **A14** Email notificación es Resend (provider existente), no se incorpora Spond.
- **A15** Modo aprendizaje usa mensajes estáticos por nodo (no genera dinámicamente con LLM en MVP).

---

**Fin del documento.** Total páginas estimadas: ~30 (markdown rendered). Siguiente paso: aprobación coach → `/sc:workflow docs/10-race-results/v2-agentic-design.md`.
