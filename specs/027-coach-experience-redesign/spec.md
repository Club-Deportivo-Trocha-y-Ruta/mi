# Feature Specification: Coach Experience Redesign

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "for all phases" — i.e., specify the complete coach UX/UI redesign program proposed in `docs/17-coach-ux-redesign/proposal.md` (all phases, 0–6). This spec covers the whole program as one feature; the phases become prioritized, independently deliverable user stories, and the technical sequencing lives in the implementation plan.

> **Source material**: `docs/17-coach-ux-redesign/proposal.md` (§1–§13) and the five evidence reports in `docs/17-coach-ux-redesign/agent-reports/`. Every current-state claim referenced below is documented there with file-level evidence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Everyday reliability in the field (Priority: P1)

The coach — usually on a tablet, outdoors, with gloves and an intermittent connection — can operate every daily control without precision-tapping, recovers from any network failure without reloading, is never dropped into a dead end by a broken link, and always sees what the system is doing while it works. The admin never clicks a visible link that silently bounces them back to where they started.

**Why this priority**: These are defects and friction in flows the coach runs several times per week (attendance, effort rubric, session management). Fixing them delivers value even if nothing else in this program ships, and every later story builds on this reliability baseline.

**Independent Test**: On a tablet (or touch emulation), complete a field-day flow — find today's session, record attendance, fill the effort rubric, upload a photo, cancel a session with parent notification — with gloves-realistic touch accuracy, on a throttled connection, and as both coach and admin roles. No dead ends, no silent failures, no control under 48×48 px.

**Acceptance Scenarios**:

1. **Given** an athlete row in the effort rubric, **When** the coach records effort/attitude/technique/RPE, **Then** each value is set by tapping discrete step controls (not dragging a slider), every step target is at least 48×48 px, and the saved state is visibly confirmed per row.
2. **Given** any list or detail view whose data fails to load, **When** the failure occurs, **Then** the coach sees a friendly message with a visible retry action that reloads only that view (no full page reload, no raw error text).
3. **Given** an admin viewing the dashboard alerts, a competition's athletes/insights views, or a newsletter detail, **When** they see an athlete's name, **Then** it is either a working link or plain non-interactive text — never a link that silently redirects them away.
4. **Given** any destructive action (delete athlete, delete media, cancel session), **When** the confirmation appears, **Then** it is one consistent dialog style across the app: initial focus lands on the safe option, Escape dismisses it, and focus returns to the triggering control.
5. **Given** a long-running generation (monthly report, newsletter, AI analysis), **When** it is in flight, **Then** the triggering control shows an in-progress state, and completion or failure is confirmed with a brief non-blocking notification, consistently across the app.
6. **Given** the club calendar, **When** the coach taps an empty day, **Then** event creation starts with that date already filled in.
7. **Given** a multi-step flow (session creation, results import), **When** the coach advances a step, **Then** the new step's heading receives focus and is announced to assistive technology.
8. **Given** the monthly newsletter overview on a slow connection, **When** it opens, **Then** the status of all athletes loads as one summary (no per-athlete request waterfall) within the project's page-load budget.

---

### User Story 2 - Find everything from a task-shaped navigation (Priority: P1)

The coach reaches every feature of the product from a navigation organized around how they actually work — daily training, competitions, athletes, families, exercise libraries — instead of a flat 12-item list, and nothing the club built is unreachable. On phone/tablet widths, the most-used areas are one thumb-tap away.

**Why this priority**: Nine fully built features are currently unreachable from any navigation, and the flat list makes every new module more expensive to find. Discoverability is the single highest-leverage structural fix; it also makes the removals in Story 3 safe to communicate.

**Independent Test**: Starting from login as coach, reach every retained feature of the product using only visible navigation (no typed URLs). Verify grouped sidebar on desktop, bottom bar + overflow on mobile widths, and that the most-used screens still take a single interaction.

**Acceptance Scenarios**:

1. **Given** the authenticated coach app, **When** the coach opens the navigation, **Then** features are grouped into at most 7 task-oriented areas (proposed: Inicio, Entrenamiento, Competencias, Atletas, Familias, Biblioteca) and every retained screen is reachable through them.
2. **Given** the grouped navigation, **When** the coach selects a top-level area, **Then** they land directly on that area's default working view (no intermediate hub page), preserving today's one-interaction access to calendar, sessions, athletes, and competitions.
3. **Given** any screen, **When** the coach uses the global quick-create control, **Then** they can start a new session, competition, calendar event, or athlete (respecting role permissions) without first navigating to that module.
4. **Given** a phone or tablet width, **When** the coach navigates, **Then** the four most-used areas are available in a persistent bottom bar and the remaining areas, profile, and sign-out are in an overflow menu.
5. **Given** the account controls, **When** any user opens the user menu, **Then** profile, sign-out and (for admins) system diagnostics are grouped there and no longer occupy main-navigation space.
6. **Given** previously bookmarked or externally shared addresses, **When** they are opened after the redesign, **Then** they still resolve (no address changes; the existing legacy-redirect policy is preserved).
7. **Given** the whole app, **When** any feature is named, **Then** one term is used per concept everywhere: the funder-facing club report ("Informes del club"), the parent-facing newsletter ("Boletines"), and the AI analysis ("Insights IA" as the noun, "Analizar con IA" as the action).
8. **Given** the AI session assistant, **When** the coach starts creating a session, **Then** the assistant is visibly offered next to manual creation (it is currently unreachable).

---

### User Story 3 - A leaner product with nothing half-built (Priority: P2)

The coach uses a product where every visible feature is finished and reachable, duplicated screens are gone, and per-athlete information (technique progress, strength progress, wellbeing) is consolidated on the athlete's profile instead of scattered across disconnected screens.

**Why this priority**: Confirmed dead or duplicated surface (~3,500 lines, 6–8 screens) costs maintenance, bundle size, and coherence. Removing it before redesigning reduces the surface every later story must cover. It depends on Story 2's navigation only for communicating the new locations.

**Independent Test**: Audit the app after this story: no screen is unreachable, no two screens present the same information under different names, the athlete profile shows technique/strength progress, and the removed screens are gone without any user-visible capability loss (beyond the explicitly approved removals).

**Acceptance Scenarios**:

1. **Given** the duplicated cross-race AI analysis screens (hub, club view, per-athlete view), **When** the cleanup ships, **Then** they are removed, the equivalent reachable views (per-competition insights, per-athlete analysis) remain the single home of that content, and the unique season panorama remains available with a visible entry from Competencias.
2. **Given** the athlete profile, **When** the coach reviews an athlete, **Then** technique-skill progress and strength progress are available there under one consolidated "Progreso" area (profile sections do not exceed 7), and the competitive-anxiety view is reachable from the profile with the athlete preselected.
3. **Given** the standalone technique session builder (which today creates a duplicate second session), **When** the cleanup ships, **Then** it is removed and its capability is provided by attaching technique content to an existing session (Story 5).
4. **Given** the standalone interval-template screen (unreachable today), **When** the cleanup ships, **Then** it is removed and template browsing/attaching remains available where it is actually used — inside session planning.
5. **Given** the gymkhana circuit composer (fully built but unreachable from any navigation), **When** the cleanup ships, **Then** it is removed together with its heavy drawing dependencies (decision D1: delete); the technique library's existing circuit diagrams are unaffected and no currently reachable capability is lost.
6. **Given** the competitive-anxiety interpretation capability (fully built server-side, never wired into any screen), **When** this story ships, **Then** the coach can request an on-demand interpretation of an athlete's questionnaire results from the individual anxiety view (decision D2: wire it in) — coach-only, guardian-consent-gated, baseline-anchored, and free of diagnostic language, exactly as the constitution's Principle V requires.
7. **Given** any removal in this story, **When** it ships, **Then** no user-visible capability is lost other than those explicitly approved above, and external links keep resolving per the legacy-redirect policy.

---

### User Story 4 - A home screen that answers "what's next and what's pending" (Priority: P2)

When the coach opens the app, the first screen tells them what matters today: the next planned session, the next race with days remaining and preparation guidance, and a short list of pending work (results to import, activities to link, newsletters due, consents missing, stale AI analyses) — each item one tap from where it gets resolved.

**Why this priority**: The current landing shows three static counters with no links; every real task starts with manual navigation. A mission-control home compounds the value of Stories 1–3 by putting the day's work first, but it can ship independently after them.

**Independent Test**: Log in as coach with seeded data covering each state (session today, race within taper window, pending imports/newsletters/consents) and verify each tile shows the right content, links to the right place, and shows a helpful empty state when there is nothing pending.

**Acceptance Scenarios**:

1. **Given** at least one future planned session, **When** the coach lands, **Then** the next session's name, relative day ("hoy", "en 2 días") and place are shown, tapping opens it, and with no planned session an inviting shortcut to plan one appears.
2. **Given** the competition calendar, **When** the coach lands, **Then** the next race shows days remaining and its preparation guidance by race class (A: full taper 5–7 days; B: mini-taper 3–4 days; C: none), with urgency visually distinguished.
3. **Given** pending work exists, **When** the coach lands, **Then** a pending-work list shows counts for: race results to import, external activities to link, newsletters due this month, missing/expired consents, and outdated AI analyses — each row linking to the screen where it is resolved. (Consent and stale-analysis counts may arrive in a second increment; the list must degrade gracefully while absent.)
4. **Given** the existing measurement alerts (overdue anthropometry, growth-spurt flags), **When** the home is redesigned, **Then** they remain present and unchanged in behavior.
5. **Given** the weekly plan, **When** aggregate data is available, **Then** the home shows planned weekly load per age band against the club's "weekly hours ≤ athlete age" cap, visibly warning as the cap is approached.
6. **Given** an admin, **When** they land, **Then** the home shows only content their role can open, with no links into coach-only screens.
7. **Given** any date, **When** season-scoped content is shown anywhere, **Then** the season derives from the current date (no hardcoded year that goes stale in January).

---

### User Story 5 - One way to build a complete session (Priority: P2)

The coach plans a complete training session — technique exercises, strength blocks, interval structure — from the session itself, through one consistent attach interaction, and works with a session screen organized in clear sections instead of one very long scroll. Finding today's session takes one tap.

**Why this priority**: "Attach training content" is the core weekly planning act and today follows three contradictory patterns (inline for intervals; build-elsewhere-and-search for strength; a duplicate-session creator for technique). High value, but it depends on Story 3's removals to avoid redesigning a screen that is being deleted.

**Independent Test**: Create a session, then from that session attach one technique exercise set, one strength block, and one interval structure — all through the same pattern, without losing the session context — and verify the session screen presents summary, attendance, plan, and media as distinct sections.

**Acceptance Scenarios**:

1. **Given** an existing session, **When** the coach adds technique exercises, strength blocks, or an interval structure, **Then** all three follow the same interaction pattern, initiated from the session, without creating a second session.
2. **Given** a build screen opened from a session, **When** it opens, **Then** that session is already preselected as the target.
3. **Given** the session screen, **When** the coach works on it, **Then** its content is organized into at most four sections (summary, attendance, plan, media) with the active section preserved on refresh and back-navigation.
4. **Given** the sessions list, **When** today has a session, **Then** a "hoy" shortcut surfaces it and today's row is visually distinct.

---

### User Story 6 - One coherent visual language (Priority: P3)

The coach experiences one product, not six: a single accent color, one consistent meaning for status colors everywhere (green = success, amber = attention, red = error/blocking, neutral gray = informational), charts that follow one style, one heading typography, and AI features that share one name, one action verb, one icon, and one freshness vocabulary.

**Why this priority**: Visual coherence multiplies trust and reduces learning cost, but it does not block any workflow; it lands best after the structural stories.

**Independent Test**: Visual audit across all coach modules: status colors carry a single meaning (including in charts), the four newer modules (técnica, fuerza, intervalos, ansiedad) are indistinguishable in style from the rest, headings render in one settled typography, and every AI entry point shares the same naming/icon/freshness presentation.

**Acceptance Scenarios**:

1. **Given** any status presentation (sync state, session state, consent state, analysis freshness, newsletter state), **When** it renders anywhere in the app, **Then** it uses the shared status vocabulary and colors with an icon or label (never color alone), per the constitution's semantics.
2. **Given** the race-class labels A/B/C, **When** they are colored, **Then** they read as an ordered intensity scale (taper effort), never as good/bad status colors.
3. **Given** the performance charts, **When** they render, **Then** grids are solid hairlines, the athlete's own series uses the product accent, best/worst references use the status vocabulary, special events (championship) are marked on the data point itself, and small samples continue to fall back to a table.
4. **Given** headings across the app, **When** they render, **Then** they use the documented brand display font, now actually shipped and self-hosted (decision D3), applied through one central definition that replaces the 115 scattered per-component references.
5. **Given** the four newer modules, **When** the pass completes, **Then** their text colors, headings, and components match the rest of the app.
6. **Given** any AI feature, **When** the coach encounters it, **Then** it is named "Insights IA", launched with "Analizar con IA", marked with one consistent icon, shows the same freshness states everywhere, presents the same in-progress run view at every entry point, and communicates expected wait and remaining monthly AI budget before launch rather than only failing afterward.

---

### User Story 7 - Comfort and power polish (Priority: P4 — optional, capacity permitting)

The coach who plans at a desk gets keyboard shortcuts and (if later justified) a jump-anywhere command palette; evening field use gets a dark appearance; low-risk actions feel instant; the race chat clearly states that conversations are not saved; and the media uploader can open the camera directly on tablets.

**Why this priority**: Genuine quality-of-life improvements with no structural dependency; explicitly deferrable without harming the program's outcome.

**Independent Test**: Each polish item is independently verifiable on its own (dark appearance toggles with the device preference; shortcuts navigate; camera opens directly; chat shows its non-persistence notice).

**Acceptance Scenarios**:

1. **Given** a device set to dark appearance, **When** the coach uses the app, **Then** all coach surfaces render a legible dark theme meeting the same contrast bars.
2. **Given** the race chat, **When** the coach opens it, **Then** a brief notice explains the conversation is not saved (privacy-by-default), so its disappearance on reload is expected.
3. **Given** a tablet, **When** the coach adds session media, **Then** they can open the camera directly rather than only the gallery picker.

---

### Edge Cases

- **Connection loss mid-action**: any failed save keeps the coach's input, shows the retry affordance, and never duplicates records on retry (attendance autosave's per-row retry is the reference behavior).
- **Server cold start (~50 s)**: the existing "server waking" notice remains; new home tiles and pending-work rows must show skeletons/degraded states rather than errors during warm-up.
- **Role edges**: an admin (who cannot open athlete profiles) sees non-interactive athlete names wherever coaches see links; parent-facing surfaces are untouched by this program.
- **Empty club states**: no sessions planned, no upcoming race (season over), zero pending work — the home and lists must show purposeful empty states with a next action, not blank space.
- **Season rollover**: on January 1 all season-scoped views must follow the new year automatically.
- **Old links**: bookmarks and externally shared links (parent emails, Spond) to any pre-redesign address must keep resolving under the preserved redirect policy.
- **Consent-gated features**: the anxiety module must remain exactly as reachable as today for consented athletes after its navigation demotion (visual priority may drop; reachability may not).
- **Concurrent AI limits**: when the monthly AI budget is exhausted or concurrency capped, launch controls must communicate it *before* launch and still handle the failure gracefully after.
- **Very large fields (10–15+ riders)** in chart reference lines: labels must not overlap into unreadability; degrade to fewer labels rather than clutter.

## Requirements *(mandatory)*

### Functional Requirements

**Navigation & discoverability (Story 2)**

- **FR-001**: The coach navigation MUST group all features into at most 7 task-oriented areas, and every retained screen MUST be reachable through visible navigation (today: 9 unreachable screens).
- **FR-002**: Selecting a top-level area MUST land directly on that area's default working view; the most-used screens (calendar, sessions, athletes, competitions) MUST remain reachable in one interaction.
- **FR-003**: Profile, sign-out, and admin-only diagnostics MUST move to a user menu; a global quick-create control MUST offer new session / competition / event / athlete anywhere, respecting roles.
- **FR-004**: On phone/tablet widths, the four most-used areas MUST be reachable from a persistent bottom bar, with remaining destinations in an overflow menu.
- **FR-005**: No screen address may change; the existing legacy-redirect policy MUST be preserved.
- **FR-006**: Naming MUST be unified: "Informes del club" (funder report), "Boletines" (parent newsletters), "Insights IA"/"Analizar con IA" (AI analysis noun/verb) — one term per concept across navigation, pages, and actions.
- **FR-007**: The AI session assistant MUST be offered visibly wherever session creation starts.

**Reliability & field usability (Story 1)**

- **FR-008**: No visible control may lead to a silent redirect; links to screens the current role cannot open MUST be hidden or rendered as plain text.
- **FR-009**: Every data-loading view MUST offer a visible retry on failure; raw technical error text MUST never be shown.
- **FR-010**: All destructive actions MUST use one consistent confirmation dialog: safe option focused by default, Escape dismisses, focus returns to the trigger. Browser-native confirmation prompts MUST NOT be used.
- **FR-011**: All interactive touch controls on coach surfaces MUST be at least 48×48 px; the effort rubric MUST use discrete step controls instead of drag sliders.
- **FR-012**: Small/secondary text on coach surfaces MUST meet the project's stricter sunlight-readability contrast bar (the existing high-contrast token, today applied only in the parent portal).
- **FR-013**: Long-running operations MUST show in-progress feedback on the triggering control, and outcomes MUST be confirmed via brief, non-blocking notifications, consistent app-wide.
- **FR-014**: Multi-step flows MUST move focus to and announce each new step for assistive technology.
- **FR-015**: Tapping an empty calendar day MUST start event creation with that date prefilled.
- **FR-016**: The monthly newsletter overview MUST load all athletes' statuses as one summary rather than one lookup per athlete, staying within the project's page-load budgets on slow connections.
- **FR-017**: Season-scoped screens MUST derive the season from the current date; hardcoded years are not acceptable.

**Subtraction (Story 3)**

- **FR-018**: The duplicated cross-race AI screens (hub, club view, per-athlete view) MUST be removed; the season panorama MUST remain, reachable from Competencias; the per-competition and per-athlete analysis views remain the single homes of that content.
- **FR-019**: The standalone technique session builder MUST be removed once its capability is available as attach-to-session (FR-023); the standalone interval-template screen MUST be removed (template use remains inside session planning); the superseded upload widget and duplicated confirmation/label helpers MUST be consolidated.
- **FR-020**: The gymkhana circuit composer MUST be removed (decision D1), including its drawing-specific dependencies; the technique library's existing circuit diagrams remain unchanged.
- **FR-021**: The anxiety on-demand interpretation MUST be wired into the individual anxiety view (decision D2), preserving every Principle V safeguard: coach-only access, guardian-consent gate, baseline-anchored wording, no diagnostic labels, and the rule-based fallback when the AI service is unavailable. This is presentation wiring of an existing, tested capability — no server-side changes.
- **FR-022**: The athlete profile MUST consolidate technique and strength progress under one "Progreso" area (athlete profile sections MUST NOT exceed 7) and MUST link to the athlete's wellbeing (anxiety) view with the athlete preselected. Removals MUST NOT reduce reachable user capability beyond those explicitly approved.

**Session building (Story 5)**

- **FR-023**: Technique exercises, strength blocks, and interval structures MUST all attach to an existing session through the same interaction pattern, initiated from the session, without creating duplicate sessions; build screens opened from a session MUST preselect it.
- **FR-024**: The session screen MUST be organized into at most four sections (summary, attendance, plan, media), preserving the active section across refresh/back.
- **FR-025**: The sessions list MUST offer a "hoy" shortcut and visually distinguish today's session.

**Coach home (Story 4)**

- **FR-026**: The coach landing MUST show: next planned session (with create shortcut when none), next race with days remaining and A/B/C preparation guidance, and the existing measurement alerts unchanged.
- **FR-027**: The landing MUST show a pending-work list — results to import, activities to link, newsletters due, missing consents, stale AI analyses — each row linking to its resolution screen and degrading gracefully while a count is unavailable.
- **FR-028**: When aggregate data is available, the landing MUST show planned weekly load per age band against the "weekly hours ≤ age" cap with a visible warning as the cap approaches.
- **FR-029**: The admin landing variant MUST show only admin-permitted content with no links into coach-only screens.

**Visual coherence & AI identity (Story 6)**

- **FR-030**: One accent color and one status vocabulary (green success / amber attention / red error / neutral informational, always icon+label, never color alone) MUST apply across all coach surfaces, including charts; A/B/C race classes MUST read as an ordered intensity scale, not status.
- **FR-031**: Charts MUST follow one style: solid hairline grids, own-athlete series in the accent, best/worst references in status colors, championship points marked on the data point itself, small-sample table fallback preserved, and reference-line labels capped before they overlap.
- **FR-032**: The documented brand display font MUST be shipped (self-hosted, no third-party font service) and applied to headings through one central definition (decision D3); scattered per-component font references MUST be removed. The design-system document MUST be updated to match shipped reality.
- **FR-033**: The técnica, fuerza, intervalos, and ansiedad modules MUST adopt the same visual language (text colors, headings, components) as the rest of the app.
- **FR-034**: AI features MUST present one identity: one name, one action verb, one icon, one freshness vocabulary (none / fresh / outdated with manual re-run), the same in-progress run view at every entry point, and expected wait plus remaining monthly AI budget communicated before launch.

**Optional polish (Story 7)**

- **FR-035** *(optional)*: All coach surfaces MUST support a dark appearance honoring the device preference at the same contrast bars.
- **FR-036** *(optional)*: The race chat MUST state that conversations are not saved; media capture MUST offer direct camera access on tablets; keyboard shortcuts MAY be added for desktop planning. A global command palette is explicitly deferred unless later justified.

### Key Entities

No new domain data is introduced. The coach home consumes read-only aggregates of existing records (sessions, race events, activities, newsletters, consents, analyses); all removals are of duplicated or unreachable presentation surface, never of stored data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of retained features are reachable through visible navigation — 0 unreachable screens (today: 9).
- **SC-002**: Top-level navigation entries reduced from 12 to at most 7, with account/diagnostic actions relocated to a user menu.
- **SC-003**: The coach reaches today's (or next) session in at most 2 interactions from landing (today: 4+ plus a visual scan of a month-long list).
- **SC-004**: 0 visible links lead to silent redirects for any role (today: 4 admin-facing surfaces do).
- **SC-005**: 100% of data-loading views offer a retry affordance on failure (today: the four highest-traffic list pages have none).
- **SC-006**: 100% of interactive touch controls on coach surfaces measure at least 48×48 px, verified on a real rendering engine (today's worst: 20×20 px on the most-used field control).
- **SC-007**: The product surface shrinks by at least 6 screens and roughly 3,500 lines with zero loss of reachable user capability beyond the explicitly approved removals.
- **SC-008**: One term per concept: exactly one name each for the club report, the parent newsletter, and the AI analysis across navigation, page titles, and actions (today: 3, 2, and 5 variants respectively).
- **SC-009**: On landing, the coach can answer "what's next and what's pending" — next session, next race with preparation guidance, pending-work counts — without navigating (today: none of this is visible on landing).
- **SC-010**: Status colors carry a single meaning across 100% of coach surfaces including charts, always paired with an icon or label.
- **SC-011**: All three session-content types (technique, strength, intervals) attach from the session screen through one pattern in at most 3 interactions each (today: one of the three cannot attach at all).
- **SC-012**: Landing and athlete-list pages keep meeting the project's load budget on a mid-tier Android over simulated 3G (≤ 2.5 s to main content) after the redesign; the newsletter overview drops from ~N requests (one per athlete) to a constant number regardless of club size.

## Assumptions

- **Resolved decisions** (`docs/17-coach-ux-redesign/proposal.md` §12, confirmed with the coach on 2026-07-11): D1 — delete the gymkhana composer; D2 — wire the anxiety interpretation into the individual view; D3 — ship the brand display font; D4 — remove the standalone technique builder in favor of attach-from-session; D5 — defer the command palette (grouped navigation + quick-create address discoverability first); D6 — remove the duplicated insights screens, keeping only the unique season panorama, relinked from Competencias.
- **Scope boundary**: the parent portal is out of scope except where it shares components; backend work is limited to small read-only aggregates for the home (weekly load, consent and stale-analysis counts) and one batched newsletter-status summary; wiring the anxiety interpretation is presentation-only (its service already exists); no changes to AI pipelines, scoring, ingestion, or stored data.
- **RBAC is unchanged**: the admin dead-click fix renders non-interactive text for admin rather than expanding admin access to athlete profiles.
- **No address changes**: all existing URLs continue to resolve; the documented legacy-redirect policy (301s pending their planned 410 transition) is preserved.
- **Language**: all product copy introduced or renamed by this program is in español neutro (Colombia); this spec and its plan are in English per the constitution's language policy.
- **Constitution alignment**: 48×48 px touch targets, the fixed status-color semantics, WCAG 2.1 AA, and the performance budgets of Principle IV are treated as hard acceptance bars, not aspirations; the anxiety module's Principle V safeguards (consent gating, coach-only access, no auto-messaging) are untouched by its navigation demotion.
- **Delivery mapping (informative)**: Stories map to the proposal's phases — Story 1 ≈ phases 0–1 (user-visible half), Story 2 ≈ phase 3, Story 3 ≈ phase 2, Story 4 ≈ phase 4, Story 5 ≈ phase 5, Story 6 ≈ phases 1+5 (visual half), Story 7 ≈ phase 6. The implementation plan owns technical sequencing (foundation work precedes the stories that consume it) and may deliver stories across several releases; each story is independently shippable.
