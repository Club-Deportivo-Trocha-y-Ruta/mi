# Race Results v2 — Agentic Redesign

**Project:** Club Deportivo Trocha y Ruta — Youth XCO
**Module:** `services/race/` (Phase 1.7 → 1.8)
**Date:** 2026-05-20
**Author:** System Architect agent
**Status:** Technical design — pending coach approval
**Audience:** coach (operation), architect/dev (implementation)

---

## 1. Executive Summary

### 1.1 Problem

The v1 of race-results (Phase 1.7) delivers a deterministic pipeline that ingests official Copa Valle PDFs, normalizes names/clubs, persists results in MySQL and exposes four tabular analytics (`athlete_progression`, `podium_gap`, `club_ranking`, `projection`). It works — but **the coach still translates DataFrames into narrative** and mentally compares each metric against LTAD principles from the theoretical framework. The bottleneck is not computation, it's interpretation.

### 1.2 Solution

**Hybrid deterministic + agentic redesign**:

- **Deterministic layer (intact):** parsing, normalization, matching, ingest, analytics queries. The 339 green tests are preserved.
- **Agentic layer (new):** a **LangGraph** workflow orchestrates the qualitative steps — anonymization, retrieval from theoretical framework, LLM call with per-athlete memory, HITL gates for coach review, insight persistence and notification. The output is a rendered markdown dashboard + downloadable PDF + consultative chat.
- **New UI:** route `/coach/race-analysis` in the existing React 19 SPA. Polling every 2 seconds via **TanStack Query**.
- **Observability:** Primary audit in MySQL — columns `cost_usd`, `tokens_in/out`, `latency_ms`, `prompt_version` in `athlete_ai_insights`. **Langfuse self-hosted optional, deferred to Phase 8** (activate only if Gemini cost >$10/month real, or coach asks for visual dashboard).
- **Eval:** versioned golden dataset + LLM-as-judge, blocking in CI before promoting prompt changes.

### 1.3 Closed decisions (summary)

| # | Decision | Value |
|---|---|---|
| 1 | Mode | Hybrid: deterministic for ETL, agentic for analysis |
| 2 | Agent framework | LangGraph 1.2.x. Langfuse self-hosted **optional**, deferred to F8 |
| 3 | LLM | Google Gemini 2.5 Flash Lite via `langchain-google-genai` |
| 4 | UI | React 19 + shadcn inside current SPA, route `/coach/race-analysis` |
| 5 | Streaming | HTTP polling every 2s → TanStack Query with refetchInterval |
| 6 | Memory | `athlete_ai_insights` table (recall N=3) |
| 7 | Privacy | Deterministic anonymization before LLM, re-hydration in frontend |
| 8 | HITL | Gates on parse-quality, TyR match <85, before email |
| 9 | Output | Markdown dashboard + PDF (weasyprint) + chat — no parent email in MVP |
| 10 | Eval | Golden dataset + LLM-as-judge blocking in CI |
| 11 | Learning mode | Global toggle, pedagogical messages per node |
| 12 | Refactor | In-place, strangler-fig inside `services/race/` |
| 13 | RAG | ChromaDB local over `docs/01-marco-teorico.md` |
| 14 | Notification | Resend email to coach when analysis finishes |
| 15 | Prompts | Versioned `.md` files in git, rendered with Jinja2, mandatory PR review |

### 1.4 Estimated ROI (assumptions)

Assumption: the coach today invests ~45-60 min per round (4-5 athletes × 10 min of manual analysis crossing 4 dashboards).

| Metric | Today (v1) | v2 goal | Δ |
|---|---|---|---|
| Time per athlete qualitative analysis | 10-12 min | 1-2 min (HITL review) | -85% |
| Time per round (5 athletes) | 50-60 min | 8-12 min | -80% |
| Decision traceability | none | `athlete_ai_insights` (cost, tokens, prompt_version, full output). Langfuse optional F8 | +∞ |
| Context reuse between rounds | manual | automatic (memory) | +∞ |
| Pedagogical quality for coach | depends | integrated `explain` mode | new |
| Risk of LTAD principle violation | medium (coach's mind) | low (guardrails + RAG) | ↓ |

Gemini Flash Lite estimated cost: ~USD 0.002 per athlete analysis (input ~3k tokens, output ~1.2k). 7 rounds × 8 athletes × 4 runs/season ≈ **USD 0.45/season**. Negligible.

### 1.5 High-level diagram

```mermaid
flowchart LR
    subgraph "Coach"
        UI["React 19 SPA<br/>/coach/race-analysis"]
    end
    subgraph "Backend FastAPI"
        ROUTER["routers/race_analysis.py<br/>(polling endpoints)"]
        GRAPH["LangGraph<br/>(state machine)"]
        DET["Deterministic v1 layer<br/>(pdf_parser, ingestor, analytics)"]
        RAG["ChromaDB<br/>marco-teorico"]
        MEM["athlete_ai_insights<br/>(MySQL)"]
        ANON["anonymization_mapping<br/>(in-memory + audit)"]
    end
    subgraph "LLM Provider"
        LLM["Gemini 2.5 Flash Lite<br/>via langchain-google-genai"]
    end
    subgraph "Observability (default DB)"
        AUDIT["athlete_ai_insights<br/>cost_usd, tokens, latency_ms"]
        LF["Langfuse self-hosted<br/>(optional, F8)"]
    end
    subgraph "Storage"
        DB[(MySQL Hostinger)]
    end

    UI -->|HTTP polling every 2s| ROUTER
    UI -->|HITL approvals POST| ROUTER
    ROUTER --> GRAPH
    GRAPH --> DET
    DET --> DB
    GRAPH --> RAG
    GRAPH --> MEM
    MEM --> DB
    GRAPH --> ANON
    GRAPH -->|prompts + anonymized data| LLM
    GRAPH -->|metrics| AUDIT
    GRAPH -.optional tracing.-> LF
    LLM -.cost if LF active.-> LF
    GRAPH -->|email Resend| UI
```

---

## 2. Complete system architecture

### 2.1 Layers diagram (detailed Mermaid)

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
        TIMELINE["AnalysisRunTimeline<br/>(consumes polling)"]:::ui
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
        N8["critic_agent<br/>(LLM, optional)"]:::agent
        N9[hitl_gate_review]:::agent
        N10[persist_insight]:::agent
        N11[rehydrate_names]:::agent
        N12[render_outputs]:::agent
        N13[notify_coach]:::agent
        CKPT[(SqliteSaver<br/>checkpoint)]:::data
    end

    subgraph TOOLS ["Tools and helpers (no LLM)"]
        QUERIES["queries.py<br/>(extracted from analytics)"]:::tools
        ANON_SVC["anonymizer.py<br/>(pseudonyms)"]:::tools
        RAG_SVC["rag/retriever.py<br/>(ChromaDB)"]:::tools
        MEM_SVC["memory/insights.py"]:::tools
        PDF_REND["pdf_renderer.py<br/>(weasyprint)"]:::tools
        EMAIL["notification/sender.py<br/>(Resend)"]:::tools
        V1["v1 services<br/>(pdf_parser, ingestor)"]:::tools
    end

    subgraph DATA ["Persistence"]
        MYSQL[(MySQL Hostinger<br/>race_* + athlete_ai_insights + agent_runs)]:::data
        CHROMA[(ChromaDB<br/>./data/chroma)]:::data
    end

    subgraph OBS ["Observability"]
        AUDIT_DB["athlete_ai_insights / agent_runs<br/>(cost_usd, tokens, latency_ms — default 8A)"]:::obs
        LF_HOST["Langfuse server<br/>(:3001 — optional F8B)"]:::obs
        LF_PG[(Langfuse Postgres — optional F8B)]:::obs
        LF_CH[(ClickHouse — optional F8B)]:::obs
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
    N7 --> AUDIT_DB
    N7 -.optional F8B.-> LF_HOST
    N10 --> MEM_SVC
    N12 --> PDF_REND
    N13 --> EMAIL

    QUERIES --> MYSQL
    MEM_SVC --> MYSQL
    RAG_SVC --> CHROMA
    V1 --> MYSQL
    AUDIT_DB --> MYSQL

    LF_HOST -.optional.-> LF_PG
    LF_HOST -.optional.-> LF_CH
```

### 2.2 Consolidated stack (minimum versions)

> Versions validated with Context7 (May 2026) and release notes of each project. Pin with `>=` allows compatible minor updates.

| Layer | Tech | Minimum version | Justification |
|---|---|---|---|
| **Orchestration** | `langgraph` | `>=1.2.0,<2.0` | 1.0 stabilized the API in Oct/2025; 1.2 (May 2026) brings `interrupt()` v2 |
| **Checkpointer** | `langgraph-checkpoint-sqlite` | `>=2.0.5` | For state machine between HITL gates; SQLite local in `./data/langgraph/checkpoints.sqlite` |
| **LLM client** | `langchain-google-genai` | `>=2.0.0` | Supports `gemini-2.5-flash-lite`, `thinking_budget`, structured output. Assumption: already in deps after this PR |
| **LangChain core** | `langchain-core` | `>=0.3.40` | Required by langgraph 1.x; already transitive |
| **Observability (default)** | native MySQL | — | Columns in `athlete_ai_insights` cover cost, tokens, latency, prompt_version |
| **Observability (optional F8B)** | `langfuse` | `>=3.0.0` | Only if F8B is activated. SDK 3.x uses `@observe` and separate `CallbackHandler` |
| **Langfuse server (optional F8B)** | `langfuse/langfuse:3` | Docker image tag `3` | Self-hosted compose: server + Postgres 16 + ClickHouse 24 (~2 GB RAM) |
| **Vector store** | `chromadb` | `>=0.5.20` | Stable `PersistentClient`; volume `./data/chroma/` |
| **Embeddings** | `sentence-transformers` | `>=3.0.0` | Model `paraphrase-multilingual-MiniLM-L12-v2` (Spanish, 384 dims, ~120 MB) — see §6 Assumption |
| **PDF render** | `weasyprint` | `>=62.3` | already in deps |
| **Template** | `jinja2` | `>=3.1` | already in deps; prompts and reports |
| **Frontend polling** | `@tanstack/react-query` | `^5.0` | already in deps; `refetchInterval: 2000` for polling, stops when `state ∈ {done, error}` |
| **Frontend markdown** | `react-markdown` | `^10.1.0` | already in deps; render the report |
| **Frontend charts** | `recharts` | `^3.8.1` | already in deps; podium-gap and projection visualization |

### 2.3 v1 (deterministic) vs v2 (agentic) boundaries

| Responsibility | Layer | Component | Calls LLM? |
|---|---|---|---|
| Parse PDF | v1 | `pdf_parser.py` | No |
| Normalize names/clubs | v1 | `normalizer.py` | No |
| Fuzzy match athletes | v1 | `matcher.py` | No |
| Transactional ingest | v1 | `ingestor.py` | No |
| Longitudinal SQL queries | v1 → v2 | `queries.py` (extracted from analytics) | No |
| Gap/delta/projection computation | v1 | `analytics.py` | No |
| Pre-LLM anonymization | v2 | `services/race/ai/anonymizer.py` | No |
| Theoretical framework retrieval | v2 | `services/race/rag/retriever.py` | No (embeddings yes) |
| Per-athlete memory recall | v2 | `services/race/ai/memory.py` | No |
| Qualitative analysis + recommendations | v2 | `analyst_agent` (LangGraph node) | Yes |
| Analysis critique (optional) | v2 | `critic_agent` (LangGraph node) | Yes |
| HITL approval | v2 | `hitl_gate_review` (interrupt) | No |
| Persist insight | v2 | `persist_insight` | No |
| Name re-hydration | v2 | `rehydrate_names` | No |
| Render markdown + PDF | v2 | `render_outputs` + `pdf_renderer.py` | No |
| Notify coach | v2 | `notification/sender.py` (existing) | No |
| Consultative chat | v2 | separate endpoint, same RAG + memory | Yes |

**Rule:** v1 NEVER calls v2. v2 CALLS v1 (as a deterministic tool/function). If v2 fails, v1 continues operating through the web import path. This preserves the 339 tests without changes.

### 2.4 File layout

```
backend/
├── app/
│   ├── models/
│   │   ├── ai_explanation.py           # (existing)
│   │   ├── athlete_ai_insight.py       # NEW — per-athlete agent memory
│   │   ├── agent_run.py                # NEW — one record per graph execution
│   │   ├── agent_run_event.py          # NEW — one record per polling event emitted
│   │   ├── anonymization_mapping.py    # NEW — pseudonym ↔ real audit
│   │   ├── race_*.py                   # (existing, no changes)
│   │   └── __init__.py                 # MODIFIED — export new ones
│   ├── schemas/
│   │   ├── race.py                     # (existing)
│   │   └── race_ai.py                  # NEW — agentic Pydantic schemas
│   ├── routers/
│   │   ├── race_analysis.py            # NEW — REST endpoints + polling
│   │   └── ...
│   ├── services/
│   │   ├── ai/                         # (existing, not touched)
│   │   └── race/
│   │       ├── pdf_parser.py           # (existing)
│   │       ├── csv_parser.py           # (existing)
│   │       ├── normalizer.py           # (existing)
│   │       ├── matcher.py              # (existing)
│   │       ├── ingestor.py             # (existing)
│   │       ├── analytics.py            # (existing, eventually extracted)
│   │       ├── queries.py              # NEW — reusable deterministic queries
│   │       ├── ai/                     # NEW subpackage
│   │       │   ├── __init__.py
│   │       │   ├── state.py            # TypedDict of graph state
│   │       │   ├── graph.py            # StateGraph construction
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
│   │       │   ├── anonymizer.py       # stable pseudonym strategy
│   │       │   ├── memory.py           # recall_recent_insights + persist
│   │       │   ├── chat_agent.py       # conversational agent (reuses RAG+mem)
│   │       │   ├── prompts/
│   │       │   │   ├── system_principles.md  # excerpt from theoretical framework
│   │       │   │   ├── analyst_v1.md
│   │       │   │   ├── critic_v1.md
│   │       │   │   ├── chat_v1.md
│   │       │   │   ├── explain_mode/
│   │       │   │   │   ├── analyst_v1.md
│   │       │   │   │   └── ...
│   │       │   │   └── eval/
│   │       │   │       └── judge_v1.md
│   │       │   └── pdf_renderer.py     # weasyprint + Jinja2 template
│   │       └── rag/
│   │           ├── __init__.py
│   │           ├── ingest.py           # chunking + theoretical framework indexing
│   │           ├── retriever.py        # consultar_marco_teorico API
│   │           └── citations.py        # Citation dataclass
│   ├── observability/                  # NEW (F8B optional)
│   │   ├── __init__.py
│   │   └── langfuse.py                 # client init + FakeLangfuse no-op (default disabled)
│   └── config.py                       # MODIFIED — ChromaDB settings; Langfuse (F8B optional)
├── alembic/versions/
│   └── 7a8b9c0d1e2f_add_agentic_race_tables.py  # NEW — revision 7a8b9c0d1e2f
│                                                  # down_revision: 64c263edd07f
├── scripts/
│   ├── rag_reindex.py                  # NEW — re-indexes theoretical framework
│   └── eval_race_analyst.py            # NEW — golden dataset runner
├── evals/
│   └── race_analyst/
│       ├── golden/
│       │   ├── case_001_thiago_progresion.json
│       │   ├── case_002_inf_a_gap_podio.json
│       │   └── ...                     # 10-20 cases
│       ├── judge_prompt_v1.md          # symlink to prompts/eval/
│       └── runner.py
├── data/                               # NEW — gitignored
│   ├── chroma/                         # Persistent ChromaDB
│   └── langgraph/
│       └── checkpoints.sqlite
└── tests/
    ├── services/
    │   ├── race/
    │   │   └── ai/
    │   │       ├── test_state.py
    │   │       ├── test_anonymizer.py
    │   │       ├── test_anonymizer_zero_leak.py  # property: 0 real names
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
│   │   └── raceAnalysis.ts             # NEW — fetch + polling with TanStack Query
│   ├── routes/
│   │   └── coach/
│   │       └── race-analysis/
│   │           ├── index.tsx           # NEW — page entry
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
│   │       └── ProgressionChart.tsx    # existing recharts
│   └── store/
│       └── explainMode.ts              # zustand toggle

docker-compose.yml                      # MODIFIED — adds chroma volume (does NOT touch langfuse)
docker-compose.langfuse.yml             # NEW — dedicated OPTIONAL compose, create only in F8B
.env.example                            # MODIFIED — ChromaDB vars + Langfuse (default disabled)

docs/10-race-results/
├── design.md                           # (existing, v1)
├── v2-agentic-design.md                # THIS DOCUMENT
├── learning-plan.md                    # NEW — progressive exercises §15
└── eval-baseline.md                    # NEW — golden dataset + scores
```

---

## 3. Data model (deltas)

### 3.1 Table `athlete_ai_insights` (NEW — agent memory)

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `athlete_id` | int FK→`athletes.id ON DELETE CASCADE` | subject athlete of the insight |
| `competitor_id` | int FK→`race_competitors.id` NULL | mapping to the race competitor (NULL if cross-season insight) |
| `season` | smallint | season (e.g. 2026) |
| `valida_num` | tinyint NULL | round that triggers the insight (NULL if end-of-season synthesis) |
| `event_id` | int FK→`race_events.id` NULL | specific event (NULL if synthesis) |
| `use_case` | varchar(32) | `race_progression`, `race_podium_gap`, `race_projection`, `race_season_summary` |
| `agent_run_id` | int FK→`agent_runs.id` NULL | traceability to the run that generated it |
| `summary_text` | text | final narrative approved by coach (post-HITL) |
| `recommendations_json` | JSON | `[{action, why, priority, principle_refs:[citation_ids]}]` |
| `metrics_snapshot_json` | JSON | snapshot of deterministic inputs (gaps, positions) — for reproducibility |
| `principles_cited_json` | JSON | `[{doc, section, chunk_id, relevance_score}]` |
| `confidence` | enum(`low`,`medium`,`high`) | inherited from `analytics.projection` + agent heuristic |
| `model` | varchar(128) | `gemini-2.5-flash-lite` |
| `prompt_version` | varchar(32) | `analyst_v1`, `analyst_v2`, ... |
| `coach_approved` | bool | true if passed HITL gate |
| `coach_edits_count` | smallint default 0 | how many editing iterations it had |
| `generated_at` | datetime | generation timestamp |
| `approved_at` | datetime NULL | coach approval timestamp |
| `generated_by_user_id` | int FK→`users.id` | coach who triggered the run |
| `archived_at` | datetime NULL | soft-delete for insights >2 seasons |
| `created_at`, `updated_at` | datetime | audit |

**Indexes:**
- `ix_insights_athlete_season (athlete_id, season DESC, valida_num DESC)` — for `recall_recent_insights(athlete_id, n=3)`
- `ix_insights_event (event_id)` — analysis by round
- `ix_insights_use_case (use_case, generated_at DESC)` — cross-athlete metrics (endpoint `/admin/ai-usage`; also usable by Langfuse if F8B active)

**Column justification:**
- `competitor_id` separate from `athlete_id`: an athlete can have multiple historical competitor_ids due to re-matching.
- `recommendations_json` with `principle_refs`: each recommendation cites the RAG source → auditability.
- `metrics_snapshot_json`: if the LLM changes, we can re-run with same inputs and compare.
- `prompt_version`: needed for comparable A/B via SQL (`GROUP BY prompt_version`); Langfuse uses it as a tag if F8B active.
- `coach_approved` + `coach_edits_count`: feedback loop — high edit count in one prompt version → signal of degradation.
- `archived_at`: soft-delete (GDPR/Ley 1581 — a parent can request deletion).

### 3.2 Table `agent_runs` (NEW — graph executions)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `external_run_id` | varchar(64) UNIQUE | UUID exposed to client for polling/HITL — never the internal PK |
| `graph_name` | varchar(64) | `race_analyst_v1` (allows multiple graphs coexisting) |
| `prompt_version` | varchar(32) | `analyst_v1` active at the time |
| `started_at` | datetime | |
| `finished_at` | datetime NULL | NULL if in progress or crashed |
| `status` | enum(`running`,`awaiting_hitl`,`completed`,`rejected`,`failed`,`cancelled`) | |
| `input_json` | JSON | input parameters (athlete_id, season, valida_nums) |
| `final_output_json` | JSON NULL | state snapshot at `END` (includes insight_id if committed) |
| `error_message` | text NULL | if `status=failed` |
| `langfuse_trace_id` | varchar(128) NULL | link to Langfuse trace for drill-down (NULL until F8B active) |
| `requested_by_user_id` | int FK→`users.id` | coach who triggered |
| `checkpoint_thread_id` | varchar(64) | thread_id passed to LangGraph SqliteSaver |
| `explain_mode` | bool default false | if learning mode was active |
| `cost_usd` | decimal(8,5) NULL | calculated after each `LLM.ainvoke` from `usage_metadata` + local pricing table. Primary cost tracking source (optional Langfuse reflects the same if F8B active) |
| `created_at`, `updated_at` | datetime | |

**Indexes:**
- `ix_agent_runs_user_started (requested_by_user_id, started_at DESC)`
- `ix_agent_runs_status (status)`
- `uq_agent_runs_external (external_run_id)`

**Justification:** `agent_runs` is the "header" of each analysis. `external_run_id` avoids exposing the autoincrement (URL security best practice). `checkpoint_thread_id` is the key to resuming from HITL.

### 3.3 Table `agent_run_events` (NEW — polling event log)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `run_id` | bigint FK→`agent_runs.id ON DELETE CASCADE` | |
| `seq` | int | monotonic order within the run (1..N) |
| `event_type` | enum(`node_start`,`node_end`,`hitl_request`,`hitl_response`,`explain`,`token`,`error`,`done`) | |
| `node_name` | varchar(64) NULL | emitting node (NULL for graph-level events) |
| `payload_json` | JSON | event data (state delta snapshot, pedagogical message, error...) |
| `created_at` | datetime | |

**Indexes:**
- `ix_run_events_run_seq (run_id, seq)`
- `ix_run_events_type (event_type)`

**Justification:** we persist events for two reasons — (1) the polling client can request `?since=42` and receive only new events without full replay; (2) retrospective auditing and debugging without opening Langfuse.

### 3.4 Table `anonymization_mappings` (NEW — privacy audit)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `run_id` | bigint FK→`agent_runs.id ON DELETE CASCADE` | |
| `pseudonym` | varchar(64) | `Atleta-PJUV-A-F-001` |
| `real_competitor_id` | int FK→`race_competitors.id` | reverse mapping (internal read-only) |
| `real_athlete_id` | int FK→`athletes.id` NULL | if confirmed TyR match |
| `salt_used` | varchar(16) | salt for hash if deterministic strategy is used |
| `created_at` | datetime | |

**Indexes:**
- `uq_anon_run_pseudonym (run_id, pseudonym)`
- `ix_anon_run_athlete (run_id, real_athlete_id)`

**Justification:** the table is NOT exposed via API. It serves to (1) re-hydrate names after the LLM call, (2) audit that no LLM response contains PII, (3) comply with Ley 1581 requirements — a parent can ask "what data about my child was sent to an external LLM" and we answer with this table.

⚠️ **Decision required:** keep the table persistent vs only in-memory per run. Persistent gives traceability but accumulates PII linked to pseudonyms. **Proposal:** persistent with 90-day TTL + scheduled cleanup. Assumption: 90 days is a sufficient window for retrospective audits without accumulating indefinitely.

### 3.5 Alembic migration

```
revision: 7a8b9c0d1e2f
down_revision: 64c263edd07f
description: Tables for agentic race-results module (insights, runs, events, anonymization)
```

**Up operations:**

1. `CREATE TABLE agent_runs` (with `external_run_id UNIQUE`)
2. `CREATE TABLE agent_run_events` (FK to agent_runs)
3. `CREATE TABLE athlete_ai_insights` (FK to athletes, agent_runs)
4. `CREATE TABLE anonymization_mappings` (FK to agent_runs)
5. Create indexes listed above.

**Down operations:** drop in reverse order (events → runs → insights → mappings).

**Post-migration validation:** script `scripts/verify_agentic_schema.py` that does `SELECT 1` on each table and validates FKs (without touching data).

---

## 4. LangGraph workflow — the core

### 4.1 Graph diagram

```mermaid
stateDiagram-v2
    [*] --> validate_input
    validate_input --> load_race_data : valid input
    validate_input --> [*] : invalid input (error)

    load_race_data --> anonymize : data loaded
    anonymize --> compute_metrics
    compute_metrics --> retrieve_principles
    retrieve_principles --> recall_memory
    recall_memory --> analyst_agent

    analyst_agent --> critic_agent : output OK
    analyst_agent --> hitl_gate_review : output with warnings

    critic_agent --> hitl_gate_review : review OK
    critic_agent --> analyst_agent : retry (max 2)

    hitl_gate_review --> persist_insight : approved
    hitl_gate_review --> analyst_agent : edited (returns with feedback)
    hitl_gate_review --> notify_coach : rejected (skip persist)

    persist_insight --> rehydrate_names
    rehydrate_names --> render_outputs
    render_outputs --> notify_coach
    notify_coach --> [*]

    note right of hitl_gate_review
        interrupt() pauses the graph.
        The coach approves/edits/rejects
        via POST /runs/{id}/hitl/{step}.
        Resumes with Command(resume=...).
    end note
```

### 4.2 State schema (TypedDict)

```python
# services/race/ai/state.py
class RaceAnalystState(TypedDict, total=False):
    # ---- Deterministic input ----
    run_id: int                         # FK agent_runs.id
    external_run_id: str                # UUID
    athlete_id: int
    season: int
    valida_nums: list[int]              # e.g [3, 4] to analyze V-III + V-IV
    explain_mode: bool

    # ---- Loaded data ----
    competitor_id: int | None
    category_id: int | None
    race_results_raw: list[dict]        # race_results rows for the athlete
    podium_context_raw: list[dict]      # podium times by event/category
    series_meta: dict

    # ---- Anonymization ----
    anonymization_map: dict[int, str]   # {competitor_id: pseudonym}
    reverse_map: dict[str, int]         # {pseudonym: competitor_id}
    salt: str

    # ---- Computed metrics (deterministic) ----
    progression_df: list[dict]
    podium_gap_df: list[dict]
    projection: dict

    # ---- RAG + memory ----
    principles_retrieved: list[dict]    # [{chunk_id, content, score, source}]
    recent_insights: list[dict]         # last N athlete insights

    # ---- LLM outputs ----
    analyst_draft: dict | None          # JSON parsed, before critic
    critic_feedback: list[str]          # critic observations
    critic_pass: bool
    retry_count: int                    # limit 2

    # ---- HITL ----
    hitl_action: str | None             # 'approve'|'edit'|'reject'
    hitl_edits: dict | None             # coach replaces draft fields
    hitl_at: str | None                 # ISO datetime

    # ---- Final output ----
    final_insight: dict                 # pre-render snapshot
    rendered_markdown: str
    pdf_path: str | None
    email_sent: bool

    # ---- Traceability ----
    langfuse_trace_id: str
    errors: list[dict]                  # non-fatal failures accumulator
    pedagogical_messages: list[dict]    # generated if explain_mode=True
```

**Decision on `total=False`:** allows each node to write only its state slice without having to initialize all fields. LangGraph merges automatically (last-write-wins by default; custom reducers if needed, e.g. `pedagogical_messages: Annotated[list, operator.add]`).

### 4.3 Node list — expected I/O

| # | Node | Reads from state | Writes to state | Calls tools | LLM | Pedagogical |
|---|---|---|---|---|---|---|
| 1 | `validate_input` | `athlete_id`, `season`, `valida_nums` | `errors` if fails | `queries.athlete_exists` | No | "Verifying athlete exists and has results..." |
| 2 | `load_race_data` | `athlete_id`, `season`, `valida_nums` | `race_results_raw`, `series_meta`, `competitor_id`, `category_id` | `queries.fetch_results_for_athlete`, `queries.fetch_podium_context` | No | "Loading results from MySQL — no LLM yet..." |
| 3 | `anonymize` | `race_results_raw`, `podium_context_raw`, `athlete_id` | `anonymization_map`, `reverse_map`, `salt` | `anonymizer.generate_mapping`, persist to `anonymization_mappings` | No | "Replacing names with pseudonyms before talking to external LLM..." |
| 4 | `compute_metrics` | `race_results_raw`, `series_meta` | `progression_df`, `podium_gap_df`, `projection` | `analytics.athlete_progression`, `analytics.podium_gap`, `analytics.projection` | No | "Calculating gaps deterministically — the LLM doesn't invent numbers..." |
| 5 | `retrieve_principles` | `progression_df`, `athlete_id` (→ age → LTAD group) | `principles_retrieved` | `rag.retriever.consultar_marco_teorico` with derived queries | No (embeddings yes) | "Looking for LTAD principles relevant to this age group..." |
| 6 | `recall_memory` | `athlete_id`, `season` | `recent_insights` | `memory.recall_recent_insights(athlete_id, n=3)` | No | "Retrieving the 3 most recent insights for this athlete to avoid repetition..." |
| 7 | `analyst_agent` | ALL (anonymized data + principles + memory) | `analyst_draft` | Gemini Flash Lite LLM, prompt `analyst_v1` | Yes | "Asking the LLM to synthesize analysis. Giving it ONLY pseudonyms..." |
| 8 | `critic_agent` | `analyst_draft`, `principles_retrieved` | `critic_feedback`, `critic_pass` | LLM with `critic_v1` prompt | Yes (optional) | "Another LLM checks that the analysis cites real principles and doesn't contradict LTAD..." |
| 9 | `hitl_gate_review` | `analyst_draft`, `critic_feedback` | `hitl_action`, `hitl_edits`, `hitl_at` | LangGraph `interrupt()` | No | "Pausing here — coach reviews before persisting..." |
| 10 | `persist_insight` | `analyst_draft`, `hitl_edits`, `run_id` | `final_insight` | `memory.persist_insight` | No | "Saving the approved insight so the next analysis remembers it..." |
| 11 | `rehydrate_names` | `final_insight`, `reverse_map` | `final_insight` updated with real names | `anonymizer.rehydrate_text` | No | "Replacing pseudonyms with real names — this does NOT go to the LLM..." |
| 12 | `render_outputs` | `final_insight`, `progression_df`, etc. | `rendered_markdown`, `pdf_path` | `pdf_renderer.render` | No | "Generating markdown + PDF with weasyprint..." |
| 13 | `notify_coach` | `run_id`, `email_destination` | `email_sent` | `notification.send_race_analysis_ready` (Resend template) | No | "Sending you an email when everything is done." |

### 4.4 Checkpointing

**Decision:** `langgraph-checkpoint-sqlite` (not Postgres, not MySQL).

**Reasons:**
- MySQL has no official saver (only Postgres). Creating one is over-engineering for single-coach use.
- SQLite local in Docker volume `./data/langgraph/checkpoints.sqlite` is sufficient (<100 runs/month).
- Isolation of graph state from business state — the graph can corrupt without affecting `race_*` tables.

**Thread strategy:**
- `checkpoint_thread_id = external_run_id` (UUID). Guarantees uniqueness and allows resume via `Command(resume=...)`.
- Indefinite persistence until `status in (completed, rejected, failed)`. Monthly cleanup job deletes terminated checkpoints >30 days.

**SQLite table generated by LangGraph:** `checkpoints` with columns `(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)`. We don't touch it directly.

### 4.5 Error handling

| Error type | Strategy | Where handled |
|---|---|---|
| Validation error (invalid input) | early abort, status=`failed`, clear message to frontend | `validate_input` |
| DB read timeout (load_race_data) | exponential retry 3x (200ms, 1s, 5s); if fails → status=`failed` | tenacity decorator in `queries.py` |
| ChromaDB not responding | fallback: `principles_retrieved = []` + warning to coach; continue | `retrieve_principles` |
| Gemini rate limit (429) | exponential backoff 4x with jitter; if persists 5 min → fallback `gemini-2.0-flash` (previous model) | wrapper in `analyst_agent`, `critic_agent` |
| Gemini timeout (>30s) | abort node, mark `analyst_draft=None`, go to `hitl_gate_review` with message "LLM down — coach decides manually" | wrapper |
| Guardrails reject output | retry 1x with injected `critic_feedback`; if fails again → HITL with raw draft + warning | `analyst_agent` |
| HITL timeout (>24h without coach response) | status=`awaiting_hitl` persistent, not cancelled. Reminder email at 4h | scheduled job `agent_runs_reaper.py` |
| Persist insight FK violation | rollback, status=`failed`, Sentry alert | `persist_insight` |
| PDF render fails (weasyprint) | continue with markdown only + warning; coach downloads PDF later | `render_outputs` |

**Dead-letter:** if a run stays `failed` >7 days, it is archived with full `error_message` and the coach is notified via email with link to run detail (`/admin/ai-usage/runs/{external_run_id}` from `agent_runs` + `agent_run_events`). If F8B active, the email also includes the `langfuse_trace_id`.

---

## 5. Agent system: single vs multi

### 5.1 Recommendation: **multi-agent with implicit supervisor (linear)**

Not a formal supervisor pattern (which would add an extra LLM routing node), but a linear composition with three LLM roles:

1. **`analyst_agent`** — produces the qualitative analysis + recommendations from data + principles + memory.
2. **`critic_agent`** — reviews analyst output: does it cite real principles? does it contradict LTAD? does it include real names (PII leak)? does it mention numbers not provided?
3. **`chat_agent`** — separate conversational agent (NOT part of the analysis graph), exposes endpoint `/chat`. Reuses RAG + athlete memory.

### 5.2 Evaluated trade-offs

| Option | Pros | Cons | Risk |
|---|---|---|---|
| **A) Single-agent** (analyst only) | Simple, 1 LLM call per run, minimum cost | No second opinion → hallucination risk passes to coach | Medium |
| **B) Linear multi-agent** (analyst + critic) | +1 LLM call catches inconsistencies before HITL → less coach edit churn | 2x cost (~$0.004 vs $0.002 per analysis) | Low |
| **C) Formal supervisor pattern** (LLM routes nodes) | Maximum flexibility, exploration | Over-engineering for known flow; latency +2-3s per routing decision | High |
| **D) Multi-agent with explicit handoff** (analyst delegates to topic specialists) | High quality if topics are orthogonal | Complex coordination, latency, high cost | High |

**Final recommendation:** **B (linear multi-agent)** for MVP. The `critic_agent` can be DISABLED via feature flag `RACE_AGENT_CRITIC_ENABLED=false` if in the golden eval baseline the critic doesn't add differential value >5% in score.

⚠️ **Required coach decision:** activate critic from MVP or wait for baseline? **Proposal:** activate, evaluate after 5-10 real runs.

### 5.3 Consultative chat (`chat_agent`)

- Separate endpoint `POST /chat` — does NOT share graph with the analysis flow.
- Conversational session by `session_id` (not LangGraph thread_id), persisted in process memory (Redis if it scales; for MVP, in-memory dict with 1h TTL).
- Agent tools:
  - `consultar_marco_teorico(query)` (RAG)
  - `obtener_insights_atleta(athlete_id, n=5)` (memory)
  - `fetch_results(athlete_id, season)` (queries.py)
- Anonymization: if the coach asks "how is Thiago doing?", the agent internally converts `Thiago` → `competitor_id`, anonymizes data, calls LLM, re-hydrates response.
- **No HITL** — chat is direct. Coach corrects in next turn if desired.

Assumption: chat doesn't require cross-session persistence in MVP. If cross-session history is desired, scale later.

---

## 6. RAG layer over theoretical framework

### 6.1 Chunking strategy

| Parameter | Value | Reason |
|---|---|---|
| Strategy | `RecursiveCharacterTextSplitter` (LangChain) or native equivalent | Respects markdown hierarchy (#, ##, ###, paragraph) |
| Chunk size | 800 tokens | Balance between sufficient context and retrieval precision |
| Overlap | 100 tokens | Avoids losing sentences that cross boundaries |
| Separators | `["\n## ", "\n### ", "\n\n", "\n", ". "]` | Prioritizes headings |
| Metadata per chunk | `{doc, h1, h2, h3, chunk_id, source_path, lines}` | Citation tracking |

**Documents to index (MVP Phase):**
- `docs/01-marco-teorico.md` (290 lines, ~6k tokens) — ~10-15 chunks
- Assumption: theoretical framework today is 1 monolithic file. If in the future it splits into subdocs (`marco-teorico/`), re-index all.

### 6.2 Embeddings — model selection

| Model | Dim | Size | Language | Cost | Recommendation |
|---|---|---|---|---|---|
| `text-embedding-3-small` (OpenAI) | 1536 | API | multilingual (ok Spanish) | $0.02 / 1M tokens | Good quality but +1 vendor |
| `gemini-embedding-001` (Google) | 768 | API | multilingual | ~free tier | Consistency with Gemini LLM; **recommended** |
| `paraphrase-multilingual-MiniLM-L12-v2` (HuggingFace) | 384 | 120 MB local | multilingual | $0 (local) | Simpler, no network for indexing |
| `intfloat/multilingual-e5-large` | 1024 | 2.2 GB local | top-tier multilingual | $0 | Best local quality but heavy |

**Recommendation:** **`gemini-embedding-001`** via `langchain-google-genai.GoogleGenerativeAIEmbeddings`. Advantages:
- Consistency with the LLM (same provider, same account).
- Robust Spanish multilingual.
- Negligible cost (source text <10k tokens, single indexing + sporadic queries).

⚠️ **Fallback if not wanting to depend on Google for embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` local (sentence-transformers). Decide based on coach preference for minimizing vendor lock-in.

### 6.3 ChromaDB persistence

```
data/chroma/
  chroma.sqlite3
  <collection_uuid>/
    ...
```

- Docker volume: `./data/chroma:/data/chroma` (gitignored).
- `PersistentClient(path="./data/chroma")`.
- Collection: `marco_teorico` (1 only; future: `glosario_xco`, `historial_clinico_agregado`...).
- Default HNSW config (M=16, ef_construction=200) — sufficient for <1000 vectors.

### 6.4 Re-indexing

| Trigger | Strategy | Implementation |
|---|---|---|
| Manual (coach edits theoretical framework) | CLI `scripts/rag_reindex.py [--doc=marco-teorico]` | Read → chunk → upsert by deterministic `chunk_id` (content hash) |
| CI hook | GitHub Action on push to `docs/01-marco-teorico.md` → runs reindex on deploy | Assumption: Render deploy script triggers it |
| Scheduled | No (docs change rarely) | n/a |

**Idempotency:** `chunk_id = sha256(doc_path + chunk_idx + content)[:16]`. If content doesn't change, upsert is a no-op.

### 6.5 Agent tool

```python
# services/race/rag/retriever.py
def consultar_marco_teorico(
    query: str,
    top_k: int = 3,
    filter_h1: Optional[str] = None,
) -> list[Citation]:
    """
    Returns relevant chunks with metadata for citation.
    Citation = {chunk_id, doc, section_path, content, score, source_lines}
    """
```

Usage in `analyst_agent`:
- Queries generated dynamically based on context (e.g. if `athlete.age < 13` → query "principles training 10-12 years"; if `gap_to_p1_pct > 30` → "technique before power").
- Top-3 per query, max 2-3 queries per analysis → ~6-9 chunks in context window.
- Each returned citation has `chunk_id` that is persisted in `principles_cited_json` → coach-side traceability.

---

## 7. Per-athlete memory

### 7.1 `AthleteAIInsight` model (section 3.1)

### 7.2 `recall_recent_insights` function

```python
# services/race/ai/memory.py
async def recall_recent_insights(
    db: AsyncSession,
    athlete_id: int,
    n: int = 3,
    exclude_archived: bool = True,
) -> list[InsightMemoryItem]:
    """
    Returns the last N approved insights (coach_approved=True)
    ordered by (season DESC, valida_num DESC, generated_at DESC).
    Excludes archived_at IS NOT NULL if exclude_archived=True.
    """
```

**InsightMemoryItem (Pydantic):**
```python
class InsightMemoryItem(BaseModel):
    insight_id: int
    season: int
    valida_num: int | None
    use_case: str
    summary_text: str           # narrative the LLM will see
    key_recommendations: list[str]  # extracted top-3 from recommendations_json
    generated_at: datetime
    confidence: str
```

**Prompt injection:**
- The `analyst_v1.md` prompt has a `{% if recent_insights %}` section that renders a block:
  ```
  ## Athlete memory (prior insights)
  {% for ins in recent_insights %}
  - Round {{ins.valida_num}} ({{ins.season}}): {{ins.summary_text[:300]}}...
    Recommendations: {{ins.key_recommendations | join(', ')}}
  {% endfor %}
  ```
- The LLM has the instruction: "avoid literally repeating prior recommendations; if the pattern persists, recommend it as urgent".

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
    Inserts new record. Does flush + commit.
    If coach_approved=False, still persists but with flag for later analysis.
    """
```

### 7.4 Garbage collection / archive

- Monthly job `scripts/archive_old_insights.py`:
  - Marks `archived_at = NOW()` for insights with `season < current_year - 1` and NOT cited in last 90 days.
  - Does not delete (audit); only excludes from recall.
- Coach UI: "Complete history" tab shows archived with tag.

⚠️ **Required decision:** physical deletion after X years or indefinite archive? **Proposal:** indefinite archive, physical deletion only if parent explicitly requests (Ley 1581 right of suppression).

---

## 8. Anonymization (privacy by design)

### 8.1 Chosen strategy: **persistent per run + deterministic by hash**

**Hybrid:**
- For each run, generate pseudonyms based on `salt = run.external_run_id` + `competitor_id` → deterministic hash → formatted suffix.
- Pseudonym format: `Atleta-{CATEGORY_CODE}-{HASH_3DIGITS}` e.g. `Atleta-PJUV-A-F-001`.
- **Different salt per run** → same competitor has different pseudonym between runs → minimizes cross-run correlation in LLM logs.
- **Deterministic within run** → if the graph retries or resumes, mapping persists.

### 8.2 Implementation (high level — no code)

`anonymizer.generate_mapping(run_id, competitor_ids, category_code) -> dict[int, str]`:
1. For each `competitor_id`, compute `hash_id = hmac_sha256(run.salt, str(competitor_id))[:3]`.
2. Generate `pseudonym = f"Atleta-{category_code}-{hash_id.upper()}"`.
3. Insert rows in `anonymization_mappings` (transaction).
4. Return `{competitor_id: pseudonym}` + `{pseudonym: competitor_id}`.

`anonymizer.anonymize_payload(data, mapping) -> dict`:
1. Recursively traverse the dict/list payload.
2. Replace any `competitor_id` or `display_name` with pseudonym.
3. If free text found (e.g. `notes`), apply regex of known names.
4. Return "clean" payload.

`anonymizer.rehydrate_text(llm_output, reverse_map) -> str`:
1. Traverse the markdown text.
2. Replace each found pseudonym with the real `display_name`.
3. Return re-hydrated text (UI only; NEVER sent back to LLM).

### 8.3 Property test: zero leak

`tests/services/race/ai/test_anonymizer_zero_leak.py`:

- Generate a synthetic payload with 5 athletes (real names + common Colombian surnames).
- Anonymize with the function.
- **Property assertion:** no string from the original list (full name, first name, last name, nickname if exists) appears in the anonymized payload.
- Repeat with 1000 random inputs (property-based test with `hypothesis`).
- If property fails on any input → test red → blocks merge.

Additional:
- Test that captures `httpx`/`requests` mocks: no POST to the Gemini endpoint contains real names (intercept layer).

### 8.4 Runtime audit

- FastAPI middleware on endpoint `/api/race-analysis/runs` logs in structured log: `{run_id, anonymized=True, mapping_count=N}`.
- Logs NEVER include the mapping or real names (only counts).
- Langfuse (if F8B active): prompt and completion are sent with pseudonyms. Self-hosted on a VPS controlled by the club — does not externalize PII. If Langfuse is never activated, the deterministic pre-LLM anonymization remains the primary defense.

---

## 9. REST API (FastAPI endpoints)

> All endpoints require JWT auth (header `Authorization: Bearer ...`). RBAC: unless specified, **coach** + **admin**. Parents do NOT access this module (their data they receive filtered via other modules).

### 9.1 `POST /api/race-analysis/runs` — start analysis

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
    status_url: str         # e.g "/api/race-analysis/runs/{run_id}/status"
    estimated_seconds: int  # heuristic: 15 + 5*len(valida_nums)
```

**Errors:**
- `400` athlete doesn't exist or is not confirmed TyR
- `400` season without events
- `403` user is not coach/admin
- `409` there's already an active run for (athlete, use_case) (avoids concurrency)
- `429` >10 runs in user's queue (rate limit)

**Side effects:** creates `agent_runs` row, triggers LangGraph in background task (`asyncio.create_task` + tracking in in-memory registry), returns immediately.

### 9.2 `GET /api/race-analysis/runs/{run_id}/status` — polling

> **Decision 2026-05-20:** SSE discarded in favor of polling — simpler, works in any provider (Render free tier, proxies), without validating timeouts. Accepted trade-off: ~2s UI lag vs realtime. Acceptable for ~30s analysis.

**Query params:**
- `since` (optional, int): returns only events with `seq > since` (avoids full replay on each poll)

**Auth:** required (run owner coach or admin)

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
    {"seq": 24, "node": "anonymize", "type": "explain", "data": {"message": "Replacing names..."}, "ts": "..."}
  ]
}
```

**Client behavior:**
- Polls every 2 seconds with `?since=<last_seq_seen>`.
- Stops polling when `state ∈ {done, error}`.
- TanStack Query pattern: `refetchInterval: state === 'done' || state === 'error' ? false : 2000`.

**RBAC:** only the `requested_by_user_id` can read. Admin can read any.

**Optimization:** if state hasn't changed since last poll, server can return `304 Not Modified` with ETag based on last emitted `seq`.

### 9.3 `POST /api/race-analysis/runs/{run_id}/hitl/{step_id}` — HITL response

**Body:**
```python
class HITLResponseBody(BaseModel):
    action: Literal["approve","edit","reject"]
    edits: dict | None = None        # if action=edit, partial of analyst_draft
    rejection_reason: str | None = None
```

**Response 200:**
```python
class HITLResponseAck(BaseModel):
    run_id: str
    step_id: str
    accepted: bool
    next_step: str | None            # e.g "persist_insight" or None if rejected
```

**Errors:**
- `404` run or step doesn't exist
- `409` run not in `awaiting_hitl` state
- `422` edits don't validate against draft schema

**Side effects:** invokes `graph.update_state(...)` + `graph.invoke(Command(resume=...))`. Persists `hitl_response` event in `agent_run_events` (visible in next poll).

### 9.4 `GET /api/race-analysis/runs/{run_id}/result` — final JSON

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
    langfuse_trace_url: str | None   # only if user is admin
```

### 9.5 `GET /api/race-analysis/runs/{run_id}/pdf` — PDF download

**Response 200:** binary `application/pdf`. Filename `analisis_<athlete_id>_<season>_v<valida>_<run_id_short>.pdf`.
**404:** if `pdf_available=false` or not yet completed.

### 9.6 `POST /api/race-analysis/chat` — consultative chat

**Body:**
```python
class ChatRequest(BaseModel):
    session_id: str | None = None    # null → creates new
    message: str = Field(min_length=1, max_length=2000)
    context_athlete_id: int | None = None  # optional, ties session to an athlete
```

**Response 200:** complete response when LLM finishes (no streaming). `{full_text, citations, session_id}`. Client uses `useQuery` with `refetchInterval` while `state === 'pending'`.

**RBAC:** coach/admin.

### 9.7 `GET /api/race-analysis/athletes/{athlete_id}/insights` — history

**Query params:**
- `season` (optional)
- `use_case` (optional)
- `include_archived` (default false)
- `limit` (default 20, max 100)

**Response:**
```python
class InsightsList(BaseModel):
    athlete_id: int
    insights: list[InsightSummary]
    total: int
```

**RBAC:** coach/admin. Parent does NOT see (their data they receive via other filtered modules).

---

## 10. Frontend components (React)

### 10.1 Layout and routes

```
/coach/race-analysis                  → RaceAnalysisDashboard (tabs)
/coach/race-analysis/runs/:runId      → RunDetailPage
/coach/race-analysis/insights         → InsightsHistoryPage
```

### 10.2 Components

#### `RaceAnalysisDashboard` (`routes/coach/race-analysis/index.tsx`)
- Main layout with shadcn `Tabs`:
  - **Start analysis** — form (athlete, season, valida_nums, use_case, explain_mode toggle) → `POST /runs`
  - **Active runs** — list with status badge (running/awaiting_hitl/completed/failed) — auto-refresh every 5s
  - **Historical insights** — link to `InsightsHistoryPage`
- Permanent `ExplainModeBanner` with global toggle (zustand).

#### `AnalysisRunTimeline` (reusable component)
- Props: `runId: string`
- Hook: `useQuery` with `refetchInterval: 2000` pointing to `/api/race-analysis/runs/${runId}/status?since=<last_seq>`. Stops when `state ∈ {done, error}`.
- Renders vertical timeline (shadcn `Stepper` or custom):
  - Each `node_end` → step ✅
  - `node_start` without `node_end` yet → step ⏳ (spinner)
  - `hitl_request` → step ⏸️ with embedded `HITLApprovalCard`
  - `error` → step ❌ red
- If `explainMode=true`, below each step shows the `explain` message (expandable panel).
- When `done` arrives → shows `MarkdownReportViewer` + download PDF button.

#### `HITLApprovalCard`
- Props: `runId`, `stepId`, `draft`, `criticFeedback`, `principlesCited`
- UI:
  - Renders `draft.summary_text` in markdown (initially read-only)
  - "Edit" button → switch to editable `Textarea`
  - Collapsible section "Critic LLM says:" → list `criticFeedback`
  - Section "Cited principles:" → cards with chunk + score
  - Three buttons: **Approve**, **Approve with changes**, **Reject**
- `onApprove`/`onEdit`/`onReject` → `POST /runs/:id/hitl/:step` with TanStack mutation.

#### `MarkdownReportViewer`
- Props: `markdown: string`, `progressionData?: ...`, `podiumGapData?: ...`
- Render: `react-markdown` with plugins (`remark-gfm` for tables).
- Inline visualization injection: if markdown contains `<chart data-type="progression">...`, substitutes with `<ProgressionChart />` (recharts).
- Footer: "Download PDF", "Copy link", "Share via email" buttons.

#### `ChatConsole`
- Layout split: chat history (virtualized scroll) + bottom input.
- Session persistence: localStorage by `coach_id`, maximum last conversation.
- Complete response: hook `useChatSend` (TanStack Query mutation) that does POST and waits for complete JSON response. Shows spinner while `isPending`.
- Each bot message shows "citations" (RAG chunks used) in expandable footer.
- If question names an athlete, captures `context_athlete_id` and maintains it in next turns.

#### `ExplainModeBanner`
- Sticky yellow light top banner.
- Toggle `🏫 Learning mode` with tooltip "Activates pedagogical explanations for each agent step".
- State in zustand `useExplainModeStore`, persisted in localStorage.

### 10.3 TanStack Query hooks

```typescript
// frontend/src/api/raceAnalysis.ts
useStartRun()                          // mutation POST /runs
useRunStatus(runId)                    // query polling GET /runs/:id/status
useRunResult(runId)                    // query GET /runs/:id/result
useRunPdfUrl(runId)                    // memoized URL
useApproveStep(runId, stepId)          // mutation POST /hitl
useChatSend(sessionId)                 // mutation POST /chat (complete response)
useAthleteInsights(athleteId, opts)    // query with pagination
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

## 11. Observability — default DB + optional Langfuse (F8)

### 11.0 Default — MySQL Audit (no extra infra)

For MVP (F0–F7 and F8 option 8A) the complete audit lives in columns of `athlete_ai_insights` and `agent_runs`:

| Metric | Column | Source |
|---|---|---|
| Cost USD per run | `athlete_ai_insights.cost_usd` | calculated in code after each `LLM.ainvoke` with local pricing table |
| Tokens in/out | `athlete_ai_insights.tokens_in`, `tokens_out` | `usage_metadata` from `langchain-google-genai` |
| Latency ms | `agent_runs.latency_ms` | `time.perf_counter()` wrap per node |
| Prompt version | `athlete_ai_insights.prompt_version` | tag in graph config |
| Full output | `athlete_ai_insights.markdown_output` | persisted |
| LangGraph node trace | `agent_run_events` | events per node for drill-down |

**Admin endpoint `GET /admin/ai-usage?days=30`** aggregates total cost, p50/p95 latency, run count, fail rate. Coach sees basic dashboard via admin frontend.

**Budget guard:** function `_check_budget()` before each run queries `SUM(cost_usd) last 30d`; if >$20 blocks + coach email.

`langfuse_trace_id` remains NULL until F8B is activated.

### 11.1 Docker Compose setup — **OPTIONAL (F8B)**

Activate only if one of these conditions is met post-MVP:
- Real Gemini cost >$10/month (justifies Hetzner VPS ~$5/month)
- Coach asks for visual trace dashboard
- Serious prompt A/B testing is planned

New services in `docker-compose.langfuse.yml` (optional profile, create only in F8B):

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

**Estimated RAM:** ~2 GB total (Postgres 200 MB, ClickHouse 700 MB, Server 800 MB, headroom 300 MB).

**Production:** same compose deployable on VPS (not Render free tier, can't handle it). For MVP self-hosted on coach's machine or small droplet.

### 11.2 Backend initialization

`app/observability/langfuse.py`:
- `init_langfuse()` lazy singleton.
- Reads env vars: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.
- **Default `LANGFUSE_ENABLED=false`** → no-op (FakeLangfuse). Agentic stack works identically without Langfuse.
- FastAPI lifespan hook: `flush()` on shutdown (no-op if disabled).

### 11.3 Instrumentation

- **Decorator `@observe(as_type="agent", name="<node_name>")`** on each LangGraph node.
- **`CallbackHandler`** passed to each `ChatGoogleGenerativeAI.ainvoke(..., config={"callbacks": [handler]})`.
- Trace ID = `external_run_id` (same as the run), for cross-system correlation.

### 11.4 Tags per trace

| Tag | Source | Use |
|---|---|---|
| `valida_num` | input | filter runs by round |
| `athlete_id` | input (no name) | drill-down without PII |
| `prompt_version` | config | A/B and regression |
| `coach_id` | request user | attribution |
| `use_case` | input | compare cost by analysis type |
| `explain_mode` | input | latency with/without |
| `critic_enabled` | feature flag | critic quality impact |

### 11.5 Cost tracking

**Default (without Langfuse):** after each `LLM.ainvoke` the code reads `usage_metadata` from `langchain-google-genai`, multiplies by local pricing table (`PRICING_PER_1M = {"gemini-2.5-flash-lite": {"in": 0.075, "out": 0.30}}` — May 2026) and persists in `athlete_ai_insights.cost_usd`.

**If F8B active:** Langfuse 3.x captures tokens automatically from the same `usage_metadata` and calculates cost against a pricing table updatable in its UI. Both sources coincide by construction.

### 11.6 Alerts

**Default (8A):**
- Runtime budget guard: if `SUM(cost_usd) 30d > $20` → blocks new runs + coach email.
- Latency: daily cron reads p95 `agent_runs.latency_ms` last 7d; if >60s → DevOps email.
- Eval score drop: if `judge_score_last_5_runs < 0.70` → blocks next deploys (CI integration).

**If F8B active:** same alerts configurable in Langfuse UI as visual complement.

---

## 12. Eval framework

### 12.1 Golden dataset structure

```
evals/race_analyst/golden/
├── case_001_thiago_progresion_baseline.json
├── case_002_inf_a_gap_podio.json
├── case_003_proyeccion_n3_low_confidence.json
├── ...
└── case_020_season_summary_15atletas.json
```

**Schema per case:**
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
      "technical skill",
      "pre-youth category",
      "windows of trainability"
    ],
    "must_cite_principles": ["chunk_id_ltad_pjuv"],
    "forbidden_terms": [
      "power meter",
      "supplements",
      "creatine",
      "7 days a week"
    ],
    "forbidden_pii": ["Thiago Duque", "Duque"],
    "max_words": 600,
    "min_recommendations": 2
  },
  "ideal_output": "# Analysis V-IV — Atleta-PJUV-A-001\n..."
}
```

### 12.2 Runner

`scripts/eval_race_analyst.py`:
- For each case: invokes the graph with `input + fixtures`, captures output.
- Applies rule-based checks (themes, forbidden, word count) → `rule_score 0-1`.
- Calls LLM-as-judge with prompt `judge_v1.md` → `judge_score 0-1`.
- `final_score = 0.4 * rule_score + 0.6 * judge_score`.
- Output: `evals/race_analyst/results/<git_sha>_<timestamp>.json` + summary table in stdout.

### 12.3 LLM-as-judge prompt (`prompts/eval/judge_v1.md`)

Structure:
- System: "You are an expert evaluator of youth XCO sports analysis. Evaluate rigor, alignment with LTAD principles, pedagogical clarity."
- User template: ideal_output + actual_output → assigns scores of 0-10 in dimensions (precision, principles, actionability, tone, length), normalized average.

### 12.4 CI integration

- GitHub Action `.github/workflows/eval-race-analyst.yml`:
  - Trigger: changes in `services/race/ai/prompts/**` or manual.
  - Steps: install deps → run `eval_race_analyst.py --golden` → fail if `avg(final_score) < 0.75`.
- Result in PR as check status + comment with scores table per case.

### 12.5 Prompt version promotion

Workflow:
1. Create `prompts/analyst_v2.md` (new version).
2. Local eval: `python scripts/eval_race_analyst.py --prompt-version v2`.
3. Compare against baseline (`v1`) → does v2 improve ≥5%?
4. If yes: PR changes default `RACE_AGENT_PROMPT_VERSION=analyst_v2`.
5. CI runs eval with v2 → if passes threshold → merge.

---

## 13. Learning mode (explain mode)

### 13.1 Design

- Global UI toggle → saves in localStorage + zustand store.
- When coach starts run with toggle ON → frontend sends `explain_mode: true` in `POST /runs`.
- Backend: `RaceAnalystState.explain_mode = true`.
- Each graph node has an optional `pedagogical_message` attribute (list of messages in Spanish, e.g. table in §4.3).
- When a node executes and `state.explain_mode=true`, before/after its core logic it persists an event in `agent_run_events`:
  ```json
  {"seq": N, "node": "...", "type": "explain", "data": {"phase": "before|after", "message": "..."}}
  ```
  The client receives it in the next poll via `new_events`.
- Frontend renders in a collapsible side panel (doesn't interrupt main flow).

### 13.2 Message generation

- **Static core messages:** defined in each `nodes/<name>.py` as a constant. Cover the "what this node does".
- **Dynamic messages (future phase 2):** a mini-LLM call with prompt "explain to the coach why this step returned this output" — adds ~1s latency, $$. **Not in MVP.**

### 13.3 Interactive tour (additional proposal)

> Not in the closed decisions. Additional proposal: first use of the module triggers a guided tour (library `intro.js` or `react-joyride`) that automatically fires explain mode. Justification: smoother onboarding for a coach who is not an engineer. Decide whether to include in MVP or phase 2.

---

## 14. v1 → v2 migration (in-place refactor)

### Phase 0 — Base infra (0.5 day, parallelizable)

**Changes:**
- `requirements.txt` += `langgraph`, `langgraph-checkpoint-sqlite`, `langchain-google-genai`, `chromadb`, `sentence-transformers` (if fallback), `langfuse` (SDK present but stack off by default).
- `alembic/versions/7a8b9c0d1e2f_add_agentic_race_tables.py` with the 4 tables (§3). Column `langfuse_trace_id` remains NULL until F8B.
- `data/chroma`, `data/langgraph` added to `.gitignore`. `docker-compose.langfuse.yml` **NOT created in F0** — deferred to optional F8B.
- `.env.example` adds Chroma vars + AI_MAX_TOKENS=8192 + `LANGFUSE_ENABLED=false` (default).
- `app/config.py` new fields `chroma_path`, `race_agent_*`. Fields `langfuse_*` present but `langfuse_enabled` default `False`.

**Success criterion:** `alembic upgrade head` applies cleanly. `pytest backend/tests/` still 339 green (v1 code not touched). **Does not require running Langfuse**.

**Rollback:** `alembic downgrade -1`.

### Phase 1 — Extract `queries.py` (1 day)

**Changes:**
- Create `services/race/queries.py` with pure functions: `fetch_results_for_athlete(db, athlete_id, season, valida_nums)`, `fetch_podium_context(db, category_id, event_id)`, `athlete_exists(db, athlete_id)`, etc.
- Refactor `analytics.py` to use `queries.py` internally (same output, no functional change).

**Success criterion:** 339 tests green. Coverage `queries.py` >= 95%. Web import path still works.

**Rollback:** revert commit, `analytics.py` restored as before.

### Phase 2 — RAG layer (1 day)

**Changes:**
- `services/race/rag/{ingest.py, retriever.py, citations.py}`.
- `scripts/rag_reindex.py` executable.
- First indexing of `docs/01-marco-teorico.md`.
- Tests `tests/services/race/rag/`.

**Success criterion:** `python scripts/rag_reindex.py` generates ChromaDB in `data/chroma/`. `consultar_marco_teorico("windows of trainability 12 years")` returns relevant chunks with score >0.6.

**Rollback:** delete `services/race/rag/` and `data/chroma/`.

### Phase 3 — Core agents (2-3 days)

**Changes:**
- `services/race/ai/{state.py, anonymizer.py, memory.py}`.
- `services/race/ai/nodes/*` (13 nodes).
- `services/race/ai/prompts/{analyst_v1.md, critic_v1.md, system_principles.md}`.
- Graph smoke tests with mock LLM.
- Smoke test: `tests/services/race/ai/test_graph_smoke.py` invokes graph end-to-end with fixtures, without real LLM (mock `FakeLLMProvider`).

**Success criterion:** graph compiles, smoke test green, `test_anonymizer_zero_leak.py` green with 1000 inputs.

**Rollback:** delete `services/race/ai/`. No impact on v1.

### Phase 4 — Graph + checkpointing (1 day)

**Changes:**
- `services/race/ai/graph.py` assembles `StateGraph` with nodes + edges.
- Configure `SqliteSaver(path="./data/langgraph/checkpoints.sqlite")`.
- HITL resume test: `test_hitl_resume.py` interrupt → update_state → continue.

**Success criterion:** interrupt works, resume resumes from checkpoint.

### Phase 5 — FastAPI endpoints + polling (0.5 days)

**Changes:**
- `app/routers/race_analysis.py` with 7 endpoints (including `GET /runs/{id}/status` for polling).
- `app/schemas/race_ai.py` with Pydantic.
- Background task launcher + tracking registry.
- Tests `tests/routers/test_race_analysis_router.py`.

**Success criterion:** `curl http://localhost:8000/api/race-analysis/runs/<id>/status` returns JSON with updated state. POST/GET return correct codes. RBAC works (parent receives 403).

### Phase 6 — Frontend UI (3-4 days)

**Changes:**
- Components `frontend/src/components/race-analysis/*`.
- Routes `frontend/src/routes/coach/race-analysis/*`.
- `useRunStatus` hook (TanStack Query + polling) + `raceAnalysis.ts` API client.
- Vitest tests + accessibility (jest-axe).

**Success criterion:** coach can start run, see timeline, approve HITL, download PDF, use chat — all from UI. Vitest tests >= 90% coverage on new code.

### Phase 7 — Eval + golden dataset (2 days)

**Changes:**
- `evals/race_analyst/golden/` with 10-20 baseline cases.
- `scripts/eval_race_analyst.py` runner.
- GitHub Action CI.
- Documentation `docs/10-race-results/eval-baseline.md`.

**Success criterion:** runner executes, baseline scores recorded. Initial threshold 0.75.

### Phase 8 — Production + observability (0.5–1.5 day)

> Option **8A default** (DB audit, 0.5 day) vs option **8B optional** (Langfuse self-hosted, +1 day). See `v2-implementation-workflow.md` §"Phase 8" decision table.

**Changes option 8A (default):**
- Endpoint `/admin/ai-usage` aggregating metrics from `athlete_ai_insights`.
- Runtime budget guard: blocks if `SUM(cost_usd) 30d > $20`.
- Basic ops runbook.

**Changes option 8B (optional, only if activated):**
- Deploy Langfuse server (coach VPS or Hetzner droplet).
- Configure `LANGFUSE_HOST` pointing to the server, flip `LANGFUSE_ENABLED=true`.
- Alerts configured in Langfuse UI.

**Success criterion 8A:** first run in staging generates row in `athlete_ai_insights` with cost_usd, tokens, latency_ms. Admin endpoint returns aggregates.

**Success criterion 8B (if activated):** first run in staging generates visible trace in Langfuse, cost reported correctly.

### Summary timeline

| Phase | Estimate | Accumulated |
|---|---|---|
| 0 — Base infra | 0.5 day | 0.5 |
| 1 — queries.py | 1 day | 1.5 |
| 2 — RAG | 1 day | 2.5 |
| 3 — Core agents | 3 days | 5.5 |
| 4 — Graph + checkpoint | 1 day | 6.5 |
| 5 — Endpoints + polling | 0.5 days | 7 |
| 6 — Frontend | 3.5 days | 10.5 |
| 7 — Eval | 2 days | 12.5 |
| 8 — Prod (8A default DB / 8B Langfuse optional) | 0.5–1.5 day | 13–14 |
| **Total** | **~14 dev-days** (3 weeks part-time) | |

Assumption: solo dev, ~5h/day. Coach reviews at end of each phase.

---

## 15. Parallel learning plan

> Goal: have the user (who aspires to be an AI developer) learn LangGraph/LLM agents by building this module. Each exercise is done BEFORE the corresponding phase, in a separate sandbox repo.

### Ex1 — Hello-world LangGraph (1h)

**Prompt for Claude Code:**
> Create a Python script that uses LangGraph 1.2 with 3 nodes: `greet` (returns "hello"), `enrich` (adds name), `farewell` (returns final message). State is TypedDict with `name: str`, `message: str`. Compile the graph, execute it with input `{"name": "Coach"}` and print the final state.

**Learning criterion:** understand StateGraph, nodes, edges, compile/invoke.

### Ex2 — Add HITL gate (1h)

**Prompt:**
> Take the graph from Ex1. Insert a `confirm` node between `enrich` and `farewell` that uses `interrupt()` with message "continue to farewell?". Configure `SqliteSaver` with `./data/ej2.sqlite`. Demonstrate the flow: invoke → receive interrupt → call `Command(resume='yes')` → complete.

**Criterion:** understand interrupt, checkpointing, resume.

### Ex3 — In-memory memory (1.5h)

**Prompt:**
> Create a graph with 2 nodes: `recall` (reads from an in-memory dict, returns last 3 entries) and `record` (writes to the dict). Use `Annotated[list, operator.add]` as state reducer. Run 5 invocations with the same thread_id, demonstrate that `recall` sees history.

**Criterion:** understand reducers, state persistence.

### Ex4 — RAG with ChromaDB (2h)

**Prompt:**
> Create a script that indexes `docs/01-marco-teorico.md` in local ChromaDB using `langchain-google-genai` for embeddings (or `paraphrase-multilingual-MiniLM-L12-v2` if you don't want an API key). Then invoke queries like "principles for 10-12 year olds" and print top-3 chunks with score. Implement idempotency by chunk_id hash.

**Criterion:** understand chunking, embeddings, vector search, idempotency.

### Ex5 — Langfuse tracing (1.5h) — **OPTIONAL, only if F8B activated**

**Prompt:**
> Take the graph from Ex4. Add `@observe` decorator to each function. Initialize Langfuse client pointing to `http://localhost:3001` (start Langfuse self-hosted with `docker compose -f docker-compose.langfuse.yml up`). Run 3 different queries, open Langfuse UI, identify the trace for each and screenshot.

**Criterion:** understand tracing, cost tracking, observability.

**Note:** skippable if F8B is not activated. Cost tracking and primary observability live in `athlete_ai_insights` (default 8A). Do this exercise only when deciding to activate Langfuse.

### Ex6 — Multi-agent supervisor (2-3h)

**Prompt:**
> Create a graph with two LLM agents (`writer` and `editor`) and a supervisor that routes. Supervisor (another LLM call) reads the last message and decides to return to writer or end. Implement conditional edge with `add_conditional_edges` based on supervisor output. Test: input "Write a haiku about cycling and refine it 2 times" → supervisor delegates writer → editor → writer → END.

**Criterion:** understand supervisor pattern, conditional edges, handoffs.

### Ex7 — Eval framework (2h)

**Prompt:**
> Take the graph from Ex6. Create 5 golden cases in JSON with input + ideal_output. Implement runner that runs each case, calculates BLEU/ROUGE similarity vs ideal (or LLM-as-judge if you have API key). Output: CSV table with scores. Threshold: avg score ≥0.7.

**Criterion:** understand eval, golden dataset, judge prompt.

### Ex8 — TanStack Query polling pattern (1h, useful for phases 5+6)

**Prompt:**
> Create FastAPI endpoint `/status/{job_id}` that returns `{state, progress_pct, new_events}`. Create React component with `useQuery` + `refetchInterval: 2000` that shows progress in real time and stops when `state === 'done'`. Simulate a job that takes 10 steps × 1s.

**Criterion:** understand polling with TanStack Query, dynamic `refetchInterval` handling, incremental event accumulation.

### Total estimated time

~12-14 hours of active learning + ~30h supervised implementation = ~45h. Assumption: 4-5 calendar weeks part-time.

---

## 16. Risks and mitigations

| # | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| R1 | LLM cost explodes (infinite loop, retries) | Medium | High | Cap `retry_count <= 2` in state; runtime budget guard DB blocks if `SUM(cost_usd) 30d > $20`; hard limit on `max_tokens`. Langfuse alert optional (F8B) reinforces. |
| R2 | Gemini rate limits (Tier 1 free) | High | Medium | Exponential backoff 4x; fallback `gemini-2.0-flash`; client-side run queue (max 10 concurrent) |
| R3 | LangGraph state corruption | Low | High | SQLite checkpointing; property tests on state invariants; rollback in `persist_insight` |
| R4 | Privacy leak (real name in Gemini log) | Low | Critical | Sentinel test in CI (`test_anonymizer_zero_leak`); request body intercept middleware; **deterministic pre-LLM anonymization is the primary defense — does not depend on Langfuse**. If F8B active, self-hosted Langfuse reinforces (does not externalize PII). |
| R5 | Coach doesn't understand agent output | Medium | High | Learning mode + onboarding; first guided run; UI with citation tooltips |
| R6 | Gemini vendor lock-in | Medium | Medium | LangChain abstraction layer → change provider 1 line; same `ChatModel` API for Anthropic/OpenAI |
| R7 | Polling overhead under load | Low | Low | ~15 requests/30s per run × N concurrent runs. Mitigation: max 10 concurrent runs; ETag/304 if state unchanged |
| R8 | Theoretical framework changes, RAG outdated | Medium | Low | Automatic reindex in CI hook + manual CLI; chunk_id by hash invalidates changes |
| R9 | LLM hallucinates numbers | Medium | High | `analyst_agent` receives deterministically pre-calculated metrics; `critic_agent` checks there are no invented numbers |
| R10 | Coach drastically corrects each time | Medium | Medium | `coach_edits_count` metric; if >2 average → revisit prompt; eval improves prompt before redeploy |
| R11 | ChromaDB index corrupted | Low | Low | `scripts/rag_reindex.py` rebuilds in <30s; docker volume backup |
| R12 | Langfuse server goes down | Low | Low (non-blocking) | Langfuse SDK fails silently if server unreachable; graph continues executing |
| R13 | Alembic migration FK violation with existing data | Low | High | Migration only creates new tables (doesn't touch existing ones); migration up/down test in CI |
| R14 | Coach waits too long for result (>60s) | Medium | Medium | Polling timeline gives feedback every 2s; `estimated_seconds_remaining` in each response; fallback "I'll notify you by email" |
| R15 | Gemini changes pricing | High | Medium | DB cost monitoring (`athlete_ai_insights.cost_usd`) + budget guard; local pricing table versioned in code; abstraction allows swap. Langfuse optional (F8B) reflects the same. |

---

## 17. MVP success criteria

### 17.1 Technical metrics

| Metric | Target | Verification |
|---|---|---|
| p50 latency 1 athlete analysis (1 use_case) | <30 s | `agent_runs.latency_ms` query p50 (Langfuse if 8B) |
| p95 latency | <60 s | `agent_runs.latency_ms` query p95 (Langfuse if 8B) |
| Coverage new code (`services/race/ai/`, `services/race/rag/`, `routers/race_analysis.py`) | >=90% | `pytest --cov` |
| Golden dataset eval avg score | >=0.80 | `scripts/eval_race_analyst.py` |
| 0 PII leaks | 100% | `test_anonymizer_zero_leak` 1000 green inputs |
| Existing tests (v1) | 339 green (no regression) | pytest CI |
| UI cross-browser | Chrome + Safari + Firefox | Playwright E2E |
| Lighthouse mobile score | >=85 perf, >=95 a11y | npm run lighthouse |

### 17.2 Adoption metrics

| Metric | Target (month 1 post-launch) | Measurement |
|---|---|---|
| Runs executed | >=10 | `agent_runs` count |
| % `completed` runs (vs `rejected/failed`) | >=80% | `agent_runs.status` |
| Avg `coach_edits_count` per insight | <=1.5 | mean of `athlete_ai_insights.coach_edits_count` |
| Average coach time per analysis | <12 min | UI tracking or self-report |
| Total LLM cost | <$5/month | `SUM(athlete_ai_insights.cost_usd) last 30d` (Langfuse dashboard if 8B) |

### 17.3 Functional validation (end-to-end)

Complete coach checklist without touching terminal:
- [ ] Login → arrives at `/coach/race-analysis`
- [ ] Click "New analysis" → form appears
- [ ] Select athlete + season + round(s) + use_case → submit
- [ ] Timeline appears, updates every 2s via polling
- [ ] HITL gate fires → sees draft, optionally edits, approves
- [ ] Markdown report renders
- [ ] "Download PDF" button produces openable PDF
- [ ] "✅ Analysis ready" email arrives in coach's inbox
- [ ] Next analysis for same athlete shows injected "recent memory"
- [ ] Chat console answers questions with citations from theoretical framework

### 17.4 Observability

**Default (8A) — DB audit:**
- [ ] `athlete_ai_insights` being populated with cost_usd, tokens, latency_ms, prompt_version
- [ ] Endpoint `/admin/ai-usage` returns aggregates
- [ ] Budget guard active (blocks if >$20/30d)
- [ ] Eval CI blocks PR with score <0.75

**Optional (8B) — Langfuse activated:**
- [ ] Langfuse shows trace of each run with all nodes
- [ ] Cost per trace reported correctly
- [ ] Tags `valida_num`, `prompt_version`, `coach_id` filterable

---

## 18. Next steps

### 18.1 Immediate actions (this week)

1. **Validate closed decisions with coach** — review §1.3 line by line, confirm or adjust (especially: persistence of `anonymization_mappings`, activate `critic_agent` from MVP, Gemini vs local embeddings model).
2. **Resolve required decisions marked in the doc:**
   - §3.4 — TTL anonymization_mappings (proposal: 90 days)
   - §5.2 — critic agent in MVP (proposal: yes, eval after 5 runs)
   - §6.2 — Gemini vs local embeddings (proposal: Gemini)
   - §7.4 — physical insight deletion vs archive (proposal: archive)
   - §13.3 — interactive onboarding tour (proposal: phase 2)
3. **Reserve Gemini API key** with adequate quota (Tier 1 free → 15 RPM Flash Lite is sufficient for MVP).
4. **Langfuse:** **NOT required** for MVP. Deferred to optional F8B post-launch. Decide host (Hetzner VPS ~$5/month vs coach's machine) only if one of these conditions is met: real Gemini cost >$10/month, coach asks for visual dashboard, or serious prompt A/B testing.
5. **Approve 14-day timeline** or adjust priorities (e.g. skip critic_agent → -2 additional days).

### 18.2 Implementation kickoff

Run:
```
/sc:workflow docs/10-race-results/v2-agentic-design.md
```

This will generate the structured step-by-step plan, spawn specialized agents (backend-architect, quality-engineer, security-engineer, data-analyst, etc.) and produce artifacts for each phase.

### 18.3 Suggested review milestones

| Milestone | When | Deliverable |
|---|---|---|
| H1: Infra + RAG working | End Phase 2 | CLI demo `consultar_marco_teorico("...")` |
| H2: End-to-end graph with fake LLM | End Phase 4 | CLI demo invokes graph, reaches `notify_coach` |
| H3: Polling working with real Gemini | End Phase 5 | demo `watch -n 2 curl http://localhost:8000/api/race-analysis/runs/<id>/status` sees state updating every 2s |
| H4: Complete UI | End Phase 6 | demo coach does full analysis without terminal |
| H5: Baseline eval established | End Phase 7 | golden scores table, 0.75 threshold agreed |
| H6: Production ready | End Phase 8 | `athlete_ai_insights` being populated + `/admin/ai-usage` active + budget guard (Langfuse optional 8B) |

### 18.4 Metrics to monitor post-launch

- Week 1: stability (0 crashes), p95 latency
- Weeks 2-4: coach adoption, avg edits, real vs estimated cost
- Month 2: re-run golden eval with prompt v2 if there are frequent edits
- Month 3: ROI analysis vs §1.4 estimate

---

## Appendix A — Consolidated versions table for `requirements.txt`

```
# New dependencies for v2 agentic
langgraph>=1.2.0,<2.0
langgraph-checkpoint-sqlite>=2.0.5
langchain-core>=0.3.40
langchain-google-genai>=2.0.0
chromadb>=0.5.20
sentence-transformers>=3.0.0   # optional, only if local embeddings
langfuse>=3.0.0       # present in SDK but stack off by default (LANGFUSE_ENABLED=false); flip to true only in optional F8B

# Existing (no changes)
fastapi>=0.115
uvicorn[standard]>=0.40
sqlalchemy[asyncio]>=2.0
weasyprint>=62.3
jinja2>=3.1
google-genai>=1.0   # already present
```

## Appendix B — New environment variables

```
# === LangGraph / Agentic ===
RACE_AGENT_ENABLED=true
RACE_AGENT_PROMPT_VERSION=analyst_v1
RACE_AGENT_CRITIC_ENABLED=true
RACE_AGENT_MAX_RETRIES=2
LANGGRAPH_CHECKPOINT_PATH=./data/langgraph/checkpoints.sqlite

# === Gemini (override existing) ===
AI_PROVIDER=google
AI_MODEL=gemini-2.5-flash-lite
AI_MAX_TOKENS=8192       # ↑ from 1024 for narrative
AI_TEMPERATURE=0.3       # ↓ from 0.4 for reproducibility

# === Langfuse ===
LANGFUSE_ENABLED=false   # default — flip to true only if F8B is activated (optional Langfuse)
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

## Appendix C — Accumulated assumptions (to validate)

- **A1** The coach today invests 45-60 min per round in manual analysis (base for ROI).
- **A2** Gemini Flash Lite free tier handles MVP load (15 RPM, 1500 RPD).
- **A3** 90-day TTL for `anonymization_mappings` is sufficient for auditing.
- **A4** Embeddings via Gemini API is preferable to local (provider consistency).
- **A5** Indefinite archive of insights (no physical deletion) complies with Ley 1581 unless parent requests.
- **A6** SqliteSaver is sufficient for <100 runs/month (does not require Postgres).
- **A7** Coach does not need shell access — all interaction via web UI.
- **A8** ~~Langfuse self-hosted on small VPS~~ — **2026-05-20:** deferred to optional F8B. Primary audit in DB columns. Langfuse activatable only if real cost >$10/month, coach asks for UI, or serious A/B testing.
- **A9** 1 solo dev-teacher, 5h/day → 14 days = ~3 calendar weeks.
- **A10** ~~TanStack Query not needed for SSE~~ — **Decision 2026-05-20:** TanStack Query `refetchInterval` used for polling. No EventSource. Accepted trade-off: ~2s lag vs eliminated SSE complexity.
- **A11** Theoretical framework changes <1 time/month (no periodic automatic reindex needed).
- **A12** Parents do NOT access this module. Their data goes filtered via existing modules.
- **A13** Critic agent activated from MVP (eval decides whether to keep).
- **A14** Notification email is Resend (existing provider), Spond not incorporated.
- **A15** Learning mode uses static messages per node (does not generate dynamically with LLM in MVP).

---

**End of document.** Estimated total pages: ~30 (markdown rendered). Next step: coach approval → `/sc:workflow docs/10-race-results/v2-agentic-design.md`.
