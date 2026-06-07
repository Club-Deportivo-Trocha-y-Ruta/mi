# Feature Specification: Password Reset from Login Page

**Feature Branch**: `claude/password-restore-login-page-pvwwU`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "We need to buy the option to restore the password from login page"

> Interpretation note: "buy" is read as "build/add". The request is to provide a
> self-service way for users to recover access to their account when they have
> forgotten their password, initiated from the login page.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Request a password reset link (Priority: P1)

A user (coach, club administrator, or parent/guardian) who cannot remember their
password opens the login page, selects a clearly visible "¿Olvidaste tu contraseña?"
option, enters the email address associated with their account, and is told that if
that email belongs to an account, a reset link has been sent. They receive an email in
español with a link to set a new password.

**Why this priority**: Without the ability to request a reset, a user locked out of the
platform has no self-service path back in and must contact the coach/administrator
manually. This is the entry point of the entire feature and delivers the core value:
regaining access. It is the minimum viable slice.

**Independent Test**: Can be fully tested by visiting the login page, opening the reset
request form, submitting a known account email, and verifying that (a) a confirmation
message is shown and (b) a reset email is generated/sent. Submitting an unknown email
shows the same neutral confirmation and generates no email.

**Acceptance Scenarios**:

1. **Given** an active account exists for `coach@example.com`, **When** the user submits
   that email in the reset request form, **Then** the system shows a neutral
   confirmation message and sends a password-reset email to that address.
2. **Given** no account exists for `unknown@example.com`, **When** the user submits that
   email, **Then** the system shows the same neutral confirmation message and sends no
   email (no disclosure of whether the account exists).
3. **Given** the user is on the login page, **When** the page renders, **Then** a clearly
   labeled "forgot password" affordance is visible and reachable by keyboard.
4. **Given** the user submits an empty or malformed email, **When** they attempt to send,
   **Then** an inline, localized validation message is shown and no request is sent.

---

### User Story 2 - Set a new password using the emailed link (Priority: P1)

A user who received the reset email opens the link, is presented with a form to enter a
new password (with confirmation), submits it, and can then log in with the new password.

**Why this priority**: Requesting a link has no value unless the user can actually
complete the reset. Together with User Story 1 this forms the end-to-end recovery flow.
It is independently testable given a valid token.

**Independent Test**: Can be tested by generating a valid reset token, opening the reset
page with that token, submitting a compliant new password, and confirming that the
account password is changed and the user can authenticate with it.

**Acceptance Scenarios**:

1. **Given** a valid, unexpired, unused reset link, **When** the user submits a new
   password that meets the password policy and matches its confirmation, **Then** the
   password is updated, the link is invalidated, and the user is informed they can now
   log in.
2. **Given** a valid reset link, **When** the user submits a new password that does not
   meet the password policy, **Then** an inline, localized validation message explains
   the requirement and the password is not changed.
3. **Given** an expired reset link, **When** the user opens it, **Then** the system
   explains the link has expired and offers to request a new one.
4. **Given** an already-used reset link, **When** the user opens it again, **Then** the
   system explains the link is no longer valid and offers to request a new one.
5. **Given** a successful password reset, **When** the user logs in with the old
   password, **Then** authentication fails.

---

### User Story 3 - Resist abuse and account enumeration (Priority: P2)

The reset flow protects users and the platform against being used to discover which
emails have accounts, and against being used to flood a person's inbox or brute-force
tokens.

**Why this priority**: This is a juvenile-athlete platform where parent and coach
accounts are linked to minors' data; an account-recovery flow is a common attack
surface. The recovery flow can ship for internal testing without full hardening, but it
MUST be hardened before it is exposed in production, hence P2 rather than P3.

**Independent Test**: Can be tested by issuing repeated reset requests for the same email
and confirming requests are throttled, by confirming responses are identical for
existing vs. non-existing emails, and by confirming tokens are single-use and expire.

**Acceptance Scenarios**:

1. **Given** repeated reset requests for the same email within a short window, **When**
   the threshold is exceeded, **Then** further requests are throttled without revealing
   account existence.
2. **Given** any reset request, **When** the response is returned, **Then** the message
   and timing do not differ between existing and non-existing accounts in a way that
   reveals which emails have accounts.
3. **Given** a reset is completed or a new reset is requested, **When** older outstanding
   links for the same account are checked, **Then** they are no longer usable.

---

### Edge Cases

- A user requests a reset for an account that exists but is deactivated or lacks login
  permission (e.g., an athlete profile that cannot log in): the system shows the same
  neutral confirmation but does not deliver a usable reset, since the account cannot log
  in anyway.
- The email delivery provider is temporarily unavailable: the user still sees the neutral
  confirmation; the failure is logged (without exposing PII) and does not reveal account
  existence.
- A user opens the reset link on a different device/browser than the one used to request
  it: the reset still works (the link is the proof of access to the inbox).
- A user requests several resets and then uses the oldest link: only the most recent
  valid link works; older ones are invalidated.
- The new password equals the current password: accepted unless a "must differ" rule is
  later required (out of scope for v1; documented as an assumption).
- A logged-in user navigates to the reset request page: the flow still functions
  (recovery does not require being logged out).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The login page MUST present a clearly labeled, keyboard-accessible option
  to start password recovery (e.g., "¿Olvidaste tu contraseña?").
- **FR-002**: Users MUST be able to request a password reset by submitting the email
  address associated with their account.
- **FR-003**: The system MUST respond to every reset request with the same neutral
  confirmation message, regardless of whether an account exists for that email, to avoid
  account enumeration.
- **FR-004**: When the submitted email belongs to an account that is allowed to log in,
  the system MUST send a password-reset message to that address in español neutro
  (Colombia) containing a single-use link to complete the reset.
- **FR-005**: The reset link MUST be time-limited and expire after a defined period; an
  expired link MUST NOT allow a password change.
- **FR-006**: The reset link MUST be single-use; once a password is successfully changed,
  the link MUST be invalidated.
- **FR-007**: Requesting a new reset for an account MUST invalidate any previously issued,
  still-valid links for that account.
- **FR-008**: Users following a valid link MUST be able to set a new password with a
  confirmation field, and the system MUST enforce the platform's password policy with
  inline, localized validation.
- **FR-009**: After a successful reset, the user MUST be able to authenticate with the new
  password and MUST NOT be able to authenticate with the previous password.
- **FR-010**: The system MUST throttle repeated reset requests (per email and/or per
  source) to mitigate inbox flooding and abuse, without disclosing account existence.
- **FR-011**: The system MUST NOT include any minor's personal data, nor reveal the
  account holder's role or linked athletes, in the reset email, the confirmation
  message, or any log entry related to this flow.
- **FR-012**: Reset-related events (requested, sent, completed, failed) MUST be logged
  without personal data beyond what is strictly necessary, using non-identifying
  references, to support security review.
- **FR-013**: Reset tokens MUST be stored and compared in a way that a leak of stored
  data does not reveal usable tokens (i.e., not stored in plain, recoverable form).
- **FR-014**: The reset request and reset completion screens MUST provide clear loading,
  success, expired/invalid, and error states with no raw error text shown to users.
- **FR-015**: Accounts that cannot log in (deactivated or without login permission) MUST
  NOT receive a usable reset, even though the neutral confirmation is still shown.

### Key Entities *(include if feature involves data)*

- **Account (User)**: The existing platform user (coach, administrator, or parent) who
  owns a password and an email address. Athletes that cannot log in are out of scope as
  recipients. Reused from the existing data model; not redefined here.
- **Password Reset Request**: Represents a single outstanding recovery attempt for an
  account. Key attributes: the target account reference, a securely stored token
  representation, an expiration time, a single-use/consumed indicator, and creation
  metadata. Relationship: belongs to exactly one Account; an Account may have at most one
  currently valid request (older ones are invalidated on new requests or on completion).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who has forgotten their password can request a reset and complete it
  end-to-end (from login page to logging in with the new password) in under 5 minutes,
  assuming timely email delivery.
- **SC-002**: 100% of reset requests return an identical neutral confirmation, with no
  difference in wording that reveals whether the email has an account.
- **SC-003**: 100% of reset links are unusable after first successful use and after their
  expiration window elapses.
- **SC-004**: After a successful reset, 100% of login attempts with the previous password
  fail and login with the new password succeeds.
- **SC-005**: Repeated reset requests beyond the defined threshold are throttled in 100%
  of attempts, verified by automated test.
- **SC-006**: No reset email, user-facing message, or log entry contains any minor's
  personal data or reveals the account holder's role or linked athletes, verified by a
  privacy audit and automated tests.
- **SC-007**: Reduce the number of manual, coach/administrator-handled password recovery
  requests to near zero once the feature is live.

## Assumptions

- **Delivery channel is email.** The platform already has an email provider configured
  for transactional messages; password reset reuses it. SMS or other channels are out of
  scope for v1.
- **Eligible recipients are login-capable adult accounts** (coach, administrator,
  parent/guardian). Athlete profiles that cannot log in are not eligible recipients.
- **Token lifetime defaults to 1 hour, single-use.** This is a reasonable industry
  default balancing security and usability; it can be tuned during planning without
  changing scope.
- **Password policy is the platform's existing policy.** This feature enforces the same
  rules already used for account passwords; it does not introduce a new policy.
- **Neutral, enumeration-safe responses are mandatory** for all reset requests; this is
  treated as a hard requirement, not a toggle.
- **No "new password must differ from old" rule in v1.** Can be added later if desired.
- **Reuse of existing auth, email-token, and notification patterns** already present in
  the platform (e.g., the existing token-based invitation flow) is expected; this keeps
  the feature within the agreed stack and avoids new runtime dependencies.
- **All user-facing copy (page text, emails, validation messages) is in español neutro
  (Colombia)**, consistent with the product language policy.
