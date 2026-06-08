# Phase 0 Research: Unified Competitions Module

**Feature**: 007-competitions-consolidation
**Date**: 2026-06-08
**Method**: Direct codebase inspection (backend models/services/routers, frontend routes/components), web research (leaderboard/standings UX, TanStack Query cross-invalidation), Context7 (TanStack Table patterns).

## Summary of the "as-built" landscape

The most important finding: **most of the data layer already exists**. This feature is far less "build from scratch" than the spec's framing implies — it is mostly **read endpoints + UI + sync logic + finishing a partially-done consolidation**.

| Capability | Backend state | Gap |
|---|---|---|
| Competition CRUD | `routers/race_events.py` (list/detail/create/patch/delete + conditions) | None material |
| Event results data | `race_results` table fully populated by ingestor (position, time_ms, laps_behind, points, status, athlete_id, category) | **No read endpoint** to return a finishing table |
| Season standings | `season_standings` SQL VIEW exists (migration `64c263edd07f`) + `analytics.club_ranking(season)` | **No read endpoint** exposing the view to the UI |
| Import (parse/dry-run/commit) | `routers/race_imports.py` + `services/race/ingestor.py` (idempotent SHA256, GENERAL + RESULTADOS) | None |
| Revision/diff | `RaceResultRevision` model, soft-delete, `imports/{id}/diff` | None material |
| Athlete↔rider link | `race_competitors.athlete_id` (+ `linked_at`/`linked_by`) + `routers/race_competitors.py` (suggest/link/unlink) + `race_competitor_link_audit` | None material |
| Roster / call-up | — | **Net-new** (no table/endpoint) |
| Calendar link | `race_events.calendar_event_id` ↔ `calendar_events.race_event_id` (both FKs) + CHECK `competition ⇒ race_event_id NOT NULL` | **No propagation logic** on edit; create-checkbox not wired end-to-end |
| AI runs + stale | `agent_runs` table incl. `stale_since` column (already added for PR5) + `routers/{race_analysis,athlete_race_analysis,club_race_insights}.py` | Still a **separate destination**; needs absorbing |

## Decisions

### D1 — Results & standings are read-only projections, not new storage
- **Decision**: Add read endpoints over existing data: `GET /race-events/{id}/results` (finishing order grouped/filterable by category) and `GET /race-events/{id}/standings` or `GET /series/{id}/standings` (from the `season_standings` view). No new result storage.
- **Rationale**: `race_results` and `season_standings` already hold everything needed. "Our club" highlight = rows where `athlete_id IS NOT NULL` (a confirmed link to a club athlete).
- **Alternatives rejected**: Materializing a standings table (redundant; the view is authoritative and recomputes on import).

### D2 — Roster/call-up is one net-new table, independent of calendar
- **Decision**: Add `race_event_roster` (`race_event_id`, `athlete_id`, `status`, `note`, `created_by_user_id`, timestamps; unique `(race_event_id, athlete_id)`). Reconciliation against results is a computed read (roster ∖ results, results ∖ roster).
- **Rationale**: The roster must exist **before** results and **before/without** a calendar event (the calendar link is opt-out). Coupling it to `EventAttendance` on the calendar event would break when the coach opts out of calendar creation, and `EventAttendance` semantics (RSVP for club events) don't match "called up to a competition."
- **Alternatives rejected**: Reuse `EventAttendance` (fragile, wrong lifecycle); JSON column on `race_events` (not queryable for reconciliation/per-athlete history). This is the single justified new dependency in the data model (recorded in plan Complexity Tracking).

### D3 — Calendar sync: race_event is the source of truth
- **Decision**: A service (`services/race/calendar_sync.py` or extend `services/race_events.py`) owns the 1:1 link. On competition create with the default-on checkbox → create a `calendar_events` row (`event_type=competition`, set both FK sides). On metadata edit (date/name/venue/status) → propagate to the linked calendar event. Reverse linking (`?race_event_id=` in EventForm) already exists and is preserved.
- **Rationale**: Both FK columns and the CHECK constraint already exist; only propagation logic is missing. Single-writer (race_event) avoids cycles. Cancellation propagates as `EventStatus.CANCELLED`.
- **Alternatives rejected**: DB triggers (opaque, untestable in `aiosqlite`), two-way writer (race conditions, the model comment explicitly avoids a back_populates cycle).

### D4 — Consolidation via strangler + redirects (per approved PRD)
- **Decision**: Finish the `docs/12-competitions-unification/workflow.md` plan: single "Competencias" sidebar entry; the AI-analysis pages are reached only inside `/competitions/*`; `301` redirects from `/coach/race-analysis` and `/training/races/:id/club-insights` for one release cycle, then `410`. Remove `RaceAnalysisPage`/`ClubInsightsByRacePage` only after redirects are stable.
- **Rationale**: Matches the already-approved decisions D1–D7; minimizes broken external deep links (Spond, emails). The frontend codemod is partly done; the live app still surfaces two destinations, so the remaining work is sidebar + redirect lifecycle + removal.
- **Alternatives rejected**: Big-bang delete (breaks external links; violates constitution incremental/reversible expectation).

### D5 — Results/standings tables: shadcn table primitive + client-side sort/filter, no new dep
- **Decision**: Add a `components/ui/table.tsx` shadcn primitive (local component, not a runtime dependency) and a small client-side sort/filter; default the view to a category selector + "our club only" toggle. Lazy-load the results tab. No `@tanstack/react-table`.
- **Rationale**: A single round's field is bounded (hundreds of rows across 26 categories) and filtered by category, so virtualization/server-side paging is unnecessary; staying off a new dep honors the constitution's stack-discipline rule. Context7 confirms TanStack Table would be the path *if* we needed manual/server-side mode, which we do not here.
- **Alternatives rejected**: `@tanstack/react-table` (new dep, unjustified at this data scale); server-side sort/filter (over-engineering for bounded data, extra round-trips on 3G).

### D6 — Cross-entity cache invalidation is explicit and centralized
- **Decision**: Mutations that touch both competition and calendar (create-with-calendar, metadata edit, cancel, associate) invalidate both `raceEventKeys` and the calendar query keys via a shared invalidation helper in the hook layer. Import/revision mutations invalidate results, standings, competitor, and race-analysis (stale) keys.
- **Rationale**: TanStack Query v5 has no automatic dependency graph; a centralized helper avoids the well-known "forgot to invalidate the other side" bug for paired resources.
- **Alternatives rejected**: Normalized cache (against TanStack philosophy; large refactor); per-call ad-hoc invalidation (error-prone, the existing duplication risk).

### D7 — Privacy posture for results/standings/insights
- **Decision**: Coach/admin see full tables. Parent reads are filtered to their own child's rows only (results where `athlete_id` ∈ their children) and 403 on cross-round/club/season insights. AI narratives keep `forbidden_names` from DB; global/anonymous views use `forbidden_names=[]` to force name-free wording. No minor PII in logs (ids only) or AI prompts.
- **Rationale**: Constitution Ley-1581 invariants + PRD D2. The pieces (anonymizer node, guardrails) already exist; this feature must not regress them.
- **Alternatives rejected**: Showing full standings to parents (leaks other minors); relying on UI hiding only (must be enforced server-side).

## Open questions resolved (no NEEDS CLARIFICATION remain)
- Standings source → `season_standings` view (confirmed in migration).
- Stale marker → `agent_runs.stale_since` (already present).
- Calendar cardinality → strict 1:1 (existing FKs + CHECK).
- Roster home → new `race_event_roster` table (D2).

## References
- [Leaderboard design pattern — ui-patterns.com](https://ui-patterns.com/patterns/leaderboard)
- [F1 Season Leaderboard with live data — domo.com](https://www.domo.com/blog/f1-season-leaderboard-tracking-drivers-and-teams-with-live-data)
- [TanStack Query v5 — Query Invalidation](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation)
- [TanStack Query discussion #1125 — related-entity invalidation](https://github.com/TanStack/query/discussions/1125)
- TanStack Table docs (Context7 `/tanstack/table`) — sorting/filtering/manual-mode (confirmed not needed at this scale).
