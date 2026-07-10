# Feature Specification: Strava Activity Sync with Coach-Gated Session Linking

**Feature Branch**: `main` (user requested current branch; no feature branch created)

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Los atletas ya cuentan con ciclocomputadores donde registran sus actividades, con sensor de frecuencia cardiaca. Usando dispositivos como Garmin, Magene y iGPSport, y cuentan con Strava. De qué manera podemos enlazar de manera sencilla una forma de que cuando sincronicen sus actividades, se puedan ver reflejadas en nuestra plataforma. Asociadas a una sesión de entrenamiento o no. Que si subieron una actividad, solo el entrenador se encarga de enlazarla a la sesión específica del entrenamiento."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect an athlete's Strava account once, activities flow in automatically (Priority: P1)

A parent/guardian (or the coach acting with the family) connects the athlete's Strava account to the club platform one single time, from the athlete's profile. From that moment on, every ride the athlete records on their cycling computer (Garmin, Magene, iGPSport) and syncs to Strava appears automatically in the club platform under that athlete — with duration, distance, and heart-rate summary — without anyone uploading files or copying data by hand.

**Why this priority**: This is the entire value of the feature. Without automatic inflow of activities there is nothing to link to sessions. It is independently valuable even before any session-linking exists: the coach finally sees real ride data (including heart rate) instead of relying on verbal reports.

**Independent Test**: Connect one athlete's Strava account, record/upload a ride to Strava, and verify the activity appears in that athlete's activity list in the platform with correct date, duration, distance, and heart-rate summary — with no manual upload step.

**Acceptance Scenarios**:

1. **Given** an athlete profile without a Strava connection, **When** the parent/guardian completes the one-time authorization flow, **Then** the platform shows the connection as active for that athlete and confirms which account is linked.
2. **Given** an athlete with an active Strava connection, **When** the athlete uploads a new ride to Strava (from any of their devices), **Then** the activity appears in the platform associated to that athlete, initially in an "unlinked" state (not attached to any training session).
3. **Given** an athlete with an active connection, **When** the same Strava activity is delivered or fetched more than once, **Then** the platform shows it exactly once (no duplicates).
4. **Given** an activity that arrives with incomplete summary data, **When** the platform later re-checks it, **Then** the missing fields are completed without creating a second copy.
5. **Given** an athlete whose family revokes access (from the platform or from Strava itself), **When** the revocation happens, **Then** the platform marks the connection as disconnected, stops receiving new activities, and clearly shows the disconnected state on the athlete profile.

---

### User Story 2 - Coach links an activity to a specific training session (Priority: P2)

The coach opens a review view of recently synced activities. For each activity, the coach decides: link it to a specific planned training session (choosing from the club's session calendar), or leave it unlinked (free ride, family outing, commute). Only the coach (or an admin) can link, re-link, or unlink; athletes and parents cannot.

**Why this priority**: This is the workflow the coach explicitly asked for — manual, coach-gated association. It turns raw activity data into training evidence attached to the club's planned sessions, but it requires User Story 1 to exist first.

**Independent Test**: With at least one synced activity and one training session on the calendar, the coach links the activity to the session and verifies (a) the activity shows the session it belongs to, (b) the session detail shows the linked activity, and (c) a parent account cannot perform or alter the link.

**Acceptance Scenarios**:

1. **Given** an unlinked synced activity, **When** the coach opens the linking action, **Then** the platform proposes training sessions near the activity's date (same day first) and lets the coach pick one or search the calendar.
2. **Given** an activity linked to a session, **When** the coach views the training session detail, **Then** the linked activities of the session's athletes are visible from the session.
3. **Given** an activity linked to the wrong session, **When** the coach re-links it to another session or unlinks it, **Then** the change takes effect immediately and the previous association is removed.
4. **Given** a parent or athlete-scoped account, **When** they view an activity, **Then** they can see its linked/unlinked state but have no action to change it.
5. **Given** several unlinked activities, **When** the coach opens the review view, **Then** activities are grouped so the coach can process them quickly (e.g., by date), and already-linked ones are distinguishable from unlinked ones.

---

### User Story 3 - Parents and coach consult activity details inside the platform (Priority: P3)

Parents see their own child's synced activities (and only their own child's) inside the platform: date, duration, distance, average/max heart rate, and whether the coach linked it to a club session. The coach sees all club athletes' activities. Nobody needs to open Strava to answer "did my kid train, and how did it go?".

**Why this priority**: Consultation polish on top of Stories 1–2. Valuable, but the feature already works for the coach without it.

**Independent Test**: Log in as a parent with two athletes in the club (one their child, one not) and verify only their child's activities are visible, with readable summary metrics.

**Acceptance Scenarios**:

1. **Given** a parent with an athlete who has synced activities, **When** the parent opens the athlete's profile, **Then** they see the activity list with date, duration, distance, and heart-rate summary in plain language.
2. **Given** a parent account, **When** they attempt to view another family's athlete activities, **Then** access is denied.
3. **Given** an activity detail view, **When** any user opens it, **Then** no precise start/end location or route map of the minor is displayed (privacy default), only summary metrics.

---

### Edge Cases

- Activity uploaded to Strava hours or days late (device synced at home, not on the ride): it must still arrive and be linkable to a past session.
- Strava's near-real-time notification never arrives (documented reliability gaps): a periodic catch-up check must guarantee the activity still appears within the fallback window (see SC-002).
- Activity is edited or deleted on Strava after syncing: the platform reflects the update; if deleted on Strava, the platform copy is flagged (and any session link is preserved for the coach to review, not silently destroyed).
- Athlete has no Strava account (e.g., under Strava's minimum age of 13) or the family declines to connect: the athlete profile simply shows no synced activities; all other platform features work unchanged.
- The same family manages multiple athletes sharing one Strava account: each activity belongs to the connected account's athlete only; the platform does not attempt to guess split ownership.
- Authorization expires or is revoked from the Strava side: the platform shows the connection as broken and offers a re-connect action; it never fails silently.
- Two athletes ride together and both upload the same route: each athlete's own activity syncs to their own profile independently; no cross-athlete deduplication is performed.
- An activity clearly not related to training (e.g., a 5-minute test ride): the coach simply leaves it unlinked; unlinked is a valid permanent state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST allow a one-time, per-athlete connection to the athlete's Strava account, initiated from the athlete's profile by a parent/guardian, coach, or admin, and MUST record which platform user authorized it and when.
- **FR-002**: The connection flow MUST be gated by registered guardian consent for the minor, consistent with the club's existing consent handling, before any external activity data is received.
- **FR-003**: Once connected, the platform MUST automatically receive each new Strava activity of the athlete without any manual upload, and store it associated to the athlete in an "unlinked" state by default.
- **FR-004**: The platform MUST guarantee eventual delivery: if the near-real-time notification for an activity is missed, a periodic catch-up mechanism MUST bring the activity in within the fallback window defined in SC-002.
- **FR-005**: Activity ingestion MUST be idempotent: the same external activity, delivered or fetched any number of times, results in exactly one record, and later deliveries with more complete data update that record in place.
- **FR-006**: Each synced activity MUST expose at least: activity date/time, sport type, duration, distance, average and maximum heart rate (when the device recorded them), and its link state (unlinked, or linked to which training session).
- **FR-007**: Only coach and admin roles MUST be able to link an activity to a training session, change the link, or unlink it. Parent and athlete-scoped accounts MUST have read-only visibility of the link state.
- **FR-008**: When linking, the platform MUST suggest training sessions near the activity's date (same-day sessions first) while still allowing the coach to choose any session from the calendar.
- **FR-009**: A training session's detail MUST show the activities linked to it, per athlete, and an activity MUST show the session it is linked to (if any).
- **FR-010**: The coach MUST have a review view of recently synced activities that distinguishes unlinked from linked activities and supports processing them in bulk order (by date), so routine review stays fast.
- **FR-011**: Parents MUST see only their own children's activities; coaches and admins see all club athletes' activities. All existing club role rules apply unchanged.
- **FR-012**: The platform MUST NOT display precise start/end locations or route maps of minors' activities in any user-facing view in this feature's scope; only summary metrics are shown.
- **FR-013**: The platform MUST reflect upstream changes: activities edited on Strava update the stored summary; activities deleted on Strava are flagged as removed upstream rather than silently deleted, so the coach can review any affected session link.
- **FR-014**: The platform MUST handle disconnection cleanly: a family-initiated disconnect from the platform, or a revocation performed on Strava's side, MUST stop ingestion for that athlete, be visibly reflected on the athlete profile, and offer a re-connect path. Previously synced activities remain.
- **FR-015**: The platform MUST tolerate delayed and incomplete upstream data: an activity arriving with missing summary fields is stored and completed later, and the coach-facing views MUST render gracefully in the interim.
- **FR-016**: No minor-identifying data (names, locations, birth dates) from synced activities MAY appear in logs, error messages, or any third-party prompt, consistent with the club's existing privacy gates.

### Key Entities *(include if feature involves data)*

- **Athlete external connection**: The one-time authorization binding an athlete profile to their Strava account. Attributes: athlete, connection status (active / disconnected / broken), who authorized it, when, consent reference.
- **Synced activity**: One activity that flowed in from the athlete's Strava account. Attributes: owning athlete, external identifier (uniqueness key), date/time, sport type, duration, distance, heart-rate summary, upstream state (present / removed upstream), link state.
- **Session link**: The coach-made association between one synced activity and one training session. Attributes: activity, training session, who linked it, when. An activity has at most one session link; a session can have many linked activities (one or more per attending athlete).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of activities uploaded to Strava by a connected athlete are visible in the platform within 15 minutes of the Strava upload.
- **SC-002**: 100% of such activities are visible within 24 hours, even when the near-real-time path fails entirely (fallback guarantee).
- **SC-003**: Zero duplicate activities: across a full month of club activity, no synced activity appears more than once per athlete.
- **SC-004**: A family completes the one-time connection flow in under 5 minutes without technical assistance beyond a written guide.
- **SC-005**: The coach can review and link a week's worth of club activities (≈30–60 activities) in under 10 minutes, and link any single activity to a session in 3 interactions or fewer from the review view.
- **SC-006**: Zero privacy incidents: no route map or precise location of a minor is displayed anywhere, and no athlete-identifying data appears in operational logs during the first month of use.
- **SC-007**: After one month of adoption, at least 80% of activities performed during scheduled club sessions by connected athletes are linked to their corresponding session by the coach.

## Assumptions

- **Strava as the single hub**: All three device brands in use (Garmin, Magene, iGPSport) already reach Strava through the athletes' existing habits. The platform integrates with Strava only; no per-brand device integration is in scope. Athletes whose devices don't reach Strava are out of scope for automatic sync.
- **Coach-gated linking is manual by design**: The user explicitly wants the coach to be the only one who associates activities to sessions. No automatic date/sport matching performs the link; at most the platform *suggests* candidate sessions (FR-008).
- **Unlinked is a valid permanent state**: Free rides, commutes, and family outings are expected and simply remain unlinked.
- **Strava minimum age**: Strava's terms require users to be at least 13. Athletes aged 10–12 may not have accounts; the feature degrades gracefully to "no synced activities" for them (edge case covered). The club does not create or encourage under-age accounts.
- **Guardian consent reuses the club's existing consent mechanism** (as with psychological assessments), extended with a consent type for external activity-data sync.
- **Privacy default for minors**: Route maps and precise locations are excluded from all views in this feature, even though the upstream data may contain them. Revisiting this (e.g., coach-only maps) would be a separate future decision.
- **Upstream reliability is imperfect**: Publicly documented reports show Strava's near-real-time notifications can be delayed or missing, and first-delivery data can be incomplete. The design assumes this (FR-004, FR-005, FR-015) rather than treating it as exceptional.
- **Upstream cost risk**: Strava has announced paid API access requirements starting mid-2026. The club accepts this dependency risk; if the cost becomes prohibitive, a manual activity-file upload fallback would be specified as a separate feature. Budget confirmation happens before implementation planning.
- **Volume**: A small club (≈10–30 connected athletes, ≤10 activities/athlete/week) fits comfortably within published API usage limits; no high-volume design is needed.

## Out of Scope

- Automatic matching/auto-linking of activities to sessions (explicitly coach-manual).
- Route maps, GPS traces, segment data, or location display of any kind.
- Manual activity-file upload (FIT/GPX/TCX) for athletes without Strava — potential future feature.
- Per-brand direct integrations (Garmin Connect API, Magene, iGPSport portals).
- Training-load analytics, zone analysis, or performance scoring derived from synced activities — future features may build on this data.
- Two-way sync (pushing planned sessions out to Strava or to devices).
- Social features (kudos, comments, club feeds).
