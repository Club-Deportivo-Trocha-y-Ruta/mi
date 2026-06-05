# Workflow: Onboarding Flow Implementation

**Date:** 2026-04-15
**Based on:** `docs/08-onboarding/research.md`, `docs/08-onboarding/design.md`
**Prerequisite:** Parents module implemented (`docs/06-parents/workflow.md`)

---

## Summary

17 steps organized in 5 phases. Each step indicates the responsible specialized agent, files to create/modify, and dependencies. Steps with no dependencies between them can be executed in parallel.

---

## Phase A — Backend: Data Models and Migration

### Step 1: Create `ParentalConsent` model
**Agent:** `fastapi-architect`
**Files:**
- Create: `backend/app/models/parental_consent.py`
- Modify: `backend/app/models/__init__.py` (add import)

**Detail:**
- `parental_consents` table with fields: id, parent_user_id (FK users), athlete_id (FK athletes), consent_version, consented_at, consent_method, ip_address, data_collection, training_tracking, anthropometry, third_party_sharing, withdrawn_at
- Indexes: `(parent_user_id, athlete_id)`, `athlete_id`
- Relationships: parent → User, athlete → Athlete

**Success criterion:** Model importable, no syntax errors.
**Dependencies:** None
**Estimate:** Small

---

### Step 2: Generate Alembic migration
**Agent:** `fastapi-architect`
**Command:**
```bash
cd backend && alembic revision --autogenerate -m "add_parental_consents_table"
```
**Verification:**
```bash
cd backend && alembic upgrade head
```

**Success criterion:** Migration applies without errors. Table `parental_consents` exists in DB.
**Dependencies:** Step 1
**Estimate:** Small

---

### Step 3: Extend Pydantic schemas
**Agent:** `fastapi-architect`
**Files:**
- Modify: `backend/app/schemas/parent_invite.py`

**Changes:**
1. Add `ParentalConsentData` schema (accept_data_collection, accept_training_tracking, accept_anthropometry, accept_third_party, privacy_policy_version)
2. Add `consent: ParentalConsentData` and `relationship_type: str = "acudiente"` to `ParentRegisterRequest`
3. Add `role: str = "parent"` and `club_name: str = ""` to `ParentInviteTokenValidation`
4. Create `ParentalConsentOut` schema for future responses

**Success criterion:** Schemas validate correctly. Import tests pass.
**Dependencies:** None (can run in parallel with Step 1)
**Estimate:** Small

---

### Step 4: Extend `consume_invite()` service
**Agent:** `fastapi-architect`
**Files:**
- Modify: `backend/app/services/invitations.py`

**Changes:**
1. Add parameters: `relationship_type: str`, `consent: ParentalConsentData`, `ip_address: str | None`
2. Use `relationship_type` to create `ParentAthlete` (instead of hardcoded "acudiente")
3. Create `ParentalConsent` record with consent data
4. Update `athlete.parental_consent_obtained = True` and `athlete.parental_consent_date`
5. Maintain backward compatibility: new parameters with defaults

**Success criterion:** `consume_invite()` creates User + ClubMember + ParentAthlete + ParentalConsent in an atomic transaction.
**Dependencies:** Step 1, Step 3
**Estimate:** Medium

---

### Step 5: Update endpoint `POST /api/auth/parent-register`
**Agent:** `fastapi-architect`
**Files:**
- Modify: `backend/app/routers/auth.py`

**Changes:**
1. Pass `body.relationship_type`, `body.consent`, and `request.client.host` to `consume_invite()`
2. Add `Request` as dependency to obtain IP

**Success criterion:** Endpoint accepts extended payload and records consent.
**Dependencies:** Step 4
**Estimate:** Small

---

### Step 6: Update endpoint `GET /api/auth/invite/{token}`
**Agent:** `fastapi-architect`
**Files:**
- Modify: `backend/app/routers/auth.py`

**Changes:**
1. Include `role="parent"` in response
2. Obtain `club_name` from the athlete and add to response

**Success criterion:** Response includes role and club_name.
**Dependencies:** Step 3
**Estimate:** Small

---

## Phase B — Backend: Email Template

### Step 7: Create HTML email template
**Agent:** `fastapi-architect`
**Files:**
- Create: `backend/templates/email/parent_invite.html`

**Detail:**
- Jinja2 template with inline CSS (email compatibility)
- Variables: `{{ athlete_first_name }}`, `{{ club_name }}`, `{{ invite_url }}`
- Design: green header (#16a34a), content with benefits, CTA button, club footer
- Responsive (max-width: 600px)
- Jinja2 autoescaping enabled

**Success criterion:** Template renders correctly with test variables. No XSS possible.
**Dependencies:** None (parallel with Phase A)
**Estimate:** Small

---

### Step 8: Fix URL in invitation generation
**Agent:** `fastapi-architect`
**Files:**
- Modify: `backend/app/routers/parent_athletes.py` (line ~264)

**Change:**
- Change invitation URL from `/registro-padre?token=` to `/onboarding?token=`
- Or use configuration variable `ONBOARDING_URL` in `config.py`

**Success criterion:** Generated URL points to `/onboarding?token={token}`.
**Dependencies:** None (parallel)
**Estimate:** Small

---

## Phase C — Frontend: Wizard Infrastructure

### Step 9: Create onboarding Zod schemas
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/schemas/onboarding.schema.ts`

**Detail:**
- `accountSchema`: password + password_confirm with refinement
- `parentProfileSchema`: first_name, last_name, phone, relationship_type
- `consentSchema`: 3 mandatory (literal true) + 1 optional (boolean)
- `onboardingFormSchema`: combination for type-safety
- Type export: `OnboardingFormData`

**Success criterion:** Schemas compile without TypeScript errors. Validations are correct.
**Dependencies:** None (parallel with backend)
**Estimate:** Small

---

### Step 10: Create onboarding Zustand store
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/stores/onboarding-store.ts`

**Detail:**
- State: currentStep, role, token, email, athleteName, clubName, formData
- Actions: setStep, setTokenData, updateFormData, reset
- Middleware: `persist` with key `"trocha-onboarding"` in localStorage

**Success criterion:** Store persists and recovers state correctly.
**Dependencies:** None (parallel)
**Estimate:** Small

---

### Step 11: Create `useOnboarding` hook
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/hooks/onboarding/useOnboarding.ts`
- Create: `frontend/src/hooks/onboarding/index.ts`

**Detail:**
- `useValidateToken(token)` — TanStack Query wrapping `GET /api/auth/invite/{token}`
- `useCompleteOnboarding()` — Mutation wrapping `POST /api/auth/parent-register`
- Error handling: 410 (expired), 409 (duplicate email), 500 (server error)

**Success criterion:** Hooks work with TanStack Query. Correct loading/error states.
**Dependencies:** Step 9 (types), existing API client
**Estimate:** Small

---

### Step 12: Update API client
**Agent:** `react-ui-engineer`
**Files:**
- Modify: `frontend/src/api/parents.ts` (or create `frontend/src/api/onboarding.ts`)

**Changes:**
- Update `registerParent()` to include `relationship_type` and `consent` in payload
- Update return type of `validateInviteToken()` to include `role` and `club_name`

**Success criterion:** API client aligned with updated backend schemas.
**Dependencies:** Step 3 (backend schemas defined)
**Estimate:** Small

---

## Phase D — Frontend: Wizard Components

### Step 13: Create `OnboardingStepper` component
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/components/onboarding/OnboardingStepper.tsx`
- Create: `frontend/src/components/onboarding/onboarding-steps.ts` (declarative config)

**Detail:**
- Custom visual stepper with shadcn primitives (Badge, Separator)
- Props: steps (StepConfig[]), currentStep (number)
- Shows: icon + label per step, state (completed/current/pending)
- Responsive: horizontal on desktop, vertical on mobile
- Declarative `ONBOARDING_STEPS` config with roles, schemas, fields, components

**Success criterion:** Stepper renders correctly for 4 steps (parent) and 4 steps (future coach).
**Dependencies:** Step 9
**Estimate:** Medium

---

### Step 14: Create step components
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/components/onboarding/steps/AccountStep.tsx`
- Create: `frontend/src/components/onboarding/steps/ParentProfileStep.tsx`
- Create: `frontend/src/components/onboarding/steps/ConsentStep.tsx`
- Create: `frontend/src/components/onboarding/steps/ConfirmStep.tsx`

**Detail per component:**

**AccountStep:**
- Email (readonly, pre-filled from token)
- Password with strength indicator
- Password confirm
- Uses shadcn Input, Label

**ParentProfileStep:**
- First name, Last name (Input)
- Phone (Input, optional)
- Relationship (Select: padre/madre/acudiente)
- Uses shadcn Input, Label, Select

**ConsentStep:**
- Card with explanation of data collected
- 3 mandatory checkboxes with detailed descriptions
- 1 optional checkbox (third parties)
- Link to privacy policy
- Contextualized athlete name
- Uses shadcn Checkbox, Card, Alert

**ConfirmStep:**
- Summary of all entered data (readonly)
- Message: "You will be linked as [relationship] of [athlete] in [club]"
- "Create account" button (final submit)
- Uses shadcn Card, Badge, Button

**Success criterion:** Each component renders and validates independently.
**Dependencies:** Step 9, Step 13
**Estimate:** Large

---

### Step 15: Create `OnboardingWizard` container
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/components/onboarding/OnboardingWizard.tsx`

**Detail:**
- Props: `{ role, tokenData, onComplete }`
- Filters `ONBOARDING_STEPS` by role
- `FormProvider` wrapping (React Hook Form)
- `defaultValues` hydrated from Zustand store
- `handleNext()`: `trigger(fields)` → `updateFormData()` → `setStep(+1)`
- `handleBack()`: `setStep(-1)`
- `handleSubmit()`: on last step, calls `onComplete(formData)`
- Step transition animation (optional, CSS transition)

**Success criterion:** Wizard navigates correctly, validates per step, persists state.
**Dependencies:** Step 10, Step 13, Step 14
**Estimate:** Medium

---

### Step 16: Create `OnboardingPage` and update routes
**Agent:** `react-ui-engineer`
**Files:**
- Create: `frontend/src/routes/auth/OnboardingPage.tsx`
- Create: `frontend/src/components/onboarding/OnboardingSuccess.tsx`
- Modify: `frontend/src/App.tsx` (add route `/onboarding`, redirect `/registro-padre`)

**Detail:**

**OnboardingPage:**
- States: "loading" | "invalid" | "expired" | "wizard" | "success"
- Mount: extracts `?token=`, calls `useValidateToken(token)`
- Loading: skeleton/spinner
- Invalid/Expired: Card with descriptive message + link "Contact the coach"
- Wizard: renders `OnboardingWizard` with `role` and `tokenData`
- onComplete: calls `useCompleteOnboarding()` mutation → "success"

**OnboardingSuccess:**
- Success icon (CheckCircle)
- "Account created successfully!"
- "You can now follow [athlete]'s sports progress"
- "Log in" button → `/login`
- Clear Zustand store (reset)

**App.tsx routes:**
```tsx
<Route path="/onboarding" element={<OnboardingPage />} />
<Route path="/registro-padre" element={<Navigate to="/onboarding" replace />} />
```

**Success criterion:** Complete flow works E2E: URL with token → wizard → registration → success.
**Dependencies:** Step 11, Step 15
**Estimate:** Medium

---

## Phase E — Validation and Cleanup

### Step 17: E2E tests for the complete flow
**Agent:** `quality-engineer`
**Files:**
- Create: `backend/tests/test_onboarding_consent.py`
- Verify: manual E2E flow with Docker Compose

**Scenarios to test:**

| # | Scenario | Expected result |
|---|---|---|
| 1 | Valid token → complete wizard → registration | User + ParentAthlete + ParentalConsent created |
| 2 | Expired token | "Link expired" screen |
| 3 | Already-used token | "Link already used" screen |
| 4 | Invalid/non-existent token | "Invalid link" screen |
| 5 | Already-registered email | 409 error with descriptive message |
| 6 | Incomplete consent (missing mandatory) | Frontend validation blocks progress |
| 7 | Back/forward navigation in wizard | State persisted correctly |
| 8 | Close browser and return to URL | Recovers progress from localStorage |
| 9 | `/registro-padre` redirect | Redirects to `/onboarding` |
| 10 | Successful registration → login → parent dashboard | Complete end-to-end flow |

**Success criterion:** All scenarios pass.
**Dependencies:** All previous steps
**Estimate:** Medium

---

## Dependency Diagram

```
Phase A (Backend)                   Phase B (Backend)       Phase C (Frontend)
                                    
Step 1 ──┬──→ Step 2               Step 7 (parallel)       Step 9 (parallel)
          │                                                  │
          ├──→ Step 4 ──→ Step 5   Step 8 (parallel)       Step 10 (parallel)
          │                                                  │
Step 3 ──┤                                                  Step 11 (parallel)
          │                                                  │
          └──→ Step 6                                       Step 12
                                                             │
                                    Phase D (Frontend)       │
                                                             ▼
                                    Step 13 ──→ Step 14 ──→ Step 15 ──→ Step 16
                                    
                                    Phase E (Validation)
                                    
                                    Step 17 (depends on ALL)
```

### Optimal parallel execution

| Round | Steps | Parallel agents |
|---|---|---|
| **Round 1** | 1, 3, 7, 8, 9, 10 | `fastapi-architect` × 3, `react-ui-engineer` × 2 |
| **Round 2** | 2, 4, 6, 11, 12, 13 | `fastapi-architect` × 3, `react-ui-engineer` × 2 |
| **Round 3** | 5, 14 | `fastapi-architect` × 1, `react-ui-engineer` × 1 |
| **Round 4** | 15, 16 | `react-ui-engineer` × 1 |
| **Round 5** | 17 | `quality-engineer` × 1 |

---

## File Summary

### Create (12 new files)

| # | File | Step |
|---|---|---|
| 1 | `backend/app/models/parental_consent.py` | 1 |
| 2 | `backend/alembic/versions/xxx_add_parental_consents.py` | 2 |
| 3 | `backend/templates/email/parent_invite.html` | 7 |
| 4 | `frontend/src/schemas/onboarding.schema.ts` | 9 |
| 5 | `frontend/src/stores/onboarding-store.ts` | 10 |
| 6 | `frontend/src/hooks/onboarding/useOnboarding.ts` | 11 |
| 7 | `frontend/src/hooks/onboarding/index.ts` | 11 |
| 8 | `frontend/src/components/onboarding/OnboardingStepper.tsx` | 13 |
| 9 | `frontend/src/components/onboarding/onboarding-steps.ts` | 13 |
| 10 | `frontend/src/components/onboarding/steps/AccountStep.tsx` | 14 |
| 11 | `frontend/src/components/onboarding/steps/ParentProfileStep.tsx` | 14 |
| 12 | `frontend/src/components/onboarding/steps/ConsentStep.tsx` | 14 |
| 13 | `frontend/src/components/onboarding/steps/ConfirmStep.tsx` | 14 |
| 14 | `frontend/src/components/onboarding/OnboardingWizard.tsx` | 15 |
| 15 | `frontend/src/routes/auth/OnboardingPage.tsx` | 16 |
| 16 | `frontend/src/components/onboarding/OnboardingSuccess.tsx` | 16 |
| 17 | `backend/tests/test_onboarding_consent.py` | 17 |

### Modify (7 existing files)

| # | File | Step | Change |
|---|---|---|---|
| 1 | `backend/app/models/__init__.py` | 1 | Add ParentalConsent import |
| 2 | `backend/app/schemas/parent_invite.py` | 3 | Add consent schemas + extend request/response |
| 3 | `backend/app/services/invitations.py` | 4 | Extend consume_invite() with consent |
| 4 | `backend/app/routers/auth.py` | 5, 6 | Pass consent to consume_invite, add role/club to response |
| 5 | `backend/app/routers/parent_athletes.py` | 8 | Fix onboarding URL |
| 6 | `frontend/src/api/parents.ts` | 12 | Update payload/response types |
| 7 | `frontend/src/App.tsx` | 16 | Add /onboarding route, redirect /registro-padre |

---

## Phase 1B (Next sprint) — Coach Onboarding

Once Phase 1A (parents) is complete, extend for coaches:

| Step | Description | Agent |
|---|---|---|
| B1 | Create `CoachInvite` model (or generalize `Invitation` with `role` field) | `fastapi-architect` |
| B2 | Endpoints: `POST /api/invitations/coach`, `POST /api/auth/coach-register` | `fastapi-architect` |
| B3 | Create `CoachProfileStep.tsx` (certifications, experience, specialization) | `react-ui-engineer` |
| B4 | Add "coach" to `ONBOARDING_STEPS` config | `react-ui-engineer` |
| B5 | Email template `coach_invite.html` | `fastapi-architect` |
| B6 | Admin UI: "Invite coach" in admin panel | `react-ui-engineer` |

**Key decision Phase 1B:** Generalize `ParentInvite` → `Invitation` with `role` field? Yes, but in Phase 1B to avoid breaking existing functionality now.

---

## Phase 2+ — Athlete Self-Onboarding

For athletes over 16 who register themselves:

| Step | Description |
|---|---|
| C1 | New invitation type: `athlete_self` |
| C2 | `AthleteProfileStep.tsx`: basic sports data |
| C3 | Own consent (>16) vs. parental (<16) — logic by age |
| C4 | Automatic club linkage without parent intermediary |
