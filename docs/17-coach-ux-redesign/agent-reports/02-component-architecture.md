# Agent report 02 — Component architecture

> Panel: coach UX audit 2026-07-11 · Agent: `react-ui-engineer` (Sonnet) · Read-only static audit, no files modified.
> Note: live shadcn registry lookups (`mcp__shadcn__*`) failed in the sandbox (proxy blocked `ui.shadcn.com`); the adoption plan is grounded in the stable shadcn/ui catalog — re-verify item names with `mcp__shadcn__search_items_in_registries` before running any `add` command.

## Inventory & duplication findings

1. **`components/ui/` has 13 primitives, confirmed exact set**: `badge, button, card, dialog, dropdown-menu, sheet, skeleton, table, tabs, textarea, toggle-group, toggle, tooltip`. Missing for a form-heavy app: `input`, `select`, `label`, `form`, `checkbox`, `radio-group`, `popover`, `calendar`/date-picker, `command`, `sonner`/toast, `alert`, `alert-dialog`, `separator`, `breadcrumb`, `sidebar`. All are evidenced below as hand-rolled substitutes, not just theoretical gaps.

2. **Raw `<input>` instead of an `Input` primitive**: 151 occurrences across 60 files (e.g. `components/athletes/AthleteForm.tsx`, `components/calendar/EventForm.tsx`, `components/technique/ExerciseForm.tsx`). 17 of those files independently redeclare a local `const inputClass = "..."` string with equivalent Tailwind chrome (`AthleteForm.tsx:36-37`, `AnthropometryForm.tsx`, `EventForm.tsx`, `ParentFormDialog.tsx`, `DurationPicker.tsx:24-27`, +12 more).

3. **Raw `<select>` instead of a `Select` primitive**: 82 occurrences across 40 files (e.g. `SessionFiltersBar.tsx`, `CompetitionFiltersBar.tsx`, `AthletesListPage.tsx`).

4. **No toast/notification primitive** (no `sonner`, confirmed zero hits in `src/` or `package.json`). At least two components hand-roll their own toast with `useState` + `setTimeout`: `components/consent/ConsentStatusPanel.tsx:276-281,363-368` ("Estado de toast simple (sin librería externa)") and `components/competitions/import/ImportWizard.tsx:526-527,643-647` (`conditionsToast` state, manual `setTimeout(…, 5000)`). 17 files reference "toast" only in comments describing this ad hoc convention (e.g. `hooks/race/useRaceEvents.ts:19,338`). Two raw `window.confirm()` calls also exist as a destructive-action guard outside any dialog system: `components/training/MediaGallery.tsx:133`, `routes/competitions/CompetitionFormPage.tsx:471`.

5. **Hand-rolled combobox, deliberately**: `components/ai/AthleteCombobox.tsx` (313 lines) reimplements a full `role="combobox"`/`listbox` widget with manual keyboard nav, click-outside, and focus return, explicitly *documented* (lines 9-13) as avoiding Radix Popover/cmdk "para evitar duplicación de Radix Popover en el chunk lazy". A deliberate, reasoned trade-off — worth revisiting rather than blindly overriding.

6. **Raw `type="date"` inputs**: 12 files (`AthleteForm.tsx`, `AnthropometryForm.tsx`, `EventForm.tsx`, `CompetitionFormPage.tsx`, etc.) — no calendar/date-picker primitive exists anywhere in `components/ui/`.

7. **Inline `boxShadow` style objects instead of design tokens**: 368 occurrences across 117 files, e.g. `AppShell.tsx:220,244,282` and `DashboardPage.tsx:32,42,56` (the *same* 3-layer string repeated verbatim three times in one file). Of these, **177 occurrences are the exact literal string** `"rgba(34, 42, 53, 0.08) 0px 0px 0px 1px"` — which is *already* registered as `--shadow-ring` in the Tailwind `@theme` block (`style.css`) and would auto-generate a `shadow-ring` utility class, currently used **zero** times anywhere.

8. **Redundant/dead shadow tokens** — two parallel token systems in `style.css`: the `:root` block defines `--shadow-ring-soft` (consumed via a hand-written `.shadow-ring-soft` utility, used correctly 37/37 times, e.g. `components/ui/card.tsx:6,21`), while the separate `@theme` block *redefines the same value* as `--shadow-card` plus `--shadow-ring`, `--shadow-ambient`, `--shadow-button-highlight` — all auto-generating Tailwind utilities with **0 usages** anywhere. Confirmed via `grep -c` per class name.

9. **"Cal Sans" hardcoded inline 115 times across 84 files** (e.g. `DashboardPage.tsx:13`, baked into the primitive itself at `components/ui/dialog.tsx:102-105`), always as `style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}`. `frontend/public/fonts/` contains **only** `InterVariable.woff2` — no Cal Sans file, no `@font-face` for it anywhere. `docs/05-design-system/design.md` (lines 56-58, 85-90, 185-186) mandates Cal Sans for all headings ≥24px, but the `@theme` token `--font-display` resolves to `system-ui, sans-serif`. Net effect: 115 duplicated inline style objects that render identically to doing nothing, because the referenced font is never loaded.

10. **Two confirm-dialog implementations with materially different accessibility** in `components/common/`: `ConfirmModal.tsx` correctly wraps the Radix-backed `Dialog` primitive (9 usages) but sets `autoFocus` on the **confirm** button unconditionally, even when `confirmDanger` is true (line 66) — destructive-action dialogs should default focus to Cancel. `ConfirmDeleteDialog.tsx` (5 usages) is a fully hand-rolled `fixed inset-0` overlay with **no Radix Dialog** — no real focus trap, no automatic Escape/outside-click semantics beyond manual wiring — a genuine accessibility regression relative to the project's own stated standard.

11. **The `ConfirmDeleteDialog` hand-rolled-modal pattern is copy-pasted 5×**: the identical `overlayStyle`/`dialogStyle`/`btnPrimaryStyle`/`btnSecondaryStyle` const block appears verbatim in `components/common/ConfirmDeleteDialog.tsx`, `components/consent/ConsentRenewalModal.tsx`, `components/consent/RevokeConsentDialog.tsx:24-40`, `components/onboarding/OnboardingWizard.tsx:46-58`, and `components/training/NotifyParentsDialog.tsx` — all bypassing the already-correct `components/ui/dialog.tsx`. Contrast with `components/strength/AgeBandGuardrailDialog.tsx` and `components/intervals/AgeGateDialog.tsx`, which **do** use the Dialog primitive correctly and even cross-reference each other in comments as the "mirror" pattern to follow — proof the team already has the right template, inconsistently applied.

12. **`components/common/` vs `components/shared/` split has no discernible rule**: `common/` holds two overlapping dialogs; `shared/` holds only `PHVBadge.tsx` (28 lines).

13. **`routes/technique/*` and `routes/strength/*` are near-mirror modules**, several explicitly self-documented:
    - `CatalogGrid.tsx`: strength's docstring says "Mirror de `components/technique/CatalogGrid.tsx`."
    - `FilterBar.tsx`: both exactly **259 lines**, same RHF watch/reset structure, differ only in field names/options.
    - `ExerciseCard.tsx`: same WCAG-48×48 Link-on-name layout, badge-row/footer-row shell identical.
    - `routes/*/CatalogPage.tsx`, `routes/*/ExerciseDetailPage.tsx` (274 changed lines out of ~450 combined — mostly field renames), `routes/*/AthleteProgressPage.tsx` — structurally identical page shells (skeleton → error w/ retry → lazy-loaded heavy board).
    - `routes/strength/BlockBuilderPage.tsx:26-29` docstring: "Mirror de `routes/technique/SessionBuilderPage.tsx` … para el patrón de estados."
    - `SessionAssembler.tsx` (682 lines) vs `BlockAssembler.tsx` (754 lines) share the same `<Card><CardContent>` metadata-grid + picker-list shell but ~78% of lines differ due to genuinely different domain fields — "shares the pattern, not the code."
    - Asymmetry, not full duplication: `technique/` additionally has `ExerciseForm`, `ExerciseFormDialog`, `CircuitDiagram`, `CircuitLayout`, `MixedAgeNotice`, `SkillProgressBoard` (curation UI — strength's catalog is static by design); `strength/` has its own `AgeBandGuardrailDialog`, `ExerciseIllustration`, `ProgressNotesBoard`.

14. **Three separate stepper implementations**: `components/training/session-wizard/SessionStepper.tsx` (docstring line 16: "Reusa el patrón de ImportWizard"), an inline `function Stepper(...)` at `ImportWizard.tsx:209-243` (near-identical markup/classes to SessionStepper), and `components/onboarding/OnboardingStepper.tsx` (visually distinct: checkmarks, connector lines, mobile "Paso X de N" collapse).

15. **`OnboardingStepper.tsx` uses Tailwind classes that resolve to nothing in this theme**: `text-foreground` (lines 90, 162), `bg-muted`/`text-muted-foreground`/`border-muted-foreground` (lines 64, 82, 92, 159, 179). `components/ai/AnthropometricRecordExplanationCard.tsx:100` has the same issue. `components.json` sets `"cssVariables": false`, and `style.css` never defines `--color-foreground`, `--color-muted`, `--color-muted-foreground`, or `--color-border` — these are the shadcn "new-york + CSS variables" semantic-token convention this project opted out of. Tailwind v4 cannot generate a utility for an undefined `@theme` color, so these classes are silent no-ops. A real, if low-severity, visual bug.

16. **`OnboardingWizard.tsx` hand-rolls Prev/Next buttons** (lines 300-333) with local `btnPrimaryStyle`/`btnSecondaryStyle` inline objects instead of the existing `Button` component (which has matching `default`/`outline` variants).

17. **`App.tsx` has 21 `<Suspense>` blocks**, each with a bespoke but structurally identical fallback: `<div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">Cargando X…</div>`. Only the loading copy differs.

18. **Eager vs lazy import split is inconsistent**: 22 `lazy()` calls (profile, insights hub/season/athlete/club, anxiety ×2, technique ×5, strength ×4, activities, activity-match, template-library, session-assistant) vs **35 eager top-level imports** (`App.tsx:60-93`) covering the entire athletes module, parents module, core training (sessions/reports/newsletters), calendar, and core competitions — the app's largest, longest-lived feature areas ship in the initial bundle while newer modules were built lazy. Inconsistent policy, not a deliberate one.

19. **Page header duplication**: 59 route files declare an `<h1>` with the inline Cal Sans style rather than a shared header component; 16 files reimplement an `ArrowLeft`-icon back-link.

20. **Stat/KPI cards ignore the existing `Card` primitive**: `DashboardPage.tsx:30-66` hand-rolls three `<article>` "stat cards" with the identical inline multi-layer `boxShadow` string that `Card` already applies via `shadow-ring-soft` by default.

21. **Data tables: raw `<table>` dominates over the shadcn `Table` primitive.** 20 files use raw `<table>`/`<thead>`/`<tr>` (`AthletesTable.tsx:79-137`, `ParentsTable.tsx`, `SessionsTable.tsx`, `DiffTable.tsx`, etc.) vs only 4 files using `components/ui/table.tsx` (`ResultsTable.tsx`, `StandingsTable.tsx`, `RosterPanel.tsx`, `PlanVsActualTable.tsx`). `AthletesTable.tsx` hand-rolls a separate mobile `<ul>` card list (lines 17-70) *and* a desktop raw table (72-137), each duplicating the same inline `boxShadow` again. By contrast, `ResultsTable.tsx:395-431` demonstrates the better pattern already present — a single semantic `<Table>` with responsive column-hiding (`hidden sm:table-cell`, `hidden md:table-cell`, `hidden lg:table-cell`) instead of a parallel mobile view — this should be the template, not the outlier.

22. **Filter bars duplicated 5×** across domains, all hand-rolled: `calendar/FiltersBar.tsx` (81 lines), `training/SessionFiltersBar.tsx` (77), `competitions/CompetitionFiltersBar.tsx` (260), `technique/FilterBar.tsx` and `strength/FilterBar.tsx` (259/259, near-identical RHF `watch`+`reset` pattern).

23. **Four independent file-dropzone implementations** (761 combined lines), all reimplementing drag/drop + accept-type validation + hint text: `RouteFileDropzone.tsx` (92), `MediaUploadZone.tsx` (279), `ai/UploadZone.tsx` (165), `import/RaceUploadZone.tsx` (225).

24. **Empty/error state copy is duplicated but not componentized**: 37 files repeat an empty-state text block (e.g. `technique/CatalogGrid.tsx:129-135`), 81 files repeat a "Reintentar"/retry button block (e.g. `technique/ExerciseDetailPage.tsx:301-307`). Cold-start-aware error messaging is separately reimplemented per module (`resolveErrorMessage` in `SessionBuilderPage.tsx:36-49`, `mapTechniqueError`, `mapStrengthError`, etc.) rather than centralized.

25. **Positive findings (no action needed)**: date formatting is well-centralized in `lib/datetime.ts` (single source, `CLUB_TIMEZONE`/`CLUB_LOCALE`-aware, handles naive-UTC MySQL datetimes) — no duplicate date helpers found. A heuristic dead-code scan (cross-referencing every non-`ui/` component basename against the rest of `src/`) found **zero** orphaned/unused component files among ~150 checked (spot-checked `MixedAgeNotice`, `RaceConditionsCard`, `AnalysisRunTimeline`, `ExerciseIllustration`, `AgeBandGuardrailDialog`, `StaleAnalysisBadge`, `AthleteCombobox`, `HITLApprovalCard` individually). `Badge` and `Table` primitives are both well-built (cva variants, semantic HTML, WCAG-AA color pairs documented in comments) — the problem is adoption, not quality.

## Proposed shared-component catalog

| Component | Purpose / API sketch | Replaces | Effort |
|---|---|---|---|
| `PageHeader` | `{ title, subtitle?, backTo?: string, actions?: ReactNode }`. `<h1>` + optional back-link + right-aligned action slot. | 59 hand-rolled `<h1>` blocks + 16 `ArrowLeft` back-links | S |
| `StatCard` | `{ label, value: ReactNode, isLoading?, hint? }`. Thin wrapper over `Card`. | `DashboardPage.tsx:30-66` hand-rolled articles; similar ad hoc stat blocks | S |
| `EmptyState` | `{ icon?: LucideIcon, title, description, action?: ReactNode }` | 37 files' duplicated "sin resultados" blocks | S |
| `ErrorState` | `{ message?, onRetry?, isColdStart?: boolean }`, with a single centralized cold-start detector replacing per-module `resolveErrorMessage`/`mapTechniqueError`/`mapStrengthError` helpers | 81 files' retry blocks + duplicated cold-start logic | M |
| `ConfirmDialog` | `{ open, title, description, confirmLabel?, cancelLabel?, tone: "default"\|"danger", isPending?, errorMessage?, onConfirm, onCancel }`, built on Radix **AlertDialog** with focus defaulting to Cancel when `tone="danger"` | `ConfirmModal` (9 sites) + `ConfirmDeleteDialog` (5 sites) + the confirm-chrome portions of `RevokeConsentDialog`, `ConsentRenewalModal`, `NotifyParentsDialog` (these three keep a custom body slot — chrome unification only) | M |
| `LibraryFilterBar` | Config-driven filter shell: `{ search?: FieldConfig, selects: FieldConfig[], onChange, onClear }` | `technique/FilterBar` + `strength/FilterBar` (near 1:1); partial fit for calendar/training/competitions filter bars | M |
| `CatalogGrid` (generic) | `{ items, isLoading, isError, skeletonCount, renderCard, emptyState }` | `technique/CatalogGrid` + `strength/CatalogGrid` (near-verbatim today) | S–M |
| `LibraryEntityCard` | `{ href, title, badges: ReactNode[], footer?: ReactNode, onEdit? }` | `technique/ExerciseCard` + `strength/ExerciseCard` | M |
| `BuilderShell` | Page shell for "assemble a session/block": metadata-form `Card`, picker-list `Card`, sticky submit footer with pending/error state | `SessionBuilderPage`/`BlockBuilderPage` outer shell; the `Card` wrapper portions of the assemblers (domain bodies stay) | L (lowest literal overlap — do incrementally) |
| `Stepper` (unified) | `{ steps: {idx,label}[], active, onStepClick?, variant?: "compact"\|"detailed" }` | `SessionStepper` + `ImportWizard`'s inline `Stepper` (near-trivial merge) | S |
| `WizardShell` | Card wrapper + header(stepper+description) + body + footer(Prev/Next/Submit using real `Button`) | `OnboardingWizard`'s hand-rolled chrome; optional future adoption by Import/Session wizards | M |
| `FormField` | Label + control + RHF error, built on shadcn `form.tsx` | the 58-hit hand-rolled label pattern + 17 duplicated `inputClass` consts | M (adopt incrementally, purely additive) |
| `FileDropzone` | `{ accept, maxSizeMb, onFiles, hint, preview?: ReactNode }` | 4 dropzones at the drag/drop/accept-validation layer (keep domain-specific preview/EXIF messaging as slots) | M–L |
| `DataTable` (convention) | Document + lightly wrap `ui/table.tsx` with the responsive column-hiding pattern proven in `ResultsTable.tsx`, optional `renderMobileCard` | 20 raw-`<table>` files, migrated incrementally | M (S per file) |
| `Toaster` (via `sonner`) | `<Toaster />` mounted once in `App.tsx` + `toast.success()/error()` | hand-rolled toast state in `ConsentStatusPanel`, `ImportWizard`, + ad hoc pattern in 17 files' comments | S to add, M to migrate |

## shadcn/ui adoption plan

| Primitive | Where it lands | Why |
|---|---|---|
| `input`, `label` | 151 raw `<input>` + 58 hand-rolled label blocks | closes the largest quantified gap; consistent focus/error styling |
| `select` | 82 raw `<select>` | keyboard/ARIA correctness out of the box |
| `form` | RHF + Zod wrapper (`FormField`/`FormItem`/`FormMessage`) | removes per-field `aria-describedby` plumbing |
| `checkbox`, `radio-group`, `switch` | onboarding consent steps, athlete `sex` field, wizard toggles | currently plain inputs |
| `alert` | inline red/amber boxes (`OnboardingWizard.tsx:279-289`, `ConfirmDeleteDialog.tsx:88-98`) | consistent variants |
| `alert-dialog` | backing primitive for `ConfirmDialog` | purpose-built for destructive confirms; fixes focus-on-confirm bug by construction |
| `popover` + `calendar` (date-picker recipe) | 12 raw `type="date"` fields, esp. `birth_date` and event dates | better on tablet than native pickers |
| `command` + `popover` (combobox recipe) | candidate replacement for `AthleteCombobox` — **re-confirm the documented bundle-size trade-off first** | don't blindly override a reasoned decision |
| `sonner` | `<Toaster/>` in `App.tsx` | current recommended shadcn toast |
| `separator` | manual `border-t border-[rgba(34,42,53,0.08)]` divider lines | small consistent cleanup |
| `sidebar` | `AppShell` hand-rolls exactly this block's job (collapsible aside, mobile drawer via `useState`, manual hamburger) | persisted collapsed state + keyboard shortcut for free; `sheet` (already installed) is its base. Highest blast radius — own P1/P2 item |
| `breadcrumb` | **not recommended** — all 16 back-links are single-level; `PageHeader.backTo` suffices | — |

## Design-token gaps

1. **Shadow tokens — two competing systems, pick one.** Quick win: the plain-ring literal appears **177 times** inline and is *already* registered as `--shadow-ring` → the utility `shadow-ring` exists today with zero new code; swap `style={{ boxShadow: "..." }}` → `className="shadow-ring"` at all 177 sites. Delete one of the duplicate multi-layer definitions (`@theme --shadow-card` vs `:root --shadow-ring-soft`), update `design.md` to the surviving name. Wire up or delete unused `--shadow-ambient`/`--shadow-button-highlight` (the inset-highlight pattern they'd serve is currently inlined in `ConfirmDeleteDialog.tsx:13-16` and `OnboardingWizard.tsx:51-54` — wiring beats deleting since that pattern is also duplicated).
2. **Cal Sans is a phantom token.** Either (a) ship the actual Cal Sans woff2 into `public/fonts/` + `@font-face` + point `--font-display` at it, collapsing 115 inline occurrences into one `font-display` utility, or (b) formally amend `design.md` to drop Cal Sans and consolidate on `font-sans`/`font-semibold`. The current state is accidental, not chosen — decide explicitly.
3. **Undefined semantic tokens** in `OnboardingStepper.tsx` + `AnthropometricRecordExplanationCard.tsx:100`: either register `--color-foreground`/`--color-muted`/`--color-muted-foreground`/`--color-border` in `@theme` (needed anyway if the `sidebar` block is adopted) or replace the 7 call sites with charcoal/mid-gray/light-gray vocabulary.
4. **Border-color literal duplicated as arbitrary-value class**: `border-[rgba(34,42,53,0.08)]`/`[…0.06]` repeatedly instead of registering the existing `--color-border-gray` in `@theme` and using `border-border-gray`.
5. **Spacing/typography**: no duplication problems found — coherent scales, consistently used. Not a priority area.

## Deletions/consolidations

| Item | Action | Risk |
|---|---|---|
| `@theme`'s unused `--shadow-card`, `--shadow-ambient`, `--shadow-button-highlight` (+ the `--shadow-ring`/`--shadow-ring-soft` name duplication) | consolidate on one naming; adopt (don't delete) `shadow-ring` | Low |
| `ConfirmDeleteDialog.tsx` | fold into `ConfirmModal`/new `ConfirmDialog` with `tone="danger"` + `errorMessage`; delete the hand-rolled version | Medium — 5 call sites, simple prop mapping; net a11y improvement |
| Copy-pasted modal chrome block (5 files) | delete after migrating onto `Dialog`/`ConfirmDialog`/`Button` — for `RevokeConsentDialog`/`ConsentRenewalModal` swap only the chrome (they embed RHF forms in the body) | Medium |
| Inline `Stepper` in `ImportWizard.tsx` | delete, import the unified `Stepper` | Low |
| `components/common/` vs `components/shared/` | merge into one folder | Low, mechanical |
| Domain one-offs (`MixedAgeNotice`, `AgeBandGuardrailDialog`, …) | **do not delete** — confirmed genuinely used | — |
| Dead component files | none found — no action | — |

## Prioritized plan

**P0 (foundational, unblocks everything else):**
- Add `input`, `select`, `label`, `form` primitives; wire `sonner` `<Toaster/>` into `App.tsx`.
- Adopt `shadow-ring` utility at the 177 exact-match call sites.
- Resolve the Cal Sans decision (ship the font or drop the reference).
- Fix `ConfirmModal.tsx:66` `autoFocus` on destructive confirm (one line, real a11y bug, used 9×).

**P1 (consolidation, highest duplication payoff):**
- `LibraryFilterBar`, `CatalogGrid`, `LibraryEntityCard` — migrate `technique/` + `strength/` (single largest, best-evidenced clone).
- `ConfirmDialog` on `alert-dialog`; retire `ConfirmDeleteDialog` + the 5-file copy-pasted chrome.
- `PageHeader`, `StatCard`, `EmptyState`, `ErrorState`.
- Migrate the 20 raw-`<table>` files onto `ui/table.tsx` per the `ResultsTable` convention.

**P2 (larger / higher-risk):**
- `sidebar` primitive adoption for `AppShell` (every authenticated route renders through it).
- `BuilderShell` extraction (lowest literal overlap — incremental).
- `FileDropzone` consolidation (each has real domain-specific needs).
- Re-evaluate `AthleteCombobox` vs `command`+`popover` bundle trade-off.
- Reconcile `OnboardingStepper` into the unified `Stepper` (as a `variant`).

**Quick wins (≤1 day each):**
1. Replace the 177 exact-literal `boxShadow` inline styles with `className="shadow-ring"`.
2. Fix `autoFocus` in `ConfirmModal.tsx:66` to target Cancel when `confirmDanger`.
3. Merge `ImportWizard`'s inline `Stepper` into `SessionStepper`.
4. Replace `DashboardPage`'s 3 hand-rolled stat `<article>`s with `Card`/`CardContent`.
5. Fix the 7 broken `text-foreground`/`bg-muted`/`text-muted-foreground` classes (swap to `text-charcoal`/`bg-light-gray`/`text-mid-gray` until semantic tokens are formally registered).
6. Merge `components/common/` and `components/shared/` into one folder.
