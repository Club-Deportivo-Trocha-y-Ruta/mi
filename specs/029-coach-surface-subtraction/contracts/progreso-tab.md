# Contract — Athlete "Progreso" Tab

UI contract for the new consolidated tab on `AthleteDetailPage` (FR-007, FR-008). Presentational composition only — no new data contract (see `data-model.md`). Builds on the 028 shared-component kit (`contracts/shared-components.md`) for loading/error/empty states.

## Tab registration

```ts
// AthleteDetailPage.tsx — extends the existing Tab union (was 6 values, becomes 7)
type Tab =
  | "info"
  | "anthropometry"
  | "growth"
  | "ai_analysis"
  | "newsletters"
  | "activities"
  | "progreso";           // NEW

const VALID_TABS: readonly Tab[] = [
  "info", "anthropometry", "growth", "ai_analysis",
  "newsletters", "activities", "progreso",           // NEW
] as const;
```

- **URL sync**: `?tab=progreso`, via the existing `updateTab`/`parseTabParam` mechanism (`AthleteDetailPage.tsx:404-413,64-69`) — no new mechanism.
- **Visibility**: always rendered (unlike `growth`, which is conditional on `records.length > 0`) — technique/strength progress do not depend on anthropometry records existing.
- **Position**: appended after `activities` in the tab row (`:570-634`) to minimize diff churn; no visual reordering of existing tabs.

## `ProgresoTabPanel` (new, internal — not exported outside `AthleteDetailPage`'s file or a co-located component file)

```ts
interface ProgresoTabPanelProps {
  athleteId: number;   // same value already in scope in AthleteDetailPage
}
```

Renders:

1. A `ToggleGroup`/segmented control with two options: "Técnica" (default) and "Fuerza" — local `useState<"tecnica" | "fuerza">("tecnica")`, **not** URL-synced (matches `AnxietyDashboardPage`'s own internal sub-tabs, which also don't sync to the URL).
2. Below the toggle, one of:
   - `<Suspense fallback={<BoardSkeleton />}><SkillProgressBoard athleteId={athleteId} /></Suspense>` (Técnica)
   - `<Suspense fallback={<BoardSkeleton />}><ProgressNotesBoard athleteId={athleteId} /></Suspense>` (Fuerza)

   Both `SkillProgressBoard` and `ProgressNotesBoard` are reused **unmodified** — same lazy import pattern as their current standalone pages (`lazy(() => import(".../SkillProgressBoard").then(m => ({ default: m.SkillProgressBoard })))`), just relocated into this panel instead of a route-level `PageShell`. Their own internal loading/error/empty states are untouched.
3. A small wellbeing pointer card/link, below or beside the toggle:
   ```tsx
   <Link to={`/anxiety?athlete=${athleteId}`}>Ver ansiedad competitiva</Link>
   ```
   Always rendered (the anxiety module itself handles the "no consent"/"no assessments" states once the coach arrives there — this is just a pointer, not a gate).

## Lazy boundaries

No change to the existing lazy-loading strategy: `SkillProgressBoard` and `ProgressNotesBoard` stay `React.lazy`-loaded exactly as they are today (they are *already* lazy inside their standalone pages, per the audit — "both already `React.lazy`-loaded by their pages, so embedding as tabs costs nothing on the initial bundle"). `AthleteDetailPage` itself is not lazy-split further by this change.

## `AnxietyDashboardPage` receiving end (smallest addition, per FR-008)

```ts
// AnxietyDashboardPage.tsx
const [searchParams] = useSearchParams();              // NEW
const athleteFromUrl = Number(searchParams.get("athlete")) || 0;   // NEW

const [tab, setTab] = useState<Tab>(athleteFromUrl > 0 ? "individual" : "crear");  // was: always "crear"
```

`IndividualTab` gains an optional prop (or reads the same `searchParams` itself) to seed its local `athleteId`/`submittedId` state from `athleteFromUrl` on mount, so the series query fires without the coach re-selecting the athlete from the dropdown. No change to `useAthleteSeries`, `useAthletes`, or any backend contract — this is purely initial-state wiring in an already-client-side-only component.

## Out of scope for this contract

- Reordering or renaming any of the other 6 tabs.
- Any change to `SkillProgressBoard`/`ProgressNotesBoard` internals (forms, mutations, history rendering).
- A dedicated "consent status" indicator on the pointer card — the anxiety module itself is the single source of truth for consent state (`contracts/anxiety-interpretation-ui.md`); duplicating it here would be a second place to keep in sync.
