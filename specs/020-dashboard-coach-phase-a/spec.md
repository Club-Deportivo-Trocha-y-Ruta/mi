# Feature Specification: Coach Dashboard — Phase A (Correctness, Performance & Club-Scope Fixes)

**Feature Branch**: `claude/spec-kit-agent-setup-poepvz` (developed on the designated session branch; spec directory `020-dashboard-coach-phase-a`)

**Created**: 2026-07-01

**Status**: Draft

**Input**: Product Manager discovery report on `/dashboard` + spec-panel multi-expert review. This spec is **Phase A only**: fix what already exists on the coach dashboard (performance, list truncation, club scoping, PHV metric reframe). The 3-band redesign ("Hoy/esta semana", "Pulso del club", aggregated anxiety signal) is explicitly **out of scope** and deferred to Phase B/C specs.

> **Language note**: This spec is a development artifact written in English per the project working-language policy. All coach-facing copy (UI strings) MUST be in español neutro (Colombia).

## Overview

The current coach dashboard (`/dashboard`) shows three stat cards (total athletes, last evaluation, PHV status) plus a "Mediciones pendientes" block. It has three defects that make it slow and unsafe in field use:

1. **N+1 requests** — `useDashboardStats` issues one `GET /api/athletes/{id}` per athlete (≈153 requests) just to compute "last evaluation" and "evaluated count". Under Render Free cold-start (~50s) + 3G this is unusable.
2. **Unbounded list** — `MeasurementAlerts` renders every non-`ok` athlete with no limit (~150 rows), drowning the tablet screen.
3. **No explicit club scope** — the dashboard does not scope the stat cards to the coach's active club; seed/other-club athletes can appear. This is an access-control concern for minors' data, not only UX.

Phase A fixes all three by **reusing the existing `GET /api/alerts` endpoint**, which already (a) filters by the coach's clubs server-side and (b) returns `last_measurement_date`, `measurement_status`, `age_decimal`, `category` and rich per-athlete fields. No new backend endpoint is required.

### In scope (Phase A)

- Eliminate the N+1 in the dashboard load.
- Truncate the actionable-measurements list with a "ver todas" link.
- Scope every dashboard block to the coach's active club, with a test proving cross-club isolation.
- Reframe the "Estado PHV" metric to an actionable, defined formula.
- Surface `training_implications` in the existing rapid-growth block (zero-cost win — data already returned).

### Out of scope (deferred)

- "Hoy/esta semana" band (next session, upcoming competition countdown, RPE alerts) → Phase B.
- "Pulso del club" band (4-week attendance, sessions/month, technique-vs-fitness balance) → Phase C.
- Aggregated competitive-anxiety signal → Phase C, gated behind a dedicated privacy review.
- Any new backend aggregation endpoint or migration.

---

## Assumptions & Constraints

- **A1**: `GET /api/alerts` is the single source of truth for dashboard athlete data in Phase A. It already enforces club scope for coaches (`_coach_club_ids`) and returns per-athlete `last_measurement_date`.
- **A2**: "Total atletas", "Última evaluación" and "Estado PHV" are all derivable from the `/alerts` payload (`athletes[]` + summary counts), so `useDashboardStats` no longer needs `getAthlete` per athlete nor `getAthletes`.
- **A3**: A coach belongs to ≥0 clubs via `club_members`. Multi-club active-club selection semantics follow whatever the app already uses for the coach's active club; if none exists yet, "active club" = the coach's single club, and the multi-club selector is out of scope for Phase A (tracked as Open Question OQ-1).
- **A4**: Admin users may pass `club_id` explicitly; behavior for admin is unchanged from the current `/alerts` contract.
- **C1**: No backend schema, migration, or new endpoint. Frontend-only, plus tests. (If OQ-1 forces a backend change, it is escalated, not silently added.)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dashboard loads fast without N+1 (Priority: P1)

The coach opens `/dashboard` and the stat cards + measurement block populate from a bounded number of requests, never one-per-athlete.

**Why this priority**: This is a real performance/cost bug that makes the dashboard unusable under cold-start + 3G. Highest impact, lowest risk.

**Independent Test**: Sign in as a coach with N athletes, load `/dashboard`, assert the network trace contains **no** `GET /api/athletes/{id}` calls and the three cards render correct values.

**Acceptance Scenarios**:

1. **Given** a coach whose active club has N athletes, **When** `/dashboard` loads, **Then** the frontend issues **at most 1** request to populate the stat cards and the measurement block combined (the shared `GET /api/alerts` call), and **zero** `GET /api/athletes/{id}` requests.
2. **Given** the `/alerts` response, **When** the cards render, **Then** "Total atletas" = count of athletes in the active club, "Última evaluación" = the most recent `last_measurement_date` across those athletes (or "--" if none), and "Estado PHV" follows the FR-004 formula.
3. **Given** `/alerts` is still loading, **When** the page renders, **Then** each card shows its loading placeholder ("…") and no card shows a stale or wrong value.
4. **Given** `/alerts` returns an error, **When** the page renders, **Then** the cards show an explicit error/empty state (not "0" presented as a real value) and the measurement block shows its existing error message.

---

### User Story 2 - Actionable list is truncated (Priority: P1)

The measurement block shows only the most urgent actionable athletes, with a link to the full list.

**Why this priority**: ~150 identical "Sin medición" rows make the tablet screen unusable; truncation is required for the dashboard to function in the field.

**Independent Test**: Load `/dashboard` for a club with 40 actionable athletes; assert at most 8 rows render, ordered by urgency, plus a "Ver todas (40)" link that navigates to the full athletes view.

**Acceptance Scenarios**:

1. **Given** M athletes in status `overdue`/`due_soon`/`never` (actionable), **When** the block renders, **Then** at most **8** rows are shown.
2. **Given** M actionable athletes, **When** the list is ordered, **Then** rows are sorted by urgency: `overdue` first (most days overdue first), then `due_soon` (soonest due first), then `never` (oldest / no measurement), so the coach sees the most urgent at the top.
3. **Given** M > 8, **When** the block renders, **Then** a "Ver todas (M)" link is shown that navigates to the existing athletes list filtered/sorted to the same actionable set.
4. **Given** M ≤ 8, **When** the block renders, **Then** no "Ver todas" link is shown.
5. **Given** M = 0, **When** the block renders, **Then** the actionable list is omitted (existing behavior) and only the summary chips (and rapid-growth block, if any) remain.

---

### User Story 3 - Every block is scoped to the coach's active club (Priority: P1)

No athlete outside the coach's active club appears anywhere on the dashboard, under any condition.

**Why this priority**: This is an access-control requirement for minors' sensitive data (anthropometry/PHV), not a cosmetic filter. It must be verified with an isolation test, not assumed.

**Independent Test**: Create coach C in club X (with athletes) and separate club Y (with different athletes, incl. seed/test rows). Sign in as C, load `/dashboard`; assert only club X athletes appear in cards and lists, and no club Y athlete appears in any block.

**Acceptance Scenarios**:

1. **Given** a coach associated with club X, **When** `/dashboard` loads, **Then** the stat cards, summary chips, rapid-growth block and actionable list all reflect **only** club X athletes.
2. **Given** athletes exist in other clubs (including seed/test data such as `ConsentTest`, `<script>…</script> Test`), **When** the coach loads `/dashboard`, **Then** none of those athletes appear in any block.
3. **Given** a coach who belongs to **0** clubs, **When** `/dashboard` loads, **Then** an explicit empty state is shown ("No tienes atletas asignados a un club" or equivalent español neutro) and no other-club or seed data is rendered.
4. **Given** a coach whose active club has **0** athletes, **When** `/dashboard` loads, **Then** an explicit empty state is shown (distinct from the loading state) and cards show "--"/0 consistently.
5. **Given** an admin user, **When** they load `/dashboard`, **Then** existing admin behavior is preserved (may see all clubs or a selected `club_id` per the current `/alerts` contract) — Phase A does not change admin scope.

---

### User Story 4 - PHV metric reframed to an actionable formula (Priority: P2)

The "Estado PHV" card shows a defined, non-alarmist metric instead of the raw "3 / 153 evaluados".

**Why this priority**: The current metric mixes test data and reals and gives no action. It's a formula change, not just UI, so it needs an explicit definition — but it's lower risk than P1 items.

**Independent Test**: Given a club with A athletes of which V have a measurement within the vigency window, assert the card renders "V de A con medición vigente" (or the agreed copy) and matches the defined formula.

**Acceptance Scenarios**:

1. **Given** the active club has A athletes and V of them have `last_measurement_date` within the vigency window (default: within `measurement_interval_days`, i.e. `measurement_status !== 'overdue' && !== 'never'`), **When** the card renders, **Then** it shows "V de A con medición vigente" (final copy per OQ-2), not "V / total evaluados".
2. **Given** A = 0, **When** the card renders, **Then** it shows "--" (not "0 de 0").
3. **Given** the vigency definition, **When** implemented, **Then** the exact window used is documented in the spec/plan (no undocumented magic threshold in code).

---

### User Story 5 - Rapid-growth block surfaces training implications (Priority: P3)

The existing "Crecimiento acelerado detectado" block shows the `training_implications` text already returned by `/alerts`.

**Why this priority**: Zero-cost win — the data is already in the payload and is exactly the actionable text the coach needs ("ajustar carga"). Aligns with "edad biológica > cronológica". Lowest priority because it's an enhancement, not a fix.

**Independent Test**: Given an athlete with `rapid_growth` and a non-null `training_implications`, assert the block renders that text alongside the existing cm/mes value.

**Acceptance Scenarios**:

1. **Given** an athlete flagged `rapid_growth` with `training_implications != null`, **When** the block renders, **Then** the implications text is shown with the existing name + cm/mes line.
2. **Given** `training_implications == null`, **When** the block renders, **Then** the existing generic guidance is shown (no empty gap).
3. **Given** a `phase_changed` or `approaching_circa` growth alert, **When** present, **Then** it MAY be surfaced in the same block (optional in Phase A; if implemented, it must not expose any new sensitive field beyond what `/alerts` already returns).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST derive "Total atletas", "Última evaluación" and "Estado PHV" from the existing `GET /api/alerts` response and MUST NOT issue any `GET /api/athletes/{id}` request on load.
- **FR-002**: The dashboard MUST issue at most one athlete-data request on load (the shared `/alerts` query), reused across cards and the measurement block via the query cache.
- **FR-003**: The actionable-measurements list MUST render at most 8 rows, sorted by urgency (`overdue` desc by days overdue → `due_soon` asc by days to due → `never`), with a "Ver todas (M)" link when M > 8 and no link when M ≤ 8.
- **FR-004**: The "Estado PHV" card MUST use the formula "V de A con medición vigente", where A = athletes in the active club and V = athletes whose `measurement_status` is neither `overdue` nor `never` (vigency window documented). It MUST show "--" when A = 0.
- **FR-005**: Every dashboard block (cards, summary chips, rapid-growth, actionable list) MUST reflect only the coach's active-club athletes. No other-club or seed/test athlete may appear under any condition.
- **FR-006**: The dashboard MUST show distinct explicit states for: loading, error, coach-with-0-clubs, and active-club-with-0-athletes. None of these may render other-club/seed data or present "0" as if it were a loaded real value.
- **FR-007**: The rapid-growth block MUST display `training_implications` when present, falling back to existing generic guidance when null.
- **FR-008**: Phase A MUST be frontend-only — no backend endpoint, schema, or migration change. Any discovery that a backend change is required MUST be escalated as a blocking Open Question, not implemented inside this spec.

### Non-Functional Requirements

- **NFR-001 (Performance)**: On a warm backend, the dashboard's athlete data MUST load in a single round-trip; request count MUST be independent of athlete count (O(1), not O(N)).
- **NFR-002 (Resilience)**: If the `/alerts` request fails or times out during cold-start, the dashboard MUST degrade to an explicit error/empty state with the existing retry behavior of the query layer, never a partial/misleading numeric state.
- **NFR-003 (Privacy)**: No new athlete field beyond what `/alerts` already returns may be surfaced. Club scoping (FR-005) MUST be covered by an automated cross-club isolation test.
- **NFR-004 (Copy)**: All new/changed strings MUST be in español neutro (Colombia).

---

## Risks & Mitigations

- **R1 — Club-scope treated as UX not security**: Mitigated by FR-005 + NFR-003 mandatory isolation test (coach of club X never sees club Y athletes).
- **R2 — Cold-start partial render**: Mitigated by FR-006 explicit states + NFR-002.
- **R3 — Scope creep from Phase B/C**: Mitigated by the explicit out-of-scope list; any band/anxiety/attendance work is rejected from this spec.
- **R4 — "Última evaluación" semantics drift**: In Phase A it is the most recent `last_measurement_date` across active-club athletes (anthropometry), matching current intent — documented in FR-001/US1-AC2 to avoid ambiguity.

---

## Open Questions — RESOLVED (2026-07-01, from code review)

- **OQ-1 (Active club for multi-club coach)** — **RESOLVED**: `MeResponse.club_ids: number[]` — a coach may belong to multiple clubs, but **no "active club" selector exists** in the app today (`auth.store.ts` has no active-club state). `GET /api/alerts` with **no `club_id`** already scopes server-side to the **union of the coach's own clubs** (`_coach_club_ids`), never other clubs. **Decision**: Phase A calls `/alerts` with no `club_id`; the dashboard reflects the union of the coach's clubs. This is safe (FR-005 holds — never other-club data) and requires **no selector**. A per-club selector is deferred to a later spec. "Active club" in this spec therefore means "the coach's club(s)" (union).
- **OQ-2 (PHV card copy)** — **RESOLVED**: Final copy = **"V de A con medición vigente"**. Vigency window = `measurement_status` is neither `overdue` nor `never` (i.e. within `measurement_interval_days`, matching the existing summary semantics). Card shows "--" when A = 0.
- **OQ-3 ("Ver todas" destination)** — **RESOLVED**: `AthletesListPage` (`/athletes`) has only client-side search + PHV filters (no measurement-status filter, no URL params). **Decision**: "Ver todas (M)" links to the plain **`/athletes`** route for Phase A. Adding a measurement-status filter/URL param to that page is **out of scope** (deferred); Phase A ships the truncation + link only.

---

## Success Criteria

- Dashboard load issues 0 `GET /api/athletes/{id}` requests and O(1) athlete-data requests.
- Actionable list never exceeds 8 rows; "Ver todas" appears iff M > 8.
- Automated test proves a coach of club X sees no club Y / seed athlete anywhere on the dashboard.
- "Estado PHV" card renders the FR-004 formula with a documented vigency window.
- No backend/migration change; no new sensitive field surfaced.
