# Contract — AI Identity (naming, icon, freshness, run-view, pre-launch hint)

Applies to every AI entry point in the coach app: session assistant, per-competition insights, per-athlete analysis, race chat, group launch, admin AI health. Covers FR-005, FR-006, FR-007.

## 1. Naming & icon standard

| Element | Value | Applies to |
|---|---|---|
| Noun (what the capability is called) | **"Insights IA"** | Page/tab titles, nav labels, section headers |
| Verb (what launches an analysis) | **"Analizar con IA"** | Every launch button/control, at every entry point |
| Icon | **`Sparkles`** (lucide) | Every AI-related icon in the app — the only icon used |

### Rename table (current → target)

| File | Current text/icon | New text/icon |
|---|---|---|
| `routes/training/SessionAssistantPage.tsx:88-92` | h1 "Asistente IA" | "Insights IA" *(keep "Asistente de sesión" or similar as a subtitle if a session-specific label reads better — noun stays "Insights IA")* |
| `routes/competitions/CompetitionDetailPage.tsx:110` | tab label "Insights IA" | unchanged — already correct, this is the target |
| `components/competitions/insights/GroupAnalysisPanel.tsx:127-137` | h3 "Análisis con IA", icon `Sparkles` | h3 unchanged text becomes button verb "Analizar con IA" (already is, `:191`) — icon already `Sparkles`, no change |
| `components/athletes/ai/AthleteAIAnalysisTab.tsx:230-231` | h2 "Análisis IA del deportista" / "Análisis del coach" (mode-dependent), icon `Sparkles` | h2 → "Insights IA" both modes; the mode-specific *description* text below (`:233-236`) keeps doing the privacy-relevant framing work, unchanged |
| `components/athletes/ai/AthleteAIAnalysisTab.tsx:340-343` | sub-tab "Lanzar", icon `Play` | sub-tab "Analizar con IA", icon `Sparkles` |
| `components/competitions/insights/AnalyzeAthleteButton.tsx:23,90` | icon `BrainCircuit`, label default `"Analizar"` | icon `Sparkles`; default label `"Analizar con IA"` (callers passing a custom `label` prop update to match, e.g. `AnalyzeAthleteButton.tsx:202`'s confirm-modal title "Re-ejecutar análisis" → "Re-ejecutar análisis con IA") |
| `components/competitions/chat/CompetitionChatPanel.tsx:23,235` | icon `MessageSquare`, header "Preguntar a la IA" | icon stays `MessageSquare` for the chat entry point specifically **only if** chat is treated as a distinct modality from "analysis" — decision: **keep `MessageSquare`** for chat (it is conversational, not a launch-and-wait analysis; forcing `Sparkles` here would blur "ask a question" vs "run an analysis"), header text unchanged ("Preguntar a la IA" is a verb phrase specific to chat, not a naming collision with "Analizar con IA") |

**Chat is the one deliberate exception to "one icon everywhere."** Rationale: `color-formula.md`'s and this feature's own naming goal is "no needless variation," not "no functional distinction" — chat is genuinely a different interaction shape (conversational Q&A vs. a launched, tracked, multi-minute pipeline run) and keeping a distinct icon (while still using the *shared* freshness/run-view machinery wherever chat itself shows progress, i.e. the "Pensando…" state) avoids implying chat has a "run" the coach could check freshness on, which it doesn't.

## 2. Freshness vocabulary (single source of truth)

Promote `AnalyzeAthleteButton`'s existing 3-state model (already correct, `AnalyzeAthleteButton.tsx:66-70` region) as the **only** freshness presentation anywhere in the app:

```ts
type InsightFreshness =
  | undefined  // no insight yet → launch directly, no badge
  | null       // fresh insight exists → show no freshness badge, confirm before re-run
  | string;    // stale_run_id → StatusBadge status="warning" label="Análisis desactualizado", launch directly (re-run, not "first run")
```

- `StaleAnalysisBadge.tsx` stops hand-coloring its own amber badge (`:43-49`) and renders `<StatusBadge status="warning" label="Análisis desactualizado" icon={AlertTriangle} />` instead — same "Re-ejecutar" `Button` beside it, unchanged (manual-only re-run, D5 honored, per its own docstring `:7-9`).
- Any future club-wide "N insights stale" rollup (not built in this feature) must reuse this exact 3-state model rather than inventing a 4th.

## 3. Run-progress view

- **Full variant**: `AnalysisRunTimeline` (`components/ai/AnalysisRunTimeline.tsx`) unchanged — stays mounted exactly where it is today (`AthleteAIAnalysisTab.tsx:296-298`), 13-node list, `aria-live="polite"`.
- **Compact variant (new)**: same component, `variant="compact"` — renders only the header block (`:310-357`: state label + progress bar + ETA), no per-node `<ol>`. Replaces `GroupRunRow`'s bespoke `StateChip` (`GroupRunRow.tsx:34-149`) for the "in progress" branches (`running`, launch outcome `started`/`recovered`) — `StateChip`'s terminal-state branches (`done`/`failed`/`hitl_waiting`/`cancelled`/`backpressure`/etc.) become `StatusBadge` renders per `contracts/status-vocabulary-sweep.md` §8, not part of the timeline.
- One run-view implementation, two densities — not two implementations.

## 4. Proactive AI budget/wait

### Frontend behavior

- Every launch control (`AnalyzeAthleteButton`, `GroupAnalysisPanel`'s launch button, the session assistant's entry point) reads `GET /api/ai/status` (below) before the coach clicks:
  - `budget_status="ok"` → no visible hint beyond the normal button.
  - `budget_status="warning"` → a small inline hint near the button, e.g. "Presupuesto de IA: 15% restante" (amber, `StatusBadge status="warning"`), launch still enabled.
  - `budget_status="exhausted"` → launch button **disabled**, plain-language explanation shown inline (not just on click): "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo." (reuses the exact existing 503 copy, `AnalyzeAthleteButton.tsx:35`, now shown *before* the click too).
  - `concurrency_available=false` → launch stays **enabled** (concurrency is transient, not a hard block) but shows "Alta demanda — espera ≈Ns" using `est_wait_seconds`.
  - Always: an "≈Ns" duration hint near the button when both budget and concurrency are fine, using `est_wait_seconds` (mirrors the existing in-flight ETA copy convention, `AnalysisRunTimeline.tsx:333-336`, so the pre-launch and in-flight hints read consistently).
- **Execution-time re-validation is unchanged**: launching still hits the real endpoint, which still re-checks `check_budget()`/`submit_run()` and can still return 503/429 (FR-006, edge case "budget state shown pre-launch may be stale"). The status hint is advisory, never a client-side gate by itself.

### Backend endpoint (new, read-only)

**Endpoint**: `GET /api/ai/status`

**Purpose**: Give the coach a pre-launch budget/wait signal instead of only a post-click 503/429 (FR-006, SC-004). Reuses existing computations verbatim — no new tables, no new business logic beyond percentage/threshold framing already implied by the existing hard-block.

#### Request

No parameters. Auth: Bearer JWT. Roles: `coach`, `admin` — reuses the exact `_coach_or_admin = require_role([UserRole.coach, UserRole.admin])` dependency already defined at `backend/app/routers/race_analysis.py:115`.

#### Response `200 application/json`

```json
{
  "budget_status": "ok",
  "budget_remaining_pct": 62,
  "concurrency_available": true,
  "est_wait_seconds": 24
}
```

- `budget_status` ∈ `ok | warning | exhausted` — `exhausted` iff `budget_remaining_pct <= 0` (identical condition to `BudgetExceededError`'s trigger in `check_budget()`, `budget_guard.py:232`); `warning` iff `< 20`; else `ok`. Computed server-side so the presentation threshold can never drift from the actual enforcement threshold.
- `budget_remaining_pct` — `round(max(0, 1 - current_usd_30d / race_ai_budget_usd_30d) * 100)`, reusing `_sum_cost_last_30d()` (`budget_guard.py:117-139`) and `settings.race_ai_budget_usd_30d` (`config.py:126`) exactly as `check_budget()` does. **No raw dollar amounts in the response** — the admin-only `/admin/ai-usage` (`race_analysis.py:1268-1280`) remains the place for dollar figures; this endpoint is the coach-safe subset.
- `concurrency_available` — direct read of `has_capacity()` (`app/services/race/ai/runner.py:75-78`), in-memory, no query.
- `est_wait_seconds` — same `latency_ms_p50` computation `/admin/ai-usage` performs over `athlete_ai_insights.metrics_snapshot_json`, scoped to a short recent window (e.g. last 7 days or last N runs), `ms → s`, rounded. A typical-duration estimate, not a queueing promise — frontend copy hedges with "≈".

#### Errors

| Code | Condition | Body |
|---|---|---|
| 401 | missing/invalid token | standard error envelope |
| 403 | role not coach/admin (parents excluded, same defense-in-depth pattern as `app/routers/ai.py`'s `_forbid_parents`) | standard error envelope |

No 422 — no request parameters to validate.

#### Non-functional

- p95 ≤ 500ms: one indexed aggregate query (already proven fast enough to run on every launch attempt today, since `check_budget()` runs it synchronously before every run) plus one in-memory read. Comfortably inside Constitution IV's budget.
- Logged with correlation ID; no request/response bodies logged (nothing PII-bearing in this payload regardless).
- Test obligations (Constitution II): happy path (ok/warning/exhausted, each derived from a seeded cost sum); RBAC-negative (parent → 403); a property test asserting `budget_status="exhausted"` if-and-only-if a subsequent real launch would 503 (keeps the hint and the hard block from silently drifting apart).

#### Frontend consumer

`useAIStatus()` (TanStack Query; key `["ai-status"]`; short `staleTime` — e.g. 30s — since budget/concurrency change as other coaches launch runs), consumed by `AnalyzeAthleteButton`, `GroupAnalysisPanel`, and the session-assistant entry point. Failure to fetch (network error) degrades to today's behavior (no pre-launch hint shown, reactive 503/429 copy only) — never blocks the launch button itself.

## 5. Chat non-persistence caption

`CompetitionChatPanel.tsx` already generates a fresh, in-memory-only `session_id` per mount and never persists history (`:4-6,143` — server-side TTL 1 hour, frontend never writes to storage) but says nothing to the coach. Add one line, in the panel header area (near "Preguntar a la IA", `:230-236`) or immediately above the message list on first open:

> "Esta conversación no se guarda — se pierde al cerrar o recargar la página."

Pure copy addition; no mechanism change (chat non-persistence is a deliberate minors-privacy default, per the spec's Assumptions — this feature labels the existing behavior, does not add persistence).

## Test obligations (Constitution II)

- Rename table above: one `vitest` assertion per file that the new label/icon renders (regression guard against the rename being partial).
- `useAIStatus` hook: happy-path + error-degrades-gracefully tests.
- `jest-axe` on every updated launch control (icon+label pairing is itself an a11y property).
- Property test (existing guardrail family, per Constitution/Quality-Gates): AI-status payload never contains athlete names/PII — trivially true here since the payload has no per-athlete fields, but the test documents the invariant explicitly rather than relying on "it happens to have no such fields."
