# Competitions Module — Consolidation & Completion (feature brief for /speckit-specify)

> This is the input ("$ARGUMENTS") for `/speckit-specify`. It states WHAT and WHY,
> not HOW. Reference architecture lives in `docs/12-competitions-unification/workflow.md`
> and `docs/10-race-results/`.

## One-line summary

Merge the two overlapping race areas (the `/competitions` CRUD module and the
`/coach/race-analysis` AI analysis module) into a single coherent **Competitions**
module that is the one place a coach goes to plan a race, load and view its results
and the season points standings, fix mistakes, link results to club athletes, manage
a call-up roster, keep the calendar in sync, and read AI insights.

## Problem / motivation

- In the running app there are effectively **two modules** for the same thing
  (competition management vs. results/AI analysis). The coach has to jump between
  them and the mental model is split.
- The unification was designed (approved PRD) and partly wired in the frontend, but
  it is **not actually finished or live**, and several core capabilities were never
  built — most importantly there is **no way to view results**: the Results tab is a
  placeholder hub with no per-event finishing table and no season points standings.

## Goal

A single **Competitions** module (one sidebar entry, one navigation tree) covering the
full lifecycle of a Copa Valle round, for coach and admin. No second module. No dead
ends. Clean, fast, mobile/tablet-friendly UI/UX.

## Users & roles

- **Coach / Admin**: full access to everything below.
- **Parent**: read-only, scoped to their own child only; never sees other athletes'
  data, AI cross-round views, raw standings of other clubs beyond what is public, or
  any minor's name in AI-generated text.

## In scope (capabilities the module must deliver)

1. **Single module / consolidation**
   - One `/competitions` area is the only entry point. The separate AI-analysis module
     is absorbed (no standalone `/coach/race-analysis` experience). Old deep links
     redirect, then are removed, without breaking external links (Spond, emails) during
     the transition.

2. **Create & manage competitions (CRUD)**
   - Create a competition/round before any PDF exists (plan ahead): name, series
     (Copa Valle), round number, date, venue, championship flag, status
     (scheduled / completed / cancelled), and optional race conditions
     (weather, temperature, surface, altitude, notes).
   - Edit metadata at any time. Delete (admin-only, guarded when dependents exist).
   - List with filters (season, status, championship, venue, has-results, upcoming) on
     desktop table + mobile cards.

3. **Load results — event results AND general points**
   - Import official PDFs/CSV through a guided wizard: the per-round **RESULTADOS**
     (finishing order) and the season **GENERAL** (cumulative points standings).
   - Parse → dry-run preview (with athlete matching) → confirm/commit, transactional
     and idempotent.

4. **View results (the missing piece)**
   - **Per-event results table**: full finishing order for the round (position, rider,
     club, category, time/gap), filterable by category, with our club's athletes
     visually highlighted.
   - **General points standings**: season-cumulative points classification, with our
     club's athletes highlighted.
   - Both readable on mobile.

5. **Reload / fix results (re-ingestion)**
   - Re-upload a corrected PDF for the same round; the system detects it is a revision
     (not an error), shows a confirmable **diff** (position / time / gap / category /
     added-removed), and applies it transactionally with an audit trail and a
     closed-catalog reason. SHA256 idempotency preserved.
   - Downstream AI analyses and any already-sent newsletters affected by the correction
     are marked **outdated** (no automatic resend or re-run; coach decides).

6. **Associate competitions with club athletes**
   - **Auto-match** parsed riders to club athletes during import.
   - **Confirm/fix matches**: resolve ambiguous matches and link/unlink competitors to
     athlete records after import.
   - **Manual roster / call-up**: coach explicitly selects which club athletes are
     entered in a competition, independent of imported results (works before results
     exist and reconciles with them afterwards).

7. **Calendar relationship — bidirectional sync**
   - Creating a competition can create/link a calendar event (opt-out checkbox, on by
     default) and a calendar race event can link to a competition. Strict 1:1.
   - Editing date / name / venue on one side keeps the linked side in sync.

8. **AI insights (integrated, not a separate module)**
   - Inside the competition detail: insights for that round.
   - Cross-round views reachable within the module: per athlete (longitudinal),
     per club/group, and a season overview.
   - Coach/admin only; parents are blocked (403). AI never emits minors' names.

9. **UI/UX quality**
   - Coherent competition detail with tabs (info, results, standings, conditions,
     athletes/roster, insights). Clear empty/loading/error states everywhere.
   - Touch targets ≥48px, WCAG 2.1 AA, español neutro (Colombia) product copy,
     usable on a tablet in the field and on intermittent mobile connectivity.

## Out of scope (for this feature)

- Public/family-facing results portal beyond the existing parent read-only view.
- Automatic AI re-runs or automatic newsletter resends (always coach-initiated).
- Federation registration / logistics (handled elsewhere).
- New AI analysis capabilities beyond surfacing what already exists, consolidated.

## Key entities (already in the schema — to be unified, not reinvented)

- **RaceEvent** (round): metadata, status, conditions; 1:1 with a calendar event.
- **RaceSeries** + **RacePointsScheme**: season grouping and points rules.
- **RaceCategory**: the 26 Copa Valle categories.
- **Rider** / **RaceCompetitor**: a person in results; may link to a club **Athlete**.
- **RaceResult**: one rider's result in one event (position, time, gap, points).
- **RaceImport** + **RaceResultRevision**: ingestion audit, idempotency, diffs.
- **(new) Roster / call-up** association: club athletes entered for a competition.
- **AI run** record: analysis anchored to a round/athlete/club/season, with an
  `outdated/stale` marker.
- **Athlete**, **Calendar event**: existing entities this module links to.

## Constraints & non-negotiables

- Privacy (Ley 1581): no minor names, DOB, or medical data in logs, commits, AI prompts
  or AI output. `data-privacy-guard` audit required.
- Incremental & reversible: ship in waves, each independently deployable; redirects live
  one release cycle before old routes are removed; no big-bang.
- Performance budgets (constitution): API p95 ≤500ms cached reads / ≤1500ms writes,
  no N+1 (season/standings queries aggregated in SQL), lazy-loaded heavy views.
- Stack: FastAPI + SQLAlchemy 2 async + Alembic + MySQL 8.4; React 19 + shadcn/ui +
  Tailwind + TanStack Query + Zustand + RHF + Zod. Reuse existing hooks/services.

## Success criteria (measurable)

- A coach can do the full lifecycle for one round — create → import results + general →
  view both tables → fix a result → confirm roster → see it on the calendar — without
  ever leaving the Competitions module.
- There is exactly one sidebar entry and zero duplicate routes/pages for race work.
- Per-event results and general standings are viewable in-app (today: impossible).
- All existing race/competition tests still pass; new capabilities are covered
  (including privacy invariants and a11y).
