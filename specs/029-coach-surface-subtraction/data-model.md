# Data Model — 029 Coach Surface Subtraction

## No new domain data

Confirms spec.md's Key Entities statement. This feature touches **zero** tables, columns, enums, or migrations. Every change is presentation-layer:

- **Removals** (composer, session builder, interval-template screen, insights hub trio, upload widget) delete React components/routes only. The backend endpoints and rows they read/wrote (`technique_exercises`, `training_sessions`, `athlete_ai_insight`, interval templates, etc.) are untouched and continue to be read/written through their surviving entry points.
- **Relocation** (`SeasonInsightsPage`) is a file move + two internal link fixes (`research.md` R2); the endpoint it calls (`GET /api/race-analysis/insights/season/{year}` via `useSeasonPanorama`) is unchanged.
- **Consolidation** (Progreso tab) mounts two already-built, already-lazy components inside an existing page; no new query, mutation, or schema.
- **Wiring** (anxiety interpretation) calls an endpoint that has existed and been tested since spec 017 (`POST /api/anxiety/assessments/{id}/interpret`); no request/response shape changes.

## Consolidated `validaLabel`

Single surviving implementation (`frontend/src/lib/insights.ts`, absorbing the private copy in `AthleteAIAnalysisTab.tsx`):

```ts
/** "Válida N" / "Cto. Departamental" / "Resumen de temporada" sentence label.
 *  Legacy exception: branches on the raw sequence number because the AI-insights
 *  payload (race/ai pipeline) does not yet expose `series_kind` — see research.md R6.
 *  Do not add a third copy; import this one. */
export function validaLabel(num: number | null | undefined): string {
  if (num === null || num === undefined) return "—";
  if (num === 0) return "Resumen de temporada";
  if (num === 99) return "Cto. Departamental";
  return `Válida ${num}`;
}
```

No signature change (still `number | null | undefined → string`) — only the call site in `AthleteAIAnalysisTab.tsx` changes (import instead of local re-declaration), so every existing caller is unaffected. `getValidaLabel` (roman numerals, `lib/raceCalendar.ts`) and the two non-label helpers (`romanForValida`, `resolveShape`) are intentionally out of this consolidation (research.md R6) and keep their current signatures.

## Progreso tab view-model

The new `"progreso"` tab on `AthleteDetailPage` is a pure composition of two existing, independently-fetched boards — no combined/joined data model:

| Slot | Component (unchanged) | Data hook (unchanged) | Keyed by |
|---|---|---|---|
| Técnica (default) | `components/technique/SkillProgressBoard.tsx` | `useAthleteSkillProgress(athleteId, enabled)` → `GET /api/technique/athletes/{id}/progress` | `athleteId` (route param, already in scope) |
| Fuerza | `components/strength/ProgressNotesBoard.tsx` | `useAthleteStrengthProgress(athleteId, enabled)` → `GET /api/strength/athletes/{id}/progress` | `athleteId` (same) |
| Wellbeing pointer | new inline link (no component extracted) | none — navigates to `/anxiety?athlete={athleteId}` | `athleteId` (same) |

Local UI state only: which of Técnica/Fuerza is active (`useState<"tecnica" | "fuerza">`), not persisted to the URL (the tab itself is; the internal toggle is not, per FR-007's "internal toggle" framing — matches how `AnxietyDashboardPage`'s own sub-tabs already behave, `routes/anxiety/AnxietyDashboardPage.tsx:14-25`, no query-string sync there either). Both boards keep their own internal loading/error/empty states exactly as they render today inside their standalone pages — nothing about their internals changes, only their mount point.
