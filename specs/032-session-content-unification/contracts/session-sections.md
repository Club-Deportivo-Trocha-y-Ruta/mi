# Contract — Session Detail Sections (UI)

**Surface**: `frontend/src/routes/training/SessionDetailPage.tsx`, route `/training/sessions/:id` (unchanged path — FR-008).

**Purpose**: Replace today's 7 stacked full-width blocks (Header, Detalles, Recorrido, Asistencia, Bloques de fuerza, Estructura de intervalos, Fotos y videos — `SessionDetailPage.tsx:548-1141`) with at most 4 named sections on the shared `components/ui/tabs.tsx` primitive (research.md R8), URL-synced via `?section=`.

## Section inventory

| `?section=` value | Label (es-CO) | Content (today's blocks folded in) | Notes |
|---|---|---|---|
| `resumen` | "Resumen" | Header status/actions (execute/cancel/edit) + Detalles (description, coach notes) + Recorrido (route text, Strava link, GPX/FIT upload, `RouteViewer`) | The session header itself (title, badges, date/time/place, action buttons) stays outside the tab body — it is not a "tab" of its own, it is the page chrome above the tabs, same as today (`:550-607`). |
| `asistencia` | "Asistencia" | `AttendanceTable` exactly as today (`:756-765`), including linked/unlinked Strava activity grouping. | Unchanged component; only its position in the page changes. |
| `plan` | "Plan" | Technique exercises (new inline picker, contracts/unified-attach-flow.md) + Bloques de fuerza (existing list + detach, `:768-853`, plus new preselect/pick-existing entry points) + Estructura de intervalos (unchanged, `:855-1037`) + plan-vs-actual links (`StructureMatchLink`, `:178-198`). | The one section every attach flow in this feature ends on. |
| `media` | "Media" | `MediaUploadZone` + `MediaGallery` exactly as today (`:1104-1141`). | Unchanged components; only position changes. |

No 5th section: the `NotifyParentsDialog` (cancel-session flow) remains a page-level dialog, not a section, exactly as today (`:1143-1156`).

## URL sync mechanism (copied from `AthleteDetailPage.tsx`, renamed)

- Query param name: `section` (was `tab` on `AthleteDetailPage`). Valid values: `resumen | asistencia | plan | media`. An unknown/malformed value is treated as absent (falls through to the default rule) — mirrors `parseTabParam`'s validation (`AthleteDetailPage.tsx:64-69`).
- On mount: if `?section=` is present and valid, it wins. If absent, the **default rule** below decides.
- On section change (tab click): `setSearchParams` updates `?section=` with `{ replace: true }` semantics for the *initial* auto-selected default (so hitting back doesn't require clicking through the auto-selected tab), but a normal push-history entry for an explicit coach-initiated tab click — same distinction `AthleteDetailPage.tsx:404-413` already makes with `next.delete("tab")` for the non-default case vs. explicit sets otherwise. Refresh and back/forward navigation preserve the active section (SC-006) because the section lives in the URL, not component state.
- Focus/announcement: per `specs/028-frontend-design-foundation/contracts/shared-components.md`'s `Stepper` focus convention (R10 of 028's research — move focus to the new section's heading on change), each section body's top-level `<h2>` receives `tabIndex={-1}` and a `.focus()` call on `TabsContent` mount, so switching sections announces to screen readers the same way the unified `Stepper` does for wizard steps. `components/ui/tabs.tsx`'s Radix-backed `TabsContent` already provides the DOM hook (`ref` forwarding, `:53-66`) this needs.

## Default section rule

**`asistencia` when `session.scheduled_date` is today in club timezone (`CLUB_TIMEZONE = "America/Bogota"`, `lib/datetime.ts:1`); `resumen` otherwise.**

Rationale (research.md R8): attendance is the highest-severity, highest-frequency field-day friction identified in the UX audit (`docs/17-coach-ux-redesign/agent-reports/01-ux-heuristics-workflows.md`, Flow 2), and "today" is precisely when a coach opening a session is doing so to run it, not to plan or review it. This is computed once, client-side, from `session.scheduled_date` (already loaded by `useTrainingSession`) — no new endpoint.

## Deep-link mapping (FR-008: no screen address changes)

| Existing entry point | Lands on |
|---|---|
| Bookmarked/shared `/training/sessions/{id}` (no query string) | Default rule above |
| Interval "Ver comparación plan vs. real" link (`StructureMatchLink`, in-page) | `plan` (same page, just switches the active section instead of scrolling) |
| Any attach flow returning the coach after a successful attach (technique inline, strength preselect-and-attach, strength pick-existing) | `?section=plan` explicitly (contracts/unified-attach-flow.md) |
| `/training/sessions/{id}/activity-match/{activityId}` | Unaffected — separate route (`App.tsx:385`), not a section of this page |
| `/training/sessions/{id}/edit` | Unaffected — separate route (`App.tsx:377`) |

## Per-section content inventory (what must render, so nothing is silently dropped in the refactor)

- **Resumen**: `SessionStatusBadge`, date/time/duration/place line, Editar/Cancelar/Marcar ejecutada actions (planned-only), Descripción, Notas del entrenador (autosaving textarea with "Guardando…" live region), Recorrido description, Strava link, GPX/FIT dropzone + `RouteViewer`.
- **Asistencia**: attendee count, loading/error states, `AttendanceTable` with linked/unlinked activity grouping.
- **Plan**: three content blocks (technique/strength/intervals) each with its own loading/error/empty state and attach/edit/remove actions in place (FR-005), plus plan-vs-actual links per linked activity.
- **Media**: upload dropzone (disabled when cancelled), gallery with delete.

## Empty states (FR-005)

When the Plan section has none of the three content types yet, it renders **one** purposeful empty state (per `specs/028-frontend-design-foundation/contracts/shared-components.md`'s `EmptyState` component) offering all three attach actions together ("Agregar ejercicios de técnica" / "Agregar bloque de fuerza" / "Crear estructura de intervalos") rather than three separate blank-looking sub-blocks — this directly satisfies Acceptance Scenario 4 of User Story 2 ("purposeful empty states with the three attach actions — not blank space"). Once any one type has content, that type's own block renders normally and the other two keep their individual (smaller, inline) empty prompts, exactly as today's per-block empty copy already does (e.g. "Sin bloques de fuerza adjuntos a esta sesión," `SessionDetailPage.tsx:794-798`).

## Non-functional

- No new npm dependency (`@radix-ui/react-tabs` already installed and used, `components/ui/tabs.tsx:14`).
- Performance opportunity (Constitution IV, not mandatory for this plan but recommended at task-breakdown time): today all of `attendanceQuery`, `mediaQuery`, `strengthBlocksQuery`, `structureQuery`, `sessionActivitiesQuery`, `unlinkedActivitiesQuery` fire unconditionally on page mount regardless of scroll position (`SessionDetailPage.tsx:376-398`). Sectioning creates the option to gate non-active-section queries behind `enabled: activeSection === '...'`, deferring work the coach may never scroll to today. This plan does not mandate it (out of scope creep risk) but flags it as a natural, low-risk follow-on now that section boundaries exist.
- Accessibility: `jest-axe` zero-violations on the sectioned page (Constitution II); each `TabsTrigger` keeps its native 48px target (`ui/tabs.tsx:42`, `min-h-11` = 44px — **note**: 44px, not 48px; existing primitive default falls one step short of the club's 48px floor and must be bumped to `min-h-12` as part of this feature's adoption, since `SessionDetailPage`'s tabs are the first place this primitive is used on the single densest, most touch-critical coach screen).
