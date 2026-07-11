# Data Model — 033 Visual Coherence & Polish

Presentation-only feature. **No new persisted entities, no schema changes, no migration.** This document defines: (1) the final status-vocabulary domain mapping table (extending `specs/028-frontend-design-foundation/data-model.md`'s illustrative version with the real, code-grounded states from `research.md` R1), (2) the A/B/C ordinal scale, (3) the chart color-role table, (4) the dark-theme token map, and (5) the one new read-model (`AIStatus`) backing R6's proactive budget/wait hint.

## 1. Status vocabulary — final domain mapping

Vocabulary (unchanged from 028): `success | warning | danger | neutral`, always rendered by `StatusBadge` with an icon **and** a label — color is never the only carrier (Constitution III).

| Domain | Source state | → Status | es-CO label | Notes |
|---|---|---|---|---|
| Strava sync | `none` | `neutral` | "Sin conectar" | |
| | `active` | `success` | "Conectado" | |
| | `broken` | `warning` | "Conexión rota" | recoverable, not destructive |
| | `disconnected` | `neutral` | "Desconectado" | intentional, valid state |
| Competition — resultados | `has_results=false` | `neutral` | "Sin resultados" | absence, not an error |
| | `has_results=true` | `success` | "Con resultados" | |
| Competition — calendario | `has_calendar_event=false` | `neutral` | "Sin calendario" | |
| | `has_calendar_event=true` | `success` | "Calendario" | |
| Competition — condiciones | `none` | `neutral` | "Sin condiciones" | |
| | `partial` | `warning` | "Condiciones parciales" | |
| | `complete` | `success` | "Condiciones OK" | |
| Session | `planned` | `neutral` | "Planificada" | |
| | `executed` | `success` | "Ejecutada" | |
| | `cancelled` | `danger` | "Cancelada" | |
| AI insight confidence | `high` | `success` | "Confianza alta" | |
| | `medium` | `warning` | "Confianza media" | |
| | `low` | `danger` | "Confianza baja" | |
| Newsletter | `none` | `neutral` | "Sin generar" | |
| | `draft` | `warning` | "Borrador" | |
| | `approved` | `success` | "Aprobado" | same color as `sent` — both "done" |
| | `sent` | `success` | "Enviado" | |
| | `failed` | `danger` | "Fallido" | |
| Consent | `never` | `neutral` | "Sin consentimiento" | |
| | `outdated` | `warning` | "Desactualizado" | |
| | `revoked` | `danger` | "Revocado" | |
| | `current` | `success` | "Vigente" | |
| Consent — AI sub-toggle | not authorized | `neutral` | "IA: no autorizada" | not an error, informational |
| | authorized | `success` | "IA: activa" | |
| Analysis freshness (AI identity, R5) | none (never run) | — | *(no badge — launch control shown instead)* | |
| | fresh | `success` | *(no badge shown — freshness only surfaces when stale)* | |
| | stale | `warning` | "Análisis desactualizado" | manual re-run only, never automatic |
| Group-run outcome (`GroupRunRow`) | `already_running` | `neutral` | "Ya en curso" | |
| | `started` / `recovered` / live `running` | *(not a status badge — routes to the compact `AnalysisRunTimeline`, R5)* | | |
| | `backpressure` | `warning` | "Límite alcanzado" | transient, actionable via "Reintentar pendientes" |
| | `error` / `no_results` / `budget_exceeded` | `danger` | "Fallido" | |
| Run state (live) | `hitl_waiting` | `warning` | "Esperando aprobación" | |
| | `done` | `success` | "Completado" | |
| | `failed` / `error` | `danger` | "Fallido" | |
| | `cancelled` | `neutral` | "Rechazado" | |

**Explicitly out of this table**: race classes A/B/C (§2 — ordinal, never status). Full before/after per file, with exact StatusBadge call sites, is in `contracts/status-vocabulary-sweep.md`.

## 2. A/B/C ordinal scale (final)

One hue (the app's own accent teal), monotone lightness, validated with `validate_palette.js --ordinal` (see `research.md` R2 for the full report):

| Tier | Meaning | Light hex | Dark hex (optional story) |
|---|---|---|---|
| C | No tapering (diagnostic race) | `#5bc6d5` | `#6dd6e6` |
| B | Mini-taper (3–4 days) | `#1cb5c7` | `#2fbfd1` |
| A | Full taper (5–7 days) | `#008492` | `#0d97a7` |

- `CD` (Campeonato Departamental) is **not** a 4th tier — it colors as **A** (its real tapering intensity per the Copa Valle calendar) and keeps its existing, separate trophy badge (`CompetitionDetailPage.tsx:452-460`) for the championship distinction. One value, two independent visual facts (intensity color + championship badge), never merged into one 4-color scale.
- Always rendered with the visible `A`/`B`/`C` letter as text — never a bare colored dot (Constitution III, FR-002).

## 3. Chart color-role table (final)

| Role | Token | Hex | Used by |
|---|---|---|---|
| Own series (self) | `--color-primary` | `#20b7c9` | Distribution curve/self-reference-line; Evolution line + dot |
| Best reference | `--color-success` | `#0ca30c` | Distribution best-rider reference line |
| Worst reference | `--color-danger` | `#d03b3b` | Distribution worst-rider reference line |
| Other riders (neutral) | `--color-mid-gray` | `#717171` | Distribution non-extreme rider reference lines |
| Championship point | `--color-primary` (same as self) + diamond shape + 2px surface ring | `#20b7c9` | Evolution championship data point only |
| Grid / axis lines | `--color-border-gray` | `rgba(34,42,53,0.08)` | Both charts, **solid**, hairline |
| Axis tick/label ink | `--color-mid-gray` | `#717171` | Both charts (was the one-off `#5a6172`) |

CVD/contrast validation (categorical-style, `pairs:"all"` — any two reference lines may be adjacent on one curve): lightness band PASS, chroma floor PASS, worst all-pairs ΔE 12.4 (danger↔success, deutan) PASS, own-series contrast 2.42:1 vs white → WARN/relief (mandates the table-view twin, not dismissable). Full detail in `contracts/chart-style.md`.

## 4. Dark-theme token map (optional story)

| Role | Light | Dark |
|---|---|---|
| Page plane | implicit white | `#0d0d0d` |
| Card/chart surface | `#ffffff` | `#1a1a1a` |
| Primary text (`--color-charcoal`) | `#2f2f2f` | `#f2f2f0` |
| Secondary text (`--color-mid-gray`) | `#717171` | `#a3a3a3` |
| Disclaimer text (`--color-text-disclaimer`) | `#5a5a5a` | `#b8b8b8` |
| Subtle panel fill (`--color-light-gray`) | `#f5f5f5` | `#242424` |
| Border (`--color-border-gray`) | `rgba(34,42,53,0.08)` | `rgba(255,255,255,0.10)` |
| Card shadow | `--shadow-card` | 1px `rgba(255,255,255,0.08)` ring (shadows don't read on dark) |
| Accent / status tokens | `#20b7c9` / `#0ca30c` / `#fab219` / `#d03b3b` | **unchanged** (all clear contrast on `#1a1a1a` as-is) |

Activation state (not persisted server-side — pure client preference):

```ts
type ThemePreference = "system" | "light" | "dark";
// localStorage key: "tyr:theme-preference:v1"
// Resolution: preference === "system" → follow prefers-color-scheme (no data-theme attribute set);
//             preference === "light"|"dark" → set <html data-theme="...">
```

## 5. AI-status read-model (backend, new — R6)

Backs the pre-launch budget/wait hint (FR-006). Read-only, no persistence beyond what already exists (`athlete_ai_insights.metrics_snapshot_json`, already-running in-memory semaphore).

```ts
interface AIStatus {
  budget_status: "ok" | "warning" | "exhausted";
  budget_remaining_pct: number;       // 0-100, rounded; derived from the same rolling-30d sum check_budget() uses
  concurrency_available: boolean;     // has_capacity() — in-memory, free
  est_wait_seconds: number;           // recent p50 total run duration, seconds, rounded; "typical", not a queue estimate
}
```

State derivation (server-side, mirrors the existing hard-block thresholds so the hint never drifts from actual enforcement):
- `budget_remaining_pct = round(max(0, 1 - current_usd_30d / race_ai_budget_usd_30d) * 100)`
- `budget_status = "exhausted"` when `budget_remaining_pct <= 0` (identical condition to `check_budget`'s `current >= max_cost_usd_30d`); `"warning"` when `< 20`; else `"ok"`.
- `concurrency_available = has_capacity()` (`app/services/race/ai/runner.py:75-78`, unchanged, no new logic).
- `est_wait_seconds` = the same `latency_ms_p50` computation `/admin/ai-usage` performs (`race_analysis.py`), scoped to a shorter recent window, converted `ms → s`, rounded.

Full endpoint contract (request/response/errors/RBAC/non-functional, styled after `specs/028-frontend-design-foundation/contracts/newsletter-status-summary.md`) is in `contracts/ai-identity.md`.

## State transitions

None introduced. Every table above reads existing state machines (session status, consent status, run state, newsletter status, sync status) that already transition through their own existing flows; this feature only changes how each state is *presented*, never how or when a state is *reached*.
