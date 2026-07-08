# Phase 0 Research — National Championship Support (Series Level)

**Feature**: 023-national-championship-level | **Date**: 2026-07-08

All Technical Context unknowns resolved. Research combined: codebase exploration (structural map of features 014/015/016/022), web search (event facts), and design reasoning (sequential analysis, 4 steps).

## R1 — The real-world event (web research)

**Decision**: Target event is the **Campeonato Nacional MTB 2026 (XCO/XCC/XCR/XCM), Pereira, 14–20 July 2026**, organized by the Federación Colombiana de Ciclismo, with prejuvenil/juvenil categories (the club's age range).

**Rationale**: Confirms urgency (event is days away — system must be ready *before* results exist, matching US1 priority), confirms the organizer is **not** Liga Vallecaucana (validates FR-006), and confirms category structure overlaps the club's existing catalog (prejuvenil/juvenil), supporting the parser-compatibility assumption.

**Sources**:
- [Federación Colombiana de Ciclismo — Calendario Nacional 2026](https://federacioncolombianadeciclismo.com/la-federacion-colombiana-de-ciclismo-presenta-el-calendario-nacional-2026/)
- [Comunicado Calendario Nacional 2026 (PDF)](https://efbt585jris.exactdn.com/wp-content/uploads/2025/12/Comunicado-Calendario-Nacional-2026-161225.pdf)
- [Señal Colombia — calendario ciclismo colombiano 2026](https://www.senalcolombia.tv/deportes/calendario-ciclismo-colombiano-2026)

**Alternatives considered**: none needed — factual grounding only. Dates subject to federation adjustments; the system stores the coach-entered date, so calendar drift is not a risk.

## R2 — Where `level` lives

**Decision**: New NOT NULL enum column `level` on `race_series` — `RaceSeriesLevel` (`departmental` | `national`), DB enum name `raceserieslevel`, `values_callable` pattern, `server_default='departmental'`.

**Rationale**:
- Level is a property of the championship *series*, and championships are single-event (INV-2), so series-level is equivalent to event-level with less surface.
- `server_default` makes the migration purely additive: existing rows (Copa Valle cups + Campeonato Departamental 2026) become `departmental` with zero backfill → FR-003 satisfied structurally.
- Mirrors the exact pattern of `RaceSeriesKind` (spec 014): `Enum(..., values_callable=lambda e: [x.value for x in e])` — stores values, not names (`MaturationStatus` precedent).

**Alternatives considered**:
- *Level on `race_event`*: rejected — duplicates per-event what is invariant per-series; every consumer (labels, notifications) reaches the series anyway.
- *Parse level from series `name`*: rejected — free text, fragile, untestable invariant.
- *Widen `kind` enum to `cup|departmental_championship|national_championship`*: rejected — breaks every `kind == championship` guard (standings, INV-2, report grouping, ingestor derivation), i.e., the exact code the spec says must not change.

## R3 — Label propagation

**Decision**: `build_race_label(kind, sequence_number, location, level=RaceSeriesLevel.departmental)` — keyword param with default. Championship + national → `"Cto. Nal.{ — city}"`; championship + departmental → `"Cto. Dep.{ — city}"`; cup unchanged.

**Rationale**: Pure helper already reused by `GET /races` and the evolution serializer (feature 016); both callers already join `RaceSeries`, so passing `series.level` adds zero queries. Defaulted param keeps all existing call sites and tests compiling/passing until each is updated deliberately.

**Alternatives considered**: separate `build_championship_label(level, city)` helper — rejected, splits the single label contract feature 016 deliberately centralized.

## R4 — Notifications: tier vs label

**Decision**: Keep `RaceTier.CD` as the tier for **all** championships (`_tier_from_event`: `is_championship=True → CD`, unchanged). Branch only the human-facing strings in `race_insight_dispatcher.py` (`_build_valida_label`, `_tier_label_es`) by the event's series level → "Campeonato Nacional" / "Campeonato Departamental".

**Rationale**: Tier drives urgency/priority semantics (tapering class, send policy) — a national championship deserves the same top tier. Introducing a new tier would ripple into `_CALENDAR_TIERS`, templates, and tests for zero user value. The spec only requires correct *naming* (FR-005).

**Collision check**: national event will be `(2026, sequence 1)`; `_CALENDAR_TIERS` keys `(year, valida_num)` could collide with Copa válida I — but `_tier_from_event` resolves `is_championship=True` **before** consulting the calendar dict, so no collision. Verified in code.

**Alternatives considered**: new `RaceTier.CN` — rejected as above.

## R5 — Valle-specific defaults (FR-006)

**Decision**:
1. `POST /race-series` already accepts `organizer` from the client (inline form sends it) — no change needed there beyond persisting `level`.
2. `race_imports._get_or_create_series`: apply `organizer="Liga Vallecaucana de Ciclismo"` default **only when `kind == cup`**; championships persist the provided organizer or NULL.
3. `points_scheme_code` remains server-forced `copa_valle_2026` for every series (spec-014 decision D5 upheld). For championships the scheme is dead weight: standings/panorama exclude by `kind` and never read the scheme. Accepted as documented cosmetic debt — changing it would touch the points infrastructure for no behavioral gain.
4. Ingestor legacy `_upsert_series` (no explicit series_id) stays Copa-Valle-hardcoded; **the supported import flow for the national championship is the competition-linked import** (feature 015 prefill → explicit `series_id`), which bypasses that path entirely.

**Rationale**: Smallest blast radius satisfying FR-006's user-visible requirement (organizer not misattributed) without reopening the points-scheme design.

**Alternatives considered**: make `points_scheme_code` nullable / add a `no_points` scheme — rejected, gratuitous migration + touches ranking infra explicitly declared out of scope.

## R6 — Frontend surface

**Decision**:
- `RaceSeriesLevel = "departmental" | "national"` in `raceSeries.types.ts`; `RaceSeriesCreate.level?` (optional, backend defaults) and `RaceSeriesRead.level` (required).
- Level `<select>` (Departamental | Nacional, default Departamental) appears **only** in the two championship-series creation points: `CreateChampionshipSeriesForm` (CompetitionFormPage) and ImportWizard's new-championship-series branch. Never shown for cups.
- New shared helper `frontend/src/lib/raceSeriesLabels.ts` → `championshipLabel(level)` ("Campeonato Nacional"/"Campeonato Departamental") consumed by InfoTab, FiltersBar option copy, and series pickers — rule-of-three preemption is justified because three consumers exist on day one.
- Existing "Campeonatos (CD)" filter option copy becomes level-neutral ("Campeonatos"); filter *predicate* unchanged (`kind == championship` matches both levels → FR-012).

**Rationale**: Matches constitution III (shadcn select, RHF+Zod, español neutro) and keeps cups' UX untouched.

## R7 — Testing strategy (constitution II)

**Decision**:
- Backend: unit tests for `build_race_label` national/departmental/cup matrix; router tests create-with-level (201), default-level (201, departmental), invalid level (422); import test championship-series-no-Valle-organizer; dispatcher test "Campeonato Nacional" body + departmental regression; standings regression (national results present → standings unchanged, SC-004). aiosqlite `create_all` picks up the new column automatically — no test-side migration work.
- Frontend: form tests for level select visibility (championship only) + submit payload; label helper unit test; InfoTab render matrix; jest-axe on touched page-level components.
- Regression invariant: every pre-023 test must pass without modification except where a label string is deliberately asserted.

**Rationale**: NON-NEGOTIABLE principle II; the departmental-unchanged guarantees (SC-005) are regression tests, not manual QA.

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Event facts (date/organizer/categories) | R1 — Pereira 14–20 Jul 2026, Fedeciclismo, prejuvenil/juvenil present |
| Where level lives | R2 — `race_series.level` enum, server_default departmental |
| Label mechanics | R3 — `build_race_label` gains defaulted `level` param |
| Notification tier vs label | R4 — tier CD unchanged; label branches |
| Valle defaults | R5 — organizer default cups-only; scheme debt documented |
| Frontend shape | R6 — 2 creation points, shared label helper |
| Test plan | R7 — full matrix incl. SC-004/SC-005 regressions |
