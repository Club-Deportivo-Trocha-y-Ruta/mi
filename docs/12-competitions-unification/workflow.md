# `/competitions` + AI Analysis Unification — Workflow

**Date:** 2026-06-01
**Requestor:** Coach
**Status:** PRD approved (decisions closed). Pending PR1 kickoff.
**Brainstorm by:** `product-manager` + `refactoring-expert`

---

## 1. Context

Two separate routes currently coexist that the coach wants to unify:

| Current route | Responsibility | Destination |
|---|---|---|
| `/competitions` | CRUD Copa Valle rounds (Phase 1.7+/1.8) | **Remains as central hub** |
| `/coach/race-analysis` | AI v2 landing (agentic LangGraph + HITL) | Absorbed into `/competitions/insights/...` |
| `/training/races/:raceEventId/club-insights` | Group AI per race | Absorbed into `insights` tab of detail view |

**Coach goal:** everything centralized in `/competitions`. CRUD + AI analysis in all combinations (round, athlete, club, season) + bidirectionality with calendar + diff re-ingestion + AI re-trigger.

---

## 2. Closed Decisions (2026-06-01)

| # | Question | Decision |
|---|---|---|
| D1 | Create `calendar_event` when creating a competition | **ON with visible opt-out** (checkbox checked by default) |
| D2 | RBAC for cross-round AI views | **Coach/admin only**. Parents → 403 |
| D3 | Monthly newsletter already sent when a correction arrives | **Mark `outdated`**, no automatic resend |
| D4 | Global season overview in MVP | **Yes**, part of Wave 2 |
| D5 | AI re-trigger policy after re-ingestion | **Always manual** with coach confirmation (no cron) |
| D6 | Re-ingestion scope MVP | **Full UI** with confirmable `DiffTable` end-to-end |
| D7 | Lifespan 301 redirects (`/coach/race-analysis`, `/training/races/:id/club-insights`) | **1 release cycle** (~PR1 to PR7), then 410 in PR7 |

---

## 3. Final Route Map

```
/competitions                          → list
/competitions/new                      → create round
/competitions/import                   → ingest-first wizard
/competitions/:id                      → detail (tabs info|results|conditions|athletes|insights)
/competitions/:id/edit                 → edit metadata
/competitions/:id/import               → re-ingestion with confirmable diff
/competitions/:id/insights/:runId      → detail of an AI run anchored to round
/competitions/insights                 → analysis hub (cross-round overview)
/competitions/insights/athletes/:id    → longitudinal per athlete
/competitions/insights/club            → group/club (absorbs ClubInsightsByRacePage)
/competitions/insights/season/:year    → season overview
```

**301 Redirects (active during PR1-PR7):**
- `/coach/race-analysis` → `/competitions/insights`
- `/training/races/:raceEventId/club-insights` → `/competitions/:raceEventId?tab=insights`

**PR7:** redirects change to 410.

---

## 4. Data Models

**A single addition:** `stale_since DATETIME NULL` column in the AI runs table (exact name to confirm with `database-architect`).

- Populated when a re-ingestion over the same `race_event_id` detects a different SHA256.
- Allows seeing "outdated analysis" without losing the history.
- Nullable, no default → non-blocking migration.

**No new table required.** `RaceResultRevision` already exists from Phase 1.7.

---

## 5. Roadmap in 7 Incremental PRs

### Wave 1 — Route Consolidation

**PR1 — Route codemod + redirects + unified sidebar**
- Lead: `react-ui-engineer`. Support: `qa-engineer`.
- Files: `App.tsx`, `AppShell.tsx`, adjust `MemoryRouter` in existing tests.
- DONE: 301 redirects work, unified "Competencias" sidebar, CI green.
- Risk: low.

### Wave 2 — Centralized AI

**PR2 — `insights` tab in `CompetitionDetailPage` (feature flag)**
- Lead: `react-ui-engineer`. Support: `qa-engineer`.
- Strangler strategy: mounts `RaceAnalysisPage` inside the tab via `VITE_INSIGHTS_IN_COMPETITION=true`. Old route stays active, zero duplication.
- Measure bundle delta < 20 KB over existing lazy chunk.

**PR3 — Cross-round AI views**
- Lead: `react-ui-engineer`. Support: `data-privacy-guard` (mandatory privacy audit), `fastapi-architect` (global endpoint).
- 4 sub-pages under `/competitions/insights/{,athletes/:id,club,season/:year}`.
- Move `components/ai/` + `components/athletes/ai/` to `components/competitions/insights/`. Hooks are NOT moved.
- **New endpoint:** `GET /api/race-analysis/insights/season/{year}` — must use aggregated query with JOIN (no N+1 in Python). Design with `fastapi-architect` before implementing UI.
- **Wave 2 Privacy:** global view uses `forbidden_names=[]` → forces anonymous wording without minors' names. RBAC: parents → 403 on all `/insights/*` routes.

### Wave 3 — Bidirectional Calendar

**PR6 — Checkbox + synchronization**
- Lead: `react-ui-engineer`. Support: `integration-engineer`.
- `CompetitionFormPage`: checkbox "Create event in calendar" (D1 = ON by default).
- Source-of-truth: `race_event` leads. Date/name/venue change propagates to linked calendar event.
- Reverse (`?race_event_id=` in `EventForm`) already exists.
- Strict 1:1 link (1 round ↔ max 1 `race` type calendar event).

### Wave 4 — Re-ingestion + AI Re-trigger

**PR4 — Re-ingestion with confirmable diff**
- Lead: `fastapi-architect`. Support: `react-ui-engineer`.
- Backend: `GET /api/race-analysis/imports/{race_event_id}/diff` (read-only, calculates delta vs last version).
- Frontend: `/competitions/:id/import` reuses existing `DiffTable`, grouping changes by: **Position** | **Time** | **Gap GC** | **Reclassified Category** | **New/Removed**.
- Closed catalogue for `revision_reason` (no free text — privacy already implemented).
- SHA256 idempotency intact.

**PR5 — AI re-trigger + `stale` flag**
- Lead: `fastapi-architect` + `database-architect`. Support: `data-privacy-guard`.
- Alembic migration: `stale_since DATETIME NULL` column in AI runs.
- Endpoint: `POST /api/race-analysis/runs/{run_id}/invalidate` (auto from ingestor on re-ingestion) + `POST /api/race-analysis/runs/{run_id}/re-execute` (manual coach — D5).
- UI: "Outdated analysis" badge + "Re-execute" button on each stale run.
- **D5 honored:** all re-triggers are manual with confirmation. NO cron, NO auto on diff confirmation.
- **Newsletters:** when stale is detected, mark affected `AthleteMonthlyNewsletter` as `outdated` (D3). DO NOT resend.

### Wave 5 — Cleanup

**PR7 — Final deprecation**
- Lead: `react-ui-engineer`. Support: `qa-engineer`.
- Remove `RaceAnalysisPage.tsx`, `ClubInsightsByRacePage.tsx`, transitional barrel re-exports.
- 301 redirects → 410 (D7).
- Bundle baseline must be ≤ PR2.

---

## 6. Critical Risks

| Risk | Mitigation | Owner |
|---|---|---|
| Broken external deep links (Spond, emails) | 301 redirects for 1 full cycle (D7). Hit telemetry. | `release-manager` |
| Bundle size in new insight views | Lazy chunks per sub-page. Measure delta in PR2 baseline. | `react-ui-engineer` |
| Endpoint `/insights/season/:year` with N+1 | Aggregated SQL query with JOIN or window functions. Benchmark before UI. | `fastapi-architect` + `sql-pro` |
| Privacy R2 in global season view | `forbidden_names=[]` forces anonymous wording. Mandatory audit PR3 + PR5. | `data-privacy-guard` |
| 1682 vitest + 305 race tests | Mechanical `MemoryRouter` paths codemod. Do not rewrite assertions. | `qa-engineer` |
| AI cost from bulk re-trigger | D5 = manual with confirmation. No auto-trigger. | (covered by decision) |
| `stale_since` migration in prod | Nullable, no default. Does not block existing queries. | `database-architect` + `release-manager` |

---

## 7. Explicit Anti-patterns

- ❌ DO NOT duplicate AI hooks in the new location. Imports from `hooks/ai/` and `hooks/race/` remain.
- ❌ DO NOT mix component codemod and new logic in the same PR.
- ❌ DO NOT remove old routes before having stable 301s for at least one deploy cycle.
- ❌ DO NOT design the global season endpoint as a loop in the application layer.
- ❌ DO NOT consolidate PR4 + PR5 into one (different rollback contracts).
- ❌ DO NOT do the migration in a big-bang. Each wave must be shippable and reversible.

---

## 8. Delegation Matrix

| PR | Lead | Support |
|----|------|---------|
| PR1 | `react-ui-engineer` | `qa-engineer` |
| PR2 | `react-ui-engineer` | `qa-engineer` |
| PR3 | `react-ui-engineer` | `data-privacy-guard`, `fastapi-architect`, `sql-pro` |
| PR4 | `fastapi-architect` | `react-ui-engineer`, `qa-engineer` |
| PR5 | `fastapi-architect` + `database-architect` | `data-privacy-guard` |
| PR6 | `react-ui-engineer` | `integration-engineer` |
| PR7 | `react-ui-engineer` | `qa-engineer`, `release-manager` |

**Global orchestrator:** `engineering-lead` takes this workflow and breaks it down PR by PR, delegating to specialists. `head-coach-lead` is consulted only if an unanticipated sports decision arises.

---

## 9. Next Steps

1. ✅ PRD approved (this document).
2. ⏳ Coach approves PR1 kickoff.
3. ⏳ `engineering-lead` takes PRD and issues detailed plan for PR1.
4. ⏳ `react-ui-engineer` executes PR1 (route codemod + redirects + sidebar).
5. ⏳ After PR1 merged and deployed, `engineering-lead` starts PR2.

**No implementation advances until explicit coach confirmation.**
