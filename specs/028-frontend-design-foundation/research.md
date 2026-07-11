# Research — 028 Frontend Design Foundation & Everyday Reliability

> Phase 0 output. Grounded 2026-07-11 via: live repo inspection (`frontend/package.json`, `components.json`, `src/style.css`, `playwright.config.ts`), Context7 docs lookup (Tailwind CSS v4 `@theme` / `@custom-variant`), web research (Cal Sans licensing/distribution), and the audit evidence in `docs/17-coach-ux-redesign/agent-reports/` (01, 02, 04). **This file also serves as the shared research base for features 029–033** — their research.md files reference it instead of repeating it.

## R1. shadcn/ui primitives to add

- **Decision**: Add via the shadcn CLI: `input`, `label`, `select`, `form`, `checkbox`, `radio-group`, `switch`, `alert`, `alert-dialog`, `separator`, `sonner`. Defer `popover` + `calendar` (date-picker recipe) to a follow-up unless a 028 task needs them; `sidebar` and `command` are explicitly NOT added here (030 decides sidebar; command palette deferred by program decision D5).
- **Rationale**: These close the measured gaps (151 raw `<input>`, 82 raw `<select>`, 58 hand-rolled labels, no toast primitive, no accessible confirm primitive). Several Radix deps are *already installed* (`@radix-ui/react-label`, `react-select`, `react-radio-group`, `react-separator`, `react-popover`, plus umbrella `radix-ui@1.4.3`) so most additions add little to no new transitive weight. `components.json` is already configured (new-york style, `cssVariables: false`, lucide icons, aliases) — generated components will use literal Tailwind classes consistent with the project's existing token approach.
- **Environment caveat**: the live registry could not be verified from this sandbox (requests to `ui.shadcn.com` are blocked by the egress proxy; the MCP registry client failed with "Request was cancelled"). The item names above are the long-stable canonical catalog names; the CLI fails loudly on a wrong name, so verify at install time (`npx shadcn@latest add <item>`), and expect the CLI to resolve the style as `new-york-v4` under Tailwind v4.
- **Alternatives considered**: hand-rolling primitives (rejected: that is the current state and the source of the drift); Radix raw without shadcn wrappers (rejected: loses the project's established cva/variant conventions in `ui/`).

## R2. Toast standard

- **Decision**: `sonner`, mounted once next to `TooltipProvider` in `App.tsx`; success/error toasts for mutation outcomes; the two hand-rolled toast implementations (`ConsentStatusPanel`, `ImportWizard` `conditionsToast`, plus the copy-pasted `ToastBanner` in `CompetitionDetailPage`/`UnlinkedCompetitorsTab`) are migrated and deleted.
- **Rationale**: shadcn's current recommended toast (their older `toast` component is deprecated in favor of sonner); ~4 KB gz; ARIA-live handled; respects `prefers-reduced-motion` (and the project's global reduced-motion CSS remains the backstop).
- **Alternatives considered**: keep per-page banners (rejected: duplicated, inconsistent, consumes layout space on dense pages); Radix Toast primitive directly (rejected: more assembly for the same result).

## R3. ConfirmDialog on alert-dialog

- **Decision**: One `ConfirmDialog` shared component built on shadcn `alert-dialog` with `tone: "default" | "danger"`; when `tone="danger"`, initial focus is the Cancel action. It replaces `ConfirmModal` (9 call sites — also fixing its `autoFocus`-on-confirm bug), `ConfirmDeleteDialog` (5 call sites, hand-rolled overlay without focus trap), both `window.confirm()` calls (`MediaGallery`, `CompetitionFormPage`), and the confirm-chrome of `NotifyParentsDialog` (which keeps its form body inside a Radix `Dialog`).
- **Rationale**: `alert-dialog` is purpose-built for destructive confirmation (role `alertdialog`, focus semantics by construction); consolidating five copy-pasted modal chromes is the rule-of-three enforced.
- **Alternatives considered**: extend `ConfirmModal` (rejected: generic `Dialog` requires manual `role="alertdialog"` bolt-on and manual focus policy — the exact source of today's bug).

## R4. Cal Sans (program decision D3: ship it)

- **Decision**: Self-host via the `@fontsource/cal-sans` npm package: CSS `@import "@fontsource/cal-sans"` (weights as needed) in `style.css`, set `@theme --font-display: "Cal Sans", system-ui, sans-serif`, replace all 115 inline `style={{ fontFamily: "'Cal Sans'..." }}` objects with the `font-display` utility (mostly inside the new `PageHeader`/`ui` primitives), and update `docs/05-design-system/design.md` to shipped reality.
- **Rationale**: Cal Sans v2 is SIL OFL 1.1 (license-clean for self-hosting), distributed as woff2 via the official calcom repo, Google Fonts, and Fontsource — the npm route pins a version, bundles the font through Vite (zero runtime third-party requests, satisfying the minors-privacy bar), and avoids manually vendoring font binaries. `font-display: swap` keeps LCP unaffected (Inter fallback paints first).
- **Sources**: [calcom/sans (GitHub)](https://github.com/calcom/sans) · [@fontsource/cal-sans (npm)](https://www.npmjs.com/package/@fontsource/cal-sans) · [Cal Sans on Google Fonts](https://fonts.google.com/specimen/Cal+Sans)
- **Alternatives considered**: Google Fonts CDN (rejected: third-party request = privacy + offline risk); manual woff2 in `public/fonts/` (viable fallback if the Fontsource package lags v2; rejected as first choice: unversioned binary in git); dropping the font (rejected by decision D3).

## R5. Design-token consolidation (Tailwind v4)

- **Decision**: (a) Adopt the existing-but-unused `--shadow-ring` `@theme` token: swap the 177 exact-literal inline `boxShadow` styles for `className="shadow-ring"`. (b) Collapse the duplicate multi-layer shadow definitions: keep `@theme --shadow-card` (auto-utility `shadow-card`) as the single name, alias/retire the hand-written `.shadow-ring-soft` utility after migrating its 37 uses (mechanical rename). (c) Register `--color-border-gray` in `@theme` so `border-border-gray` replaces `border-[rgba(34,42,53,0.08)]` arbitrary values. (d) Add semantic status tokens to `@theme`: `--color-success: #0ca30c`, `--color-warning: #fab219`, `--color-danger: #d03b3b` (constitution III semantics; values from the validated dataviz status scale) — consumed by `StatusBadge` now and by charts in 033. (e) Fix the 7 no-op semantic classes (`text-foreground`, `bg-muted`, `text-muted-foreground`, `border-muted-foreground`) in `OnboardingStepper`/`AnthropometricRecordExplanationCard` by swapping to project vocabulary (registering the full shadcn semantic-token set is deferred to 030's sidebar decision). (f) Delete the dead `text-light-gray-dark` class and the unused lime `--color-accent` block; merge the duplicate `--color-link-blue`/`--color-primary` names (keep `--color-primary`).
- **Rationale**: Confirmed v4 mechanics via Context7: `@theme --color-*`/`--shadow-*` auto-generate utilities, so (a)–(d) are zero-new-code token work. Inline styles cannot respond to `prefers-color-scheme` — this consolidation is also the prerequisite for 033's optional dark mode (`@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *))` documented for that feature).
- **Alternatives considered**: keeping `.shadow-ring-soft` as the survivor (equivalent; `@theme` name chosen because it auto-generates and matches v4 idiom); oklch re-specification of the palette (rejected: unnecessary churn, hex values already ship).

## R6. Rubric control replacement

- **Decision**: Replace the four native `<input type="range">` sliders in `RubricSliders` with discrete step controls built on the existing `ToggleGroup`/`ToggleGroupItem` primitive — RPE 0–10 as 11 steps (48×48 px, wrapping to two rows on narrow widths), Esfuerzo/Actitud/Técnica 1–5 as 5 steps; keep `aria-valuetext`-equivalent labels (OMNI anchors) and the existing autosave wiring untouched.
- **Rationale**: The pattern already exists in-repo (`session_kind` in `StepGeneral`, `surface_condition` in `ImportWizard`) — consistency for free; discrete steps match the data (integers only), eliminate drag precision issues with gloves, and give every value a 48 px target. Keyboard support (arrow keys/roving tabindex) comes from Radix.
- **Alternatives considered**: bigger slider thumbs (rejected: drag precision remains the failure mode; WCAG target-size applies to the whole track interaction); steppers with +/- buttons (rejected: 10-tap worst case to reach a value; slower in the field).

## R7. Target-size verification

- **Decision**: New Playwright spec `frontend/e2e/target-size.spec.ts` sweeping key coach screens (session detail incl. rubric, results table, dashboard, lists) and asserting `boundingBox()` ≥ 48×48 for interactive elements (`a`, `button`, `[role=button]`, inputs), with a documented allowlist for inline text links.
- **Rationale**: jest-axe in jsdom structurally cannot measure rendered size (no layout engine) — proven by the audit: axe-clean components with 20 px thumbs. Playwright infra already exists (`@playwright/test` 1.50, `playwright.config.ts`, 7 specs, preinstalled Chromium), so this is an additive spec, not new infrastructure.
- **Alternatives considered**: unit-level `getComputedStyle` checks (rejected: jsdom lies about layout); manual device audits only (rejected: not a regression gate).

## R8. Batched newsletter status (N+1 fix)

- **Decision**: One read-only backend endpoint returning, for a given `year`/`month`, every active athlete's newsletter status in a single response (contract: `contracts/newsletter-status-summary.md`); frontend hook `useNewsletterStatusSummary(year, month)` replaces the per-athlete `useNewsletterForAthlete` fan-out on the dashboard page; per-athlete detail queries remain for the detail view. Also add the missing pending affordance (spinner + "Generando…") to the per-athlete generate button.
- **Rationale**: Constitution IV forbids N+1 list patterns; a 20–30-athlete club currently fires 20–30 requests on a 3G connection at cold start. The aggregate is a trivial grouped query over existing data — no schema change.
- **Alternatives considered**: client-side request batching/parallel limits (rejected: still O(N) requests); GraphQL-style batching layer (rejected: stack discipline).

## R9. Role-aware athlete links (admin dead-click fix)

- **Decision**: Shared `AthleteLink` component: renders a router link for roles allowed on `/athletes/:id` (coach), and plain styled text (`<span>`) otherwise; adopted at the four broken call sites (`MeasurementAlerts` ×2, competitions `AthletesTab`, `InsightsTab`, `AthleteNewsletterDetailPage`). RBAC itself is unchanged (program assumption: do not expand admin access).
- **Rationale**: Fixes the silent `ProtectedRoute` bounce at the source with one testable component; keeps the decision reversible (if admin is later granted access, `AthleteLink` gains a role).
- **Alternatives considered**: admitting admin to the athlete route (rejected: permission expansion out of scope); toast-on-redirect in `ProtectedRoute` (rejected: still a dead end, just a narrated one).

## R10. Wizard focus management

- **Decision**: Shared behavior in the unified `Stepper`/wizard shell: on step change, move focus to the new step's `<h2>` (`tabIndex={-1}` + `.focus()`), with the heading announced via its natural semantics; validation-failure focus behavior (existing `shouldFocus`) is preserved. Applied to `SessionWizard` and `ImportWizard`; `OnboardingStepper` is folded as a `variant` where practical.
- **Rationale**: Standard accessible-wizard pattern; fixes both wizards with one shared implementation (rule of three: three steppers exist today).
- **Alternatives considered**: `aria-live` region announcing step names (kept as complement where heading focus is disruptive, e.g., inside dialogs).

## R11. Remaining small fixes (grounded in audit evidence)

- Calendar day-click: fill the empty `handleDateClick` with `navigate('/calendar/events/new?date=' + dateStr)` — the receiving `EventFormPage` already reads `?date=`.
- Season derivation: replace `CURRENT_SEASON = 2026` with a `currentSeason()` helper (club timezone) in `lib/datetime.ts`.
- Sunlight contrast: adopt the existing `--color-text-disclaimer` token for coach-facing small text (~35 files with 10–11 px `text-mid-gray`), starting with rubric labels, table timestamps, and form hints.
- `MediaUploadZone`: add `capture="environment"` to the file input.
- Eager/lazy + Suspense: introduce one route-level Suspense wrapper (replaces 21 identical inline fallbacks); leave the eager/lazy split rebalancing to 029/030 where routes move anyway.
- Folder hygiene groundwork: absorb `components/common/` into `components/shared/`; move `PHVBadge` to `components/athletes/` (5 imports).
