# Feature Specification: Perceived Performance — Instant-Feeling App Despite a Sleeping Backend

**Feature Branch**: `012-perceived-performance-cache`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Perceived performance: instant-feeling app despite a sleeping backend — persist non-sensitive content for instant return visits, honestly communicate server wake-up waits, and keep navigation smooth (no empty flashes, likely-next data prepared, field actions reflected immediately)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Instant return visits from device-stored content (Priority: P1)

A coach on a tablet in the field, or a parent on an Android phone, reopens the app (or refreshes a page, or opens a new tab) hours after their last visit. Instead of a blank screen waiting on a backend that may take ~50 seconds to wake, they immediately see the non-sensitive content they viewed last time — the competition calendar list and race-event/competition metadata (the audited allow-list of FR-002) — clearly usable right away, while the app quietly refreshes that content in the background once the server responds.

**Why this priority**: This is the single largest perceived-performance win. Today every reload starts from zero and waits on a possibly-asleep backend; for the field/3G users this product exists to serve, that reads as "the app is broken." It is independently shippable and delivers value even if nothing else in this feature is built.

**Independent Test**: With a previously visited session on record and the backend forced asleep (or unreachable for the first ~50 s), reload the app and verify previously viewed allow-listed content is visible and navigable within ~1 second, then verify it silently updates when the server responds. Verify device storage contains no minor-identifiable data and is emptied on logout.

**Acceptance Scenarios**:

1. **Given** a coach viewed the competitions list earlier today and the server is now asleep, **When** they reopen the app or refresh the page, **Then** the previously viewed list content is visible within ~1 second and is refreshed in the background once the server responds, without any user action.
2. **Given** a user logs out on a shared device, **When** any other person uses the app on that device afterwards, **Then** no content from the previous account is visible or recoverable from device storage (the stored content is fully wiped at logout, in addition to the in-memory cleanup that exists today).
3. **Given** device-stored content older than the expiry window (~24 hours), **When** the user returns, **Then** the stale stored content is silently discarded and the app behaves as a first visit (normal loading states).
4. **Given** the app has been updated to a new version since the content was stored, **When** the user returns, **Then** the previously stored content is invalidated and re-fetched, so an outdated app's data shapes are never shown.
5. **Given** a parent viewed an athlete's personal profile (anthropometry/PHV, date of birth, medical notes) during a session, **When** device storage is inspected after a reload, **Then** none of that minor-identifiable content is present — only allow-listed, non-personal list content is ever stored.
6. **Given** device storage is unavailable or full (e.g., private browsing mode), **When** the user uses the app, **Then** the app works exactly as it does today (in-memory only), with no errors surfaced to the user.

---

### User Story 2 - Honest server wake-up experience (Priority: P2)

A user opens the app after the backend has gone to sleep. The app starts waking the server immediately — while the user is still typing their credentials or looking at cached content — and whenever a request genuinely has to wait, the user sees a plain-language "la aplicación está iniciando…" message instead of a silent spinner or a timeout error, so the wait feels expected rather than broken.

**Why this priority**: The constitution (Principle IV) already mandates surfacing a clear "starting the server" state instead of a generic spinner. This story fulfills that existing obligation and removes the single most confusing failure mode ("is it broken?"). It depends on nothing else in this feature.

**Independent Test**: Force a sleeping backend, open the login page, and verify a wake-up request is fired immediately; submit credentials and verify any wait longer than ~3 seconds shows the waking-server state, which clears automatically when the server responds.

**Acceptance Scenarios**:

1. **Given** the server is asleep, **When** the user lands on the login page (or the authenticated app shell mounts), **Then** the app immediately sends a lightweight wake-up request so the server is warming while the user types.
2. **Given** any in-app request has been waiting longer than ~3 seconds, **When** the wait continues, **Then** the user sees an explicit "la aplicación está iniciando…" state (in español neutro) instead of an indefinite spinner or an error.
3. **Given** the waking-server state is showing, **When** the server responds, **Then** the state clears automatically and the requested content appears without the user retrying.
4. **Given** the server fails to respond after the existing retry policy is exhausted, **When** the wait ends, **Then** the user sees a friendly, localized error state with a retry affordance — never raw exception text.

---

### User Story 3 - Smooth navigation and instant field actions (Priority: P3)

A coach moves through paginated standings, filters session lists, opens a row they were hovering over, and records attendance at the track. Pages never flash empty between loads; data for the row they are about to open was quietly prepared in advance; attendance and roster changes appear on screen the moment they tap, reconciling with the server afterwards.

**Why this priority**: These are incremental perceived-performance refinements that compound with P1/P2 but deliver smaller standalone value. Each is independently observable and testable.

**Independent Test**: Navigate between pages of a standings table and verify the previous page remains visible (with a subtle refreshing indicator) until the next page arrives; hover/touch a list row, open it, and verify it renders without a visible loading state; record attendance and verify the UI reflects it instantly and rolls back with a localized message if the server rejects it.

**Acceptance Scenarios**:

1. **Given** a user is on page 1 of a paginated or filtered list (standings, sessions, competitions), **When** they move to page 2 or change a filter, **Then** the existing rows remain visible (with a subtle refreshing indicator) until the new rows arrive — never an empty intermediate state.
2. **Given** a user hovers over (or touch-starts on) a list row, **When** they open that row shortly after, **Then** the detail renders without a visible loading state in the common case (warm server).
3. **Given** a user has just logged in, **When** their role's landing page opens, **Then** its primary data was already being fetched during the login transition.
4. **Given** a coach records attendance or adjusts a roster in the field, **When** they confirm the action, **Then** the change is reflected on screen immediately, and **if** the server later rejects it, the change is rolled back with a clear, localized explanation.

---

### Edge Cases

- **Corrupted or unreadable stored content**: the app discards it silently and behaves as a first visit; no error shown.
- **Background refresh fails while cached content is on screen**: cached content remains visible with a non-blocking, localized indicator that data could not be refreshed (no unbounded spinner, no raw error).
- **Multiple tabs open simultaneously**: the most recently fetched data wins in device storage; tabs never show another account's data.
- **Browser crash or battery death before logout on a shared device**: the expiry window (~24 h) bounds exposure; only allow-listed non-personal content was stored in the first place.
- **Device clock skew**: expiry must not be defeated by a wrong device clock in a way that retains data materially longer than intended.
- **Optimistic action conflicts** (e.g., two coaches edit the same roster): the server remains the source of truth; the losing change is rolled back with a localized message.
- **Parent switches active child on a shared family device**: in-memory data for the previous child is already purged today; device-stored content needs no extra wipe because per-athlete content is never stored (decision recorded in Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST retain allow-listed server content on the device across page reloads, new tabs, and app restarts, and MUST display that retained content within ~1 second of opening a previously visited view, even when the server is asleep or unreachable.
- **FR-002**: Device retention MUST operate on an explicit allow-list only. Initially (as narrowed by the mandatory `data-privacy-guard` audit, 2026-06-10): the competition calendar event **list**, race events available for the calendar, race-event metadata (list + detail: name/date/location/conditions), and revision-reason catalogs. Everything not allow-listed MUST NOT be stored — explicitly including: race **standings/results/competitors** (rows embed competitor names, including minors — public posting at events does not waive Ley 1581 for device persistence), single calendar-event **detail** (birthday events embed a minor's first name and age), **training-session lists** (items can embed `media[].athlete_ids` and free-text coach notes; may be re-allowed only after a backend summary schema strips those fields), anthropometry/PHV records, medical data, dates of birth, attendance, parent-specific data, newsletters, per-athlete AI-generated content, and credentials/tokens beyond what the app already stores today. New content types default to *not stored* and require a fresh privacy review.
- **FR-003**: Content displayed from device storage MUST be refreshed in the background automatically once the server responds, and the on-screen content MUST update without user action.
- **FR-004**: All device-stored content MUST be fully wiped at logout, in addition to the in-memory cleanup that exists today.
- **FR-005**: Device-stored content MUST be scoped to the account that fetched it; content fetched under one account MUST never be displayed under another account on the same device.
- **FR-006**: Device-stored content MUST expire automatically after approximately 24 hours and MUST be invalidated whenever the app is updated to a new version.
- **FR-007**: If device storage is unavailable, full, or corrupted, the app MUST degrade gracefully to today's in-memory behavior with no user-facing errors.
- **FR-008**: When any request has been waiting longer than ~3 seconds, the app MUST display an explicit waking state (final copy per ux-researcher validation: "La aplicación está iniciando…" — "aplicación" instead of "servidor" for non-technical parents; español neutro, Colombia) instead of a generic spinner, and MUST clear it automatically when the response arrives.
- **FR-009**: The app MUST proactively send a lightweight wake-up request to the server as soon as the login page or the authenticated app shell mounts.
- **FR-010**: Paginated and filtered lists MUST keep the previously loaded rows visible, with a subtle refreshing indicator, until replacement data arrives; an empty intermediate state MUST never be shown when previous data exists.
- **FR-011**: The app MUST prepare likely-next data ahead of navigation: the detail behind a list row on hover/touch intent, and the role-appropriate landing data immediately after a successful login.
- **FR-012**: Attendance recording and roster adjustments MUST be reflected on screen immediately upon user confirmation and reconciled with the server afterwards; a server rejection MUST roll the change back and show a clear, localized explanation.
- **FR-013**: This feature MUST NOT change which data any role is permitted to see; all existing access rules apply unchanged to stored, prefetched, and optimistically displayed content.
- **FR-014**: All user-facing copy introduced by this feature MUST be in español neutro (Colombia), with full diacritics.

### Key Entities

- **Device-stored content snapshot**: the allow-listed server responses retained on the device, together with the metadata needed to govern them — owning account, app version at storage time, and freshness timestamps for expiry.
- **Persistence allow-list**: the explicit, reviewable catalog of content types eligible for device storage; default-deny for anything new.
- **Waking-server state**: a user-visible UI state representing "the server is waking up", triggered by wait duration, cleared by response arrival, distinct from error states.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a return visit with the server asleep, previously viewed allow-listed content is visible and navigable within 1 second on a mid-tier Android device over simulated 3G (versus up to ~50 seconds of blank screen today).
- **SC-002**: 100% of requests that wait longer than ~3 seconds present the explicit waking-server state; users never see an indefinite spinner or a raw timeout error during a cold start.
- **SC-003**: Moving between pages or filters of a list never shows an empty intermediate state when previous data exists (0 occurrences in acceptance testing).
- **SC-004**: A privacy audit of device storage after exercising every major flow finds zero minor-identifiable fields (names tied to personal data, dates of birth, anthropometry/medical values, per-athlete AI text).
- **SC-005**: After logout, zero application data from the session remains in device storage.
- **SC-006**: Opening a list item after hover/touch intent renders without a visible loading state in at least 80% of attempts against a warm server.
- **SC-007**: A coach recording attendance in the field sees the result reflected on screen in under 1 second, regardless of server latency at that moment.

## Assumptions

- The three user stories map to three independently shippable delivery slices (P1 → P2 → P3), matching the analysis this spec derives from.
- **Decision (owner-confirmed)**: a logout-only device wipe is sufficient for the parent child-switch case, because per-athlete content is never device-stored (allow-list) and in-memory data is already purged per athlete on switch; no additional device wipe occurs on child switch.
- **Decision (owner-confirmed)**: the waking-server state appears after ~3 seconds of waiting — late enough to stay hidden on ordinarily slow requests, early enough to reassure during a real cold start.
- The ~24-hour expiry window is a privacy/freshness trade-off default; it bounds shared-device exposure while covering a typical training-day usage pattern.
- The initial allow-list is curated with a privacy review (data-privacy-guard audit per the constitution) and may only grow through the same review. **Audit outcome (2026-06-10)**: the original draft list was narrowed — standings/results/competitors, single calendar-event detail, and training-session lists were excluded (see FR-002); FR-002 reflects the audited list, which is authoritative over any earlier draft.
- No backend or database change is required or permitted by this feature; the backend's existing lightweight health endpoint is assumed available for wake-up requests.
- The existing retry-with-backoff behavior remains the mechanism that keeps requests alive through a cold start; this feature changes what the user sees while that happens.
