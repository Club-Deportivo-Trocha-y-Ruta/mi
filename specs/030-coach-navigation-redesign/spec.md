# Feature Specification: Coach Navigation Redesign

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 3 of 6. Covers phase 3 (navigation regroup) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §4; evidence: `docs/17-coach-ux-redesign/agent-reports/03-information-architecture.md`; program spec: `specs/027-coach-experience-redesign/spec.md`, Story 2).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A navigation shaped like the coach's work (Priority: P1)

The coach finds every feature inside at most 7 task-oriented areas — Inicio, Entrenamiento, Competencias, Atletas, Familias, Biblioteca — instead of scanning a flat 12-item list, and selecting an area lands directly on its default working view with no interstitial hub.

**Why this priority**: The flat list mixes daily field tools with monthly admin and specialized libraries at equal weight, and it grows linearly with every new module. Grouping is the structural fix that makes the whole product legible; everything else in this feature hangs off it.

**Independent Test**: As coach, starting from login, reach every retained screen using only visible navigation; verify at most 7 top-level areas, that each area opens its default view in one interaction, and that the group containing the current screen is visually indicated.

**Acceptance Scenarios**:

1. **Given** the authenticated coach app, **When** the navigation renders, **Then** it presents at most 7 task-oriented areas and every retained screen is reachable through them (0 orphans).
2. **Given** a top-level area, **When** the coach selects it, **Then** they land directly on its default working view (Entrenamiento → calendar; Competencias → competitions list; Atletas → athletes list; Familias → parents list; Biblioteca → technique catalog) — today's one-interaction access to the most-used screens is preserved.
3. **Given** sibling views within an area (e.g., Calendario ↔ Sesiones ↔ Actividades), **When** the coach switches between them, **Then** a consistent secondary-navigation pattern is used and the active view is preserved on refresh and back-navigation.
4. **Given** the current screen, **When** the navigation renders, **Then** the containing area is visibly highlighted and expanded.
5. **Given** an admin, **When** the navigation renders, **Then** coach-only areas and entries (Atletas, Padres) are absent, and everything shown is openable by admin.

---

### User Story 2 - Previously hidden tools become visible (Priority: P1)

The coach discovers, through normal navigation, the tools that were fully built but invisible: the AI session assistant next to manual session creation, the season panorama inside Competencias, and strength-block building from the strength library.

**Why this priority**: Surfacing finished work is the highest value-to-effort ratio in the whole program. It depends on the subtraction feature (029) having settled *which* screens survive.

**Independent Test**: Without typing any URL, reach: the AI session assistant from the sessions area, the season panorama from Competencias, and strength-block creation from Biblioteca → Fuerza.

**Acceptance Scenarios**:

1. **Given** session creation, **When** the coach starts a new session, **Then** creating with the AI assistant is offered visibly next to manual creation.
2. **Given** the Competencias area, **When** the coach explores it, **Then** the season panorama ("Panorama de temporada") is one visible interaction away.
3. **Given** Biblioteca → Fuerza, **When** the coach browses the catalog, **Then** building a strength block is offered there (today it is reachable only from inside a session).

---

### User Story 3 - Thumb-first navigation on phone and tablet (Priority: P2)

On phone/tablet widths the four most-used areas — Inicio, Entrenamiento, Competencias, Atletas — sit in a persistent bottom bar within thumb reach, and everything else (Familias, Biblioteca, profile, sign-out, admin diagnostics) lives in a "Más" overflow.

**Why this priority**: The coach's primary field device is a tablet; today's mobile navigation is a hamburger drawer replicating the desktop list, requiring two hands and extra taps for the most frequent mid-session jumps.

**Independent Test**: On a phone/tablet viewport, verify the bottom bar shows the four areas plus "Más"; every remaining destination is reachable through the overflow; the bar never overlaps content or the on-screen keyboard.

**Acceptance Scenarios**:

1. **Given** a phone or tablet width, **When** the coach navigates, **Then** a persistent bottom bar offers Inicio, Entrenamiento, Competencias, Atletas, and "Más"; the active area is indicated.
2. **Given** the "Más" overflow, **When** opened, **Then** it lists the remaining areas plus profile, sign-out, and (for admin) diagnostics; all its targets meet the 48×48 px rule.
3. **Given** an admin on mobile, **When** the bar renders, **Then** the coach-only Atletas slot is replaced by an area the admin can open.
4. **Given** an open on-screen keyboard or a scrolling list, **When** the coach works, **Then** the bottom bar never obscures inputs or trap content behind it.

---

### User Story 4 - Account actions and quick creation from anywhere (Priority: P2)

Profile, sign-out, and admin diagnostics live in a user menu instead of occupying navigation space, and a global quick-create control starts a new session, competition, calendar event, or athlete from any screen, respecting roles.

**Why this priority**: Creation today requires first navigating to each module's list page; account actions consume prime navigation space. Both are small, high-frequency wins that complete the new shell.

**Independent Test**: From several unrelated screens, create each of the four record types via quick-create (role-permitting); open the user menu and reach profile, sign-out, and (as admin) diagnostics.

**Acceptance Scenarios**:

1. **Given** any screen, **When** the coach uses quick-create, **Then** they can start a new session, competition, calendar event, or athlete without first navigating to that module; options the role cannot use are absent.
2. **Given** the user menu, **When** any user opens it, **Then** profile and sign-out are there; diagnostics appears for admin only; none of these occupy main navigation.
3. **Given** the whole app after this feature, **When** any concept is named, **Then** naming is unified: "Informes del club" (funder report), "Boletines" (parent newsletters), "Insights IA"/"Analizar con IA" (AI analysis noun/verb) — one term per concept in navigation, page titles, and actions.

---

### Edge Cases

- **Bookmarks and external links**: no screen address changes; every existing URL, including legacy redirects, resolves exactly as before — the regroup is presentation-only.
- **Deep entry**: opening a deep link (e.g., a specific competition) must highlight and expand the correct navigation area.
- **Role switch mid-session**: signing out and in as a different role must rebuild the navigation without stale entries.
- **Narrow desktop windows**: between mobile and desktop breakpoints the navigation must remain fully operable — no dead zone where neither pattern renders.
- **Keyboard and assistive tech**: groups, overflow, user menu, and quick-create must be fully keyboard-operable with correct roles/labels; the "skip to content" affordance must survive the shell change.
- **Anxiety module demotion**: moving "Ansiedad competitiva" under Atletas changes visual priority only — reachability for consented use is identical (constitution Principle V unaffected).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Coach navigation MUST group all features into at most 7 task-oriented areas (Inicio, Entrenamiento, Competencias, Atletas, Familias, Biblioteca), with every retained screen reachable through visible navigation.
- **FR-002**: Selecting an area MUST land directly on its default working view; the most-used screens (calendar, sessions, athletes, competitions) MUST remain one interaction from anywhere in the shell.
- **FR-003**: Sibling views within an area MUST use one consistent secondary-navigation pattern, distinct from per-record tabs, preserving the active view across refresh and back-navigation.
- **FR-004**: The area containing the current screen MUST be visually indicated and expanded; role-inaccessible areas and entries MUST be absent for that role.
- **FR-005**: On phone/tablet widths a persistent bottom bar MUST offer Inicio, Entrenamiento, Competencias, Atletas, and a "Más" overflow containing all remaining destinations, profile, sign-out, and admin diagnostics; the bar MUST never obscure content or inputs.
- **FR-006**: Profile, sign-out, and admin-only diagnostics MUST move into a user menu; a global quick-create control MUST offer new session / competition / calendar event / athlete anywhere, filtered by role.
- **FR-007**: The AI session assistant MUST be visibly offered wherever session creation starts; the season panorama MUST be reachable from Competencias; strength-block building MUST be reachable from Biblioteca → Fuerza.
- **FR-008**: Naming MUST be unified across navigation, page titles, and actions: "Informes del club", "Boletines", "Insights IA" (noun) / "Analizar con IA" (verb) — exactly one term per concept.
- **FR-009**: No screen address may change; the legacy-redirect policy MUST be preserved; the navigation regroup MUST be expressible as presentation change only (no permission or data changes).
- **FR-010**: The navigation shell MUST be fully keyboard-operable and correctly announced by assistive technology, including the skip-to-content affordance.

### Key Entities

No new domain data. Navigation structure is presentation over existing screens and roles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Top-level navigation entries drop from 12 to at most 7, with account/diagnostic actions relocated to the user menu.
- **SC-002**: 100% of retained screens are reachable through visible navigation; 0 orphaned screens remain.
- **SC-003**: The most-used screens (calendar, sessions, athletes, competitions) remain reachable in 1 interaction from the shell — no regression from today.
- **SC-004**: On mobile widths, the four most-used areas are reachable with one thumb tap; every other destination in at most 3 taps.
- **SC-005**: Creating any of the four record types from an unrelated screen takes at most 2 interactions via quick-create (today: 3+ including list-page navigation).
- **SC-006**: Exactly one name per concept for the club report, parent newsletter, and AI analysis across the app (today: 3, 2, and 5 variants).
- **SC-007**: 0 broken bookmarks: 100% of pre-redesign URLs resolve identically after the regroup.
- **SC-008**: A first-time observer (e.g., the club admin) can locate any named feature in under 30 seconds using navigation alone.

## Assumptions

- **Program context**: feature 3 of 6 (specs 028–033), program Story 2, proposal §4. Recommended after 029 so the new navigation only presents surviving screens; independently shippable regardless (it would simply keep entries for screens 029 later removes).
- **Area contents** follow the proposal's sitemap: Entrenamiento = Calendario (default), Sesiones, Actividades; Competencias = Válidas (default), Sin enlazar, Panorama de temporada; Atletas = Todos (default), Ansiedad competitiva; Familias = Padres (coach-only), Boletines, Informes del club (with its settings page demoted to a settings affordance); Biblioteca = Técnica (default), Fuerza. Inicio is the landing (redesigned separately in 031).
- **Decision D5 (resolved 2026-07-11)**: no command palette in this feature — grouped navigation plus quick-create addresses discoverability; revisit only if later justified.
- **Roles unchanged**: the regroup adds no permissions; admin sees the same screens as today, minus coach-only entries, plus the dead-click fix from 028.
- **Language**: all new navigation labels are in español neutro (Colombia).
- **Scope boundary**: no landing-content redesign (031), no screen removals (029), no visual re-theming beyond the shell itself (033).
