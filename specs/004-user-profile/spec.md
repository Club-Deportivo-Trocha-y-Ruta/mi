# Feature Specification: User Profile & Account Settings

**Feature Branch**: `claude/branch-cloning-ok0PF`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "create profile module for each user. Implement the option to change email, passwords, basic information"

## User Scenarios & Testing *(mandatory)*

This feature gives every login-capable user (admin, coach, parent) a self-service
"My Profile / Account Settings" area where they manage their own account: view and
update their basic information, change their email address, and change their password.
Each capability is an independent, testable slice.

### User Story 1 - Update my basic information (Priority: P1)

A signed-in user opens their profile, sees their current details (first name, last name,
phone), edits one or more of them, and saves. The change is reflected immediately the
next time their name or contact details are shown anywhere in the product.

**Why this priority**: This is the most-used, lowest-risk capability and the foundation
of the profile module. It delivers immediate value (correcting a misspelled name or an
outdated phone number) without touching credentials or security flows, so it is a viable
standalone MVP.

**Independent Test**: Sign in, change the phone number and last name, save, reload the
profile, and confirm the new values persist and appear in the app's user display.

**Acceptance Scenarios**:

1. **Given** a signed-in user on their profile page, **When** they edit their first name,
   last name, and/or phone and save, **Then** the changes are persisted and confirmed
   with a success message.
2. **Given** a signed-in user editing their profile, **When** they submit an invalid
   value (e.g., empty required name, malformed phone), **Then** the form shows an inline,
   localized validation error and nothing is saved.
3. **Given** a signed-in user on their profile page, **When** the page loads, **Then**
   they see their own current values and CANNOT edit fields that are not self-managed
   (role, account active status, login capability, club membership).

---

### User Story 2 - Change my password (Priority: P1)

A signed-in user changes their account password from within the profile area by entering
their current password and a new password (with confirmation). On success, the new
password is required for future sign-ins.

**Why this priority**: Letting authenticated users rotate their own password is a core
security capability and complements the existing "forgot password" recovery flow (which
is for users who are locked out). It is independently valuable and testable.

**Independent Test**: Sign in, open "Change password", enter the correct current password
and a valid new password twice, save, sign out, and confirm sign-in works only with the
new password.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they provide the correct current password and a
   valid, confirmed new password, **Then** the password is updated and a confirmation
   message is shown.
2. **Given** a signed-in user, **When** they provide an incorrect current password,
   **Then** the change is rejected with a clear error and the password is unchanged.
3. **Given** a signed-in user, **When** the new password fails the strength policy or the
   confirmation does not match, **Then** an inline validation error is shown and nothing
   is changed.
4. **Given** a successful password change, **When** it completes, **Then** the user
   receives a confirmation email that their password was changed (no password in the email).

---

### User Story 3 - Change my email address (Priority: P2)

A signed-in user updates the email address tied to their account. Because email is the
login identifier and a contact channel, the change is protected with **verify-new-email-
before-apply**: the user re-confirms their identity, the system ensures the new address is
not already in use, and the email only switches after the user proves ownership of the new
address by completing a confirmation sent to it.

**Why this priority**: Email change is higher-risk than basic info (it changes the login
identifier and notification destination), so it is sequenced after the two P1 slices but
is still essential for a complete profile module.

**Independent Test**: Sign in, request an email change to an unused address, complete the
confirmation sent to that new address, and confirm the new address becomes the login
identifier while the old one no longer signs in.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they request to change their email to an address
   not used by any other account, **Then** a confirmation is sent to the NEW address and
   the account email is NOT changed yet.
2. **Given** a pending email-change confirmation, **When** the user completes the
   confirmation from the new address before it expires, **Then** the account's email is
   updated and used for future sign-in and notifications.
3. **Given** a signed-in user, **When** they request an email already used by another
   account, **Then** the request is rejected with a neutral, enumeration-safe message and
   no change is made and no confirmation is sent.
4. **Given** a signed-in user requesting an email change, **When** re-authentication
   (current password) is missing or incorrect, **Then** the request is rejected and no
   confirmation is sent.
5. **Given** an email change has taken effect, **When** it completes, **Then** a
   notification is sent to the previous email address so the original owner is alerted.
6. **Given** a pending email-change confirmation, **When** it has expired or was already
   used, **Then** completing it fails and the account email is unchanged.

---

### Edge Cases

- A user submits the profile form with no changes → the system accepts it as a no-op (or
  a neutral "no changes" message), never an error.
- A user tries to set a new password equal to the current password → rejected with a
  clear message.
- Two profile edits happen for the same account in quick succession → the last valid save
  wins; no partial/corrupt state is persisted.
- An athlete record (`can_login = false`) → has no profile/account-settings area and
  cannot reach these screens.
- A user whose account is deactivated mid-session → cannot save profile changes.
- Email change to the user's own current email → treated as a no-op, not a conflict.
- A user attempts to edit another user's profile via direct navigation → denied; users
  may only manage their own account through this module.
- Network/server cold start (Render free tier) → the UI shows a clear "starting" / loading
  state rather than a generic spinner or timeout error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a self-service profile area accessible to every
  authenticated, login-capable user (admin, coach, parent).
- **FR-002**: The system MUST display the signed-in user's own current basic information
  (first name, last name, phone) and email address.
- **FR-003**: Users MUST be able to update their own first name, last name, and phone, and
  the changes MUST persist and be reflected wherever the user's identity is displayed.
- **FR-004**: The system MUST validate basic-information input (required names, phone
  format) and reject invalid input with inline, localized error messages without saving.
- **FR-005**: The system MUST NOT allow a user to change, via this module, fields that are
  not self-managed: role, account-active status, login capability, account creator, or
  club membership.
- **FR-006**: Users MUST be able to change their own password by supplying their current
  password and a new password with confirmation.
- **FR-007**: The system MUST reject a password change when the supplied current password
  is incorrect, and MUST leave the existing password unchanged.
- **FR-008**: The system MUST enforce the project's password strength policy on the new
  password and require the confirmation field to match.
- **FR-009**: The system MUST send a confirmation notification after a successful password
  change, and the notification MUST NOT contain the password or any minor's personal data.
- **FR-010**: Users MUST be able to request a change to their own email address, and the
  change MUST take effect only after the user confirms ownership of the new address via a
  confirmation sent to that new address (verify-new-email-before-apply).
- **FR-011**: The system MUST prevent an email change to an address already associated with
  another account and MUST respond with a neutral, enumeration-safe message, sending no
  confirmation.
- **FR-012**: The system MUST require identity re-confirmation (current password) before
  initiating an email change request.
- **FR-013**: The email-change confirmation MUST be single-use and time-limited; once it
  expires or is consumed it MUST NOT be reusable, mirroring the project's existing hashed,
  single-use token pattern for password recovery.
- **FR-013a**: The system MUST notify the previous email address after an email change has
  taken effect, so the original owner is alerted.
- **FR-014**: The system MUST ensure a user can only view and modify their OWN account
  through this module (no access to other users' profiles).
- **FR-015**: The system MUST NOT expose sensitive account data (password hashes, raw
  tokens, other users' data) in any profile response, log, or error message.
- **FR-016**: The system MUST keep all profile/account-settings end-user copy (labels,
  messages, emails) in español neutro (Colombia) and avoid clinical/judgmental wording.
- **FR-017**: All profile screens MUST provide explicit loading, empty, and error states
  for every asynchronous operation.
- **FR-018**: The system MUST log security-relevant profile events (password change, email
  change) without recording credentials or PII of minors.

### Key Entities *(include if feature involves data)*

- **User Account**: The existing account a person signs in with. Self-managed attributes
  in this module: first name, last name, phone, email, password. Non-self-managed (read-only
  here): role, active status, login capability, creator, club membership, athlete linkage.
- **Email Change Confirmation**: A short-lived, single-use confirmation that ties a
  requested new email to the account and proves ownership of the new address before the
  change is applied. Holds the target (new) email, an expiry, and a used/consumed marker.
  Mirrors the project's existing hashed, single-use, time-limited token pattern used for
  password recovery.
- **Account Notification**: A message sent to the user (e.g., "password changed",
  "email changed") on a security-relevant account event; never contains secrets or minor PII.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can update and save their basic information in under 1 minute, and the
  updated values are visible immediately after saving.
- **SC-002**: 100% of attempts to change a password with an incorrect current password are
  rejected, with the original password remaining valid.
- **SC-003**: 100% of attempts to change an email to an address already in use are rejected
  with a neutral message that does not reveal whether the address exists.
- **SC-004**: After a successful password or email change, the user receives the
  corresponding confirmation/alert notification 100% of the time.
- **SC-005**: A user can never view or modify another user's account through this module
  (0 successful cross-account accesses in security testing).
- **SC-006**: No profile response, log entry, or error message contains a password, raw
  token, or any minor's personal data (verified by privacy audit).
- **SC-007**: Every profile screen shows a clear loading/error state on slow or cold-start
  responses (no unbounded spinners, no raw exception text).

## Assumptions

- Scope is **self-service for the signed-in user only**. Administrative editing of other
  users' accounts is out of scope for this feature (it may already exist in the users
  admin area and is not changed here).
- Only login-capable users have a profile area. Athlete records (`can_login = false`) are
  excluded; managing athlete sport profiles remains the existing athletes module.
- The existing authentication, password-hashing, email-delivery, and notification
  infrastructure is reused; no new external service is introduced.
- The password strength policy reuses the project's existing/standard policy applied in the
  password-reset flow; no new policy is defined here.
- The "forgot password" recovery flow (for locked-out users) already exists and is separate
  from the in-session "change password" capability added here.
- Email and notification copy follows the constitution's language policy (español neutro,
  Colombia) and minor-privacy rules (Ley 1581).
- Re-authentication for sensitive changes (password, email) uses the user's current
  password rather than a separate step-up factor.
- Email change uses **verify-new-email-before-apply** (confirmed with the user): the
  account email switches only after the user confirms ownership of the new address.
  Administrative recovery of a user's email is out of scope for this feature.
