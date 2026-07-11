# Contract — Status Vocabulary Sweep

Maps all eight ad hoc status presentations found in the coach app onto the shared `StatusBadge` (`specs/028-frontend-design-foundation/contracts/shared-components.md`):

```ts
type Status = "success" | "warning" | "danger" | "neutral";
interface StatusBadgeProps {
  status: Status;
  label: string;      // always present — color never the only carrier
  icon?: LucideIcon;   // defaulted per status
}
```

Each domain keeps its own thin adapter function (`{domain}Status(state): { status, label, icon? }`) beside its data — `StatusBadge` itself stays domain-ignorant, per 028's contract ("Domain adapters... live beside their domains").

Default icons per status (used unless a domain overrides for a specific state, noted per row): `success → CheckCircle2`, `warning → AlertTriangle`, `danger → XCircle`, `neutral → Circle`/`CircleOff`.

## 1. Strava connection — `components/activities/ConnectionStatusBadge.tsx:30-51`

| State | → Status | Label (es-CO) | Icon override |
|---|---|---|---|
| `none` | `neutral` | "Sin conectar" | `CircleOff` (existing) |
| `active` | `success` | "Conectado" | `CheckCircle2` (existing) |
| `broken` | `warning` | "Conexión rota" | `TriangleAlert` (existing) |
| `disconnected` | `neutral` | "Desconectado" | `Link2Off` (existing) |

**Change**: replace the local `STATUS_CONFIG` map + `<Badge variant={config.variant}>` wrapper with `sessionStrava­Status(state)` → `<StatusBadge status label icon />`. Existing icons are kept (already well-chosen); only the variant-name plumbing changes (`"secondary"` → `"neutral"` where applicable).

## 2. Competition status trio — `components/competitions/CompetitionStatusBadges.tsx:29-113`

Three independent adapters (booleans + one tri-state), one `StatusBadge` each, tooltips unchanged:

| Sub-badge | State | → Status | Label |
|---|---|---|---|
| Resultados | `has_results=false` | `neutral` | "Sin resultados" |
| | `has_results=true` | `success` | "Con resultados" |
| Calendario | `has_calendar_event=false` | `neutral` | "Sin calendario" |
| | `has_calendar_event=true` | `success` | "Calendario" |
| Condiciones | `none` | `neutral` | "Sin condiciones" |
| | `partial` | `warning` | "Condiciones parciales" |
| | `complete` | `success` | "Condiciones OK" |

**Change**: keep the existing `Tooltip` wrapper (unaffected by this sweep) around each `StatusBadge`. Icons (`Trophy`, `Link2`/`Link2Off`) stay as domain overrides passed via the `icon` prop.

## 3. Session status — `components/training/SessionStatusBadge.tsx:7-32`

| State | → Status | Label |
|---|---|---|
| `planned` | `neutral` | "Planificada" |
| `executed` | `success` | "Ejecutada" |
| `cancelled` | `danger` | "Cancelada" |

**Change**: this is the one implementation that **bypasses `Badge` entirely** (hand-rolled `<span>` with manual `className` per state, `:24-32`). Delete `SessionStatusBadge.tsx`'s body; re-export a thin `sessionStatus(state)` adapter and render `<StatusBadge>` at every call site. Highest-value single fix in the sweep (fixes both the color-consistency gap and the primitive-bypass gap in one file).

## 4. AI insight confidence — `lib/insights.ts:114-126` (+ verbatim duplicate `AthleteAIAnalysisTab.tsx:75-87`)

| State | → Status | Label |
|---|---|---|
| `high` | `success` | "Confianza alta" |
| `medium` | `warning` | "Confianza media" |
| `low` | `danger` | "Confianza baja" |

**Change**: delete the duplicate in `AthleteAIAnalysisTab.tsx` (`confidenceBadgeVariant`/`confidenceText`, lines 75-87); both call sites (`AthleteAIAnalysisTab.tsx:279`, and wherever `lib/insights.ts`'s versions are consumed) import the single `confidenceStatus(confidence)` adapter from `lib/insights.ts`, returning `{status, label}` for `StatusBadge` instead of `{variant, label}` for `Badge`. Rule of three already satisfied by the duplicate alone; this sweep is also the vehicle to delete it.

## 5. Newsletter status — `routes/training/AthleteNewslettersDashboardPage.tsx:47-56`

| State | → Status | Label |
|---|---|---|
| `none` | `neutral` | "Sin generar" |
| `draft` | `warning` | "Borrador" |
| `approved` | `success` | "Aprobado" |
| `sent` | `success` | "Enviado" |
| `failed` | `danger` | "Fallido" |

**Change**: this implementation also **bypasses `Badge`** (hand-rolled `badgeClass` strings rendered via a raw `<span>`, call site `:162-167`). Replace `STATUS_CONFIG` + inline span with a `newsletterStatus(status)` adapter + `<StatusBadge>`. Note `approved` and `sent` share `success` — they are differentiated only by label text, not color (both mean "done" from the coach's perspective; only `sent` additionally shows its `sent_at` timestamp, unchanged).

## 6. Consent status (+ embedded AI sub-toggle) — `components/consent/ConsentStatusPanel.tsx:52-76,206-224`

| State | → Status | Label |
|---|---|---|
| `never` | `neutral` | "Sin consentimiento" |
| `outdated` | `warning` | "Desactualizado" |
| `revoked` | `danger` | "Revocado" |
| `current` | `success` | "Vigente" |

Embedded AI-toggle pill (`AiConsentRow`, `:187-250` — a **second**, previously uncounted ad hoc status system in the same file):

| State | → Status | Label |
|---|---|---|
| not authorized | `neutral` | "IA: no autorizada" |
| authorized | `success` | "IA: activa" |

**Change**: both `STATE_CONFIG` (`:52-76`) and the inline `isAiActive ? ... : ...` pill (`:212-219`) become `StatusBadge` renders via two adapters (`consentStatus(state)`, `aiConsentStatus(isActive)`) in the same file — no behavior change to the renew/revoke/toggle actions themselves, which stay exactly as built.

## 7. Analysis freshness — `components/competitions/insights/StaleAnalysisBadge.tsx:43-49`

| State | → Status | Label |
|---|---|---|
| stale | `warning` | "Análisis desactualizado" |

**Change**: replace the hand-colored `<Badge variant="secondary" className="bg-amber-100 text-amber-800">` with `<StatusBadge status="warning" label="Análisis desactualizado" icon={AlertTriangle} />`. The "Re-ejecutar" `Button` beside it (`:50-59`) is unchanged — this is a color-only fix, folded into the broader AI freshness-vocabulary unification (`contracts/ai-identity.md`).

## 8. Run/launch state — `components/competitions/insights/GroupRunRow.tsx:34-149` (`StateChip`)

| State | → Status | Label |
|---|---|---|
| `already_running` | `neutral` | "Ya en curso" |
| `backpressure` | `warning` | "Límite alcanzado" |
| `error` / `no_results` / `budget_exceeded` | `danger` | "Fallido" |
| live `hitl_waiting` | `warning` | "Esperando aprobación" |
| live `done` | `success` | "Completado" |
| live `failed` / `error` | `danger` | "Fallido" |
| live `cancelled` | `neutral` | "Rechazado" |
| live `running` / outcome `started`/`recovered` | *(not a badge)* | *(routes to the compact `AnalysisRunTimeline`, see `contracts/ai-identity.md`)* | |

**Change**: `StateChip` (a full, self-contained 116-line status-badge reimplementation, `:34-149`) is deleted; its non-"in progress" branches become one `groupRunStatus(runState, outcome)` adapter feeding `StatusBadge`. The "in progress" branches (`running`, `started`, `recovered`) instead mount the compact `AnalysisRunTimeline` variant per `contracts/ai-identity.md`, replacing today's spinner-chip with the shared run-view.

## Non-goals

- Race classes A/B/C (`lib/insights.ts` `CARRERA_TIER`) are explicitly **not** part of this sweep — ordinal, not status. See `contracts/chart-style.md` §"A/B/C ordinal scale" / `data-model.md` §2.
- No change to any underlying state machine, API contract, or RBAC — every mapping above is a rendering swap over data these components already receive as props.

## Test obligations (Constitution II)

- One `vitest` test per adapter function (8 adapters + the 2 sub-adapters in `ConsentStatusPanel` = 10) asserting the full state→`{status,label}` table above.
- One `jest-axe` pass per updated component confirming `StatusBadge` renders remain violation-free (icon+label, not color-alone, is itself an accessibility property worth a regression test).
- Snapshot/DOM assertion that `SessionStatusBadge` and `AthleteNewslettersDashboardPage`'s badge no longer render a raw hand-styled `<span>` (regression guard against the primitive-bypass recurring).
