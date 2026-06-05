# Research: Invitation-Based Onboarding Flow

**Date:** 2026-04-15
**Depth:** deep
**Sources consulted:** 24

## Executive Summary

The Trocha y Ruta invitation system is **95% implemented on the backend** but has critical gaps in the frontend, email templates, and parental consent. Web research confirms that the current stack (opaque tokens + FastAPI + React Hook Form) is the correct pattern, but security adjustments are needed (token hashing in DB) and a complete parental consent module given that COPPA 2025 enters into force on 22-Apr-2026.

---

## 1. Current Codebase State

### Backend — Implemented ✅

| Component | File | Status |
|---|---|---|
| `ParentInvite` model | `backend/app/models/parent_invite.py` | ✅ Complete |
| Invitations service | `backend/app/services/invitations.py` | ✅ Complete |
| Invitations router | `backend/app/routers/parent_athletes.py` | ✅ Complete |
| Pydantic schemas | `backend/app/schemas/parent_invite.py` | ✅ Complete |
| Auth: validate token | `backend/app/routers/auth.py` — `GET /api/auth/invite/{token}` | ✅ Complete |
| Auth: parent registration | `backend/app/routers/auth.py` — `POST /api/auth/parent-register` | ✅ Complete |
| Alembic migration | `c3d4e5f6a7b8_add_parent_invites_and_consent.py` | ✅ Complete |
| NotificationService | `backend/app/services/notification/` | ✅ Complete |
| Template registry (PARENT_INVITE) | `backend/app/services/notification/template_registry.py` | ✅ Registered |

### Available Backend Endpoints

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| `POST` | `/api/parent-athletes/invite` | Create invitation + send email | Coach/Admin |
| `GET` | `/api/parent-athletes/invites?athlete_id={id}` | List invitations | Coach/Admin |
| `GET` | `/api/auth/invite/{token}` | Validate token | Public |
| `POST` | `/api/auth/parent-register` | Complete parent registration | Public |
| `GET` | `/api/parent-athletes/my-athletes` | Parent portal: my athletes | Parent |

### Frontend — Partially Implemented

| Component | File | Status |
|---|---|---|
| `ParentRegisterPage` | `frontend/src/routes/auth/ParentRegisterPage.tsx` | ✅ Exists |
| `ParentInviteManager` | `frontend/src/components/parents/ParentInviteManager.tsx` | ✅ Exists |
| Invitations API client | `frontend/src/api/parents.ts` | ✅ Exists |
| React Query hooks | `frontend/src/hooks/parents/` | ✅ Exists |
| Route `/onboarding` | `frontend/src/App.tsx` | ❌ **Does not exist** |
| HTML email template | `templates/email/parent_invite.html` | ❌ **Does not exist** |

### Critical Gaps Identified

| # | Issue | Severity | Detail |
|---|---|---|---|
| 1 | **Route mismatch** | 🔴 High | Backend generates URL `/onboarding?token=...` but frontend has `/registro-padre` |
| 2 | **Missing email template** | 🔴 High | `templates/email/parent_invite.html` referenced but does not exist on disk |
| 3 | **No consent workflow** | 🟡 Medium | Columns `parental_consent_obtained/date` in DB but no UI or endpoint |
| 4 | **Token not hashed in DB** | 🟡 Medium | Token stored raw — should be hashed (SHA-256) |
| 5 | **No multi-role onboarding** | 🟡 Medium | Only supports parents. Needs extensibility for future coaches and athletes |
| 6 | **No rate limiting** | 🟢 Low | Public endpoints with no abuse protection |

---

## 2. Web Research: Best Practices

### 2.1 Invitation Tokens — Opaque > JWT

**Confidence: High (95%)**

For single-use invitations, opaque tokens outperform JWT:

| Criterion | JWT | Opaque Token |
|---|---|---|
| Instant revocation | ❌ Requires blacklist | ✅ Delete from DB |
| Readable content | ⚠️ Base64 decodable | ✅ Opaque |
| Native single-use | ❌ Requires state | ✅ Mark in DB |
| Size in URL | ❌ 300-500 bytes | ✅ 43 chars |

**Recommendation:** Keep current `secrets.token_urlsafe(32)` but **hash with SHA-256 before storing**. If the table is compromised, raw tokens cannot be used.

**Sources:**
- [ZITADEL — JWT vs Opaque Tokens](https://zitadel.com/blog/jwt-vs-opaque-tokens)
- [RFC 9700 — OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/rfc9700/)

### 2.2 Multi-Role Onboarding — Branching from Token

**Confidence: High (88%)**

The "persona-based onboarding" pattern is optimal: the token already contains the role, the frontend infers the steps without asking the user.

```
Token validated → role = "parent"  → steps [account, profile, consent, confirmation]
Token validated → role = "coach"   → steps [account, professional profile, terms, confirmation]
Token validated → role = "athlete" → steps [account, sports profile, confirmation] (future)
```

**Declarative step architecture:**

```typescript
type StepConfig = {
  id: string;
  label: string;
  schema: ZodSchema;
  fields: string[];
  roles: UserRole[];
};

const ONBOARDING_STEPS: StepConfig[] = [
  { id: "account",    roles: ["parent", "coach", "athlete"], ... },
  { id: "profile",    roles: ["parent", "coach", "athlete"], ... },
  { id: "consent",    roles: ["parent"],                     ... },
  { id: "coach-bio",  roles: ["coach"],                      ... },
  { id: "confirm",    roles: ["parent", "coach", "athlete"], ... },
];

// Runtime: filter by role
const visibleSteps = ONBOARDING_STEPS.filter(s => s.roles.includes(userRole));
```

**Sources:**
- [DesignerUp — 14 Types of Onboarding UX](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/)
- [Appcues — Choosing the Right Onboarding Pattern](https://www.appcues.com/blog/choosing-the-right-onboarding-ux-pattern)

### 2.3 Parental Consent — COPPA 2025

**Confidence: Very High (95%) — Critical**

COPPA 2025 enters into force **April 22, 2026** (in 7 days). Trocha y Ruta collects data from athletes aged 10-15 → applies.

> **Jurisdictional note:** COPPA is a US federal law. For Colombia, Ley 1581 de 2012 (Habeas Data) and Ley 1098 (Código de Infancia) impose similar obligations. Implementing COPPA standards is international best practice.

**Requirements for the app:**

1. **Direct notice to parents** before collecting minors' data:
   - What data is collected (name, date of birth, anthropometric measurements)
   - How it is used (sports tracking, PHV calculation)
   - If shared with third parties (Intervals.icu, Google Sheets)
   - Retention period

2. **Recommended verifiable consent method:**
   - **Digital wizard** with explicit checkboxes per data category (MVP)
   - **Text-Plus** (SMS OTP) as second factor (Phase 2)

3. **`parental_consents` table** with versioning:

```python
class ParentalConsent(Base):
    __tablename__ = "parental_consents"
    id: Mapped[int]
    parent_user_id: Mapped[int]       # FK users
    athlete_id: Mapped[int]           # FK athletes
    consent_version: Mapped[str]      # "v1.0"
    consented_at: Mapped[datetime]
    consent_method: Mapped[str]       # "digital_wizard" | "signed_doc"
    ip_address: Mapped[str | None]
    data_uses_accepted: Mapped[dict]  # JSON: {training: true, third_party: false}
    withdrawn_at: Mapped[datetime | None]
```

4. **Ongoing parental controls:**
   - View what data is held on their child
   - Revoke consent
   - Request deletion

**Sources:**
- [FTC — COPPA Rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa)
- [Loeb & Loeb — COPPA 2025 Amendments](https://www.loeb.com/en/insights/publications/2025/05/childrens-online-privacy-in-2025-the-amended-coppa-rule)
- [Securiti — FTC COPPA Final Rule](https://securiti.ai/ftc-coppa-final-rule-amendments/)

### 2.4 Frontend Stack for Multi-Step Wizard

**Confidence: High (92%)**

Recommended stack: **React Hook Form v7 + Zod + Zustand persist + shadcn/ui**

**Key pattern — per-step validation with `trigger()`:**

```typescript
const handleNext = async () => {
  const currentStepFields = ONBOARDING_STEPS[currentStep].fields;
  const isValid = await methods.trigger(currentStepFields);
  if (!isValid) return;
  store.updateFormData(methods.getValues());
  setCurrentStep(prev => prev + 1);
};
```

**Persistence:** `zustand/persist` + `localStorage` allows progress recovery if the user closes the browser. Verify token is valid before restoring state.

**Stepper UI:** shadcn/ui has no official Stepper. Options:
1. Build simple stepper with shadcn primitives (recommended for full control)
2. SmartStepper npm package (compatible with RHF + Zod)

**Sources:**
- [LogRocket — Multi-Step Form RHF + Zod](https://blog.logrocket.com/building-reusable-multi-step-form-react-hook-form-zod/)
- [Build with Matija — Zustand + Zod + shadcn](https://www.buildwithmatija.com/blog/master-multi-step-forms-build-a-dynamic-react-form-in-6-simple-steps)
- [React Hook Form — Advanced Usage (trigger)](https://react-hook-form.com/advanced-usage)

### 2.5 FastAPI Architecture — E2E Flow

**Confidence: High (90%)**

```
Coach/Admin                 Backend FastAPI              Frontend React
    |                            |                            |
    |-- POST /invite ----------->|                            |
    |                            |-- generates token + hash   |
    |                            |-- saves hash in DB         |
    |                            |-- email with raw token --->|
    |                            |                    click on link
    |                            |<-- GET /invite/validate?token=xxx
    |                            |-- hash(token), lookup in DB|
    |                            |-- returns {email, role} -->|
    |                            |              multi-step wizard
    |                            |<-- POST /invite/accept
    |                            |-- atomic transaction:      |
    |                            |   creates user + relations |
    |                            |   records consent          |
    |                            |   marks token used         |
    |                            |-- returns JWT session ---->|
    |                            |              redirects to dashboard
```

**Recommended rate limiting (Redis + slowapi):**

| Endpoint | Limit | Per |
|---|---|---|
| `POST /invite` | 10/hour | Authenticated user |
| `GET /invite/validate` | 20/hour | IP |
| `POST /invite/accept` | 5/hour | IP |

**Sources:**
- [Scalekit — FastAPI Passwordless Auth](https://www.scalekit.com/blog/fastapi-passwordless-magic-link-otp-implementation)
- [Upstash — Rate Limiting FastAPI](https://upstash.com/docs/redis/tutorials/python_rate_limiting)

---

## 3. Contradictions and Nuances

- **Token hashing:** The current codebase stores tokens raw. Best practice is to hash them. However, the current system already works and the risk is low for a local sports club. **Recommendation:** implement hashing in this iteration as a security improvement.
- **COPPA jurisdiction:** COPPA is US law, not Colombian. But Colombian Ley 1581 has similar principles. Implementing the COPPA standard is over-engineering from a legal standpoint, but it is the best protection for minors.
- **Stepper component:** There is no consensus on using a library vs. building your own. For full control + integration with shadcn/ui, building your own is preferable.

## 4. Knowledge Gaps

1. **Specific Colombian law for sports apps with minors** — requires legal consultation, not web research
2. **SMTP/transactional provider** (SendGrid, AWS SES, Resend) — separate infrastructure decision
3. **Onboarding flow for athletes >16 years old** — not researched in depth (Phase 2+)

## 5. Prioritized Recommendations

### Priority 1 — Fix what is broken
1. Fix route mismatch: unify at `/onboarding`
2. Create email template `parent_invite.html`
3. Convert `ParentRegisterPage` into a multi-step wizard

### Priority 2 — Complete functionality
4. Implement parental consent (table + UI)
5. Token hashing in DB (SHA-256)
6. Generalize invitation model for multi-role

### Priority 3 — Hardening
7. Rate limiting on public endpoints
8. Privacy dashboard for parents
9. Wizard progress persistence (Zustand)

---

## Full Sources

### Tokens and Security
1. [ZITADEL — JWT vs Opaque Tokens](https://zitadel.com/blog/jwt-vs-opaque-tokens) — High
2. [Permit.io — Bearer Tokens Guide](https://www.permit.io/blog/a-guide-to-bearer-tokens-jwt-vs-opaque-tokens) — High
3. [RFC 9700 — OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/rfc9700/) — Very High
4. [DZone — API Access Token Best Practices](https://dzone.com/articles/security-best-practices-for-managing-api-access-to) — Medium

### FastAPI
5. [Scalekit — FastAPI Passwordless Auth](https://www.scalekit.com/blog/fastapi-passwordless-magic-link-otp-implementation) — High
6. [Upstash — Rate Limiting FastAPI](https://upstash.com/docs/redis/tutorials/python_rate_limiting) — High
7. [Bryan Anthonio — FastAPI Rate Limiter Redis](https://bryananthonio.com/blog/implementing-rate-limiter-fastapi-redis/) — Medium

### React Multi-Step Forms
8. [LogRocket — Multi-Step Form RHF + Zod](https://blog.logrocket.com/building-reusable-multi-step-form-react-hook-form-zod/) — High
9. [Build with Matija — Zustand + Zod + shadcn](https://www.buildwithmatija.com/blog/master-multi-step-forms-build-a-dynamic-react-form-in-6-simple-steps) — High
10. [React Hook Form — Advanced Usage](https://react-hook-form.com/advanced-usage) — Very High
11. [ClarityDev — Multistep Form](https://claritydev.net/blog/build-a-multistep-form-with-react-hook-form) — Medium

### COPPA and Privacy
12. [FTC — COPPA Rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa) — Very High
13. [Loeb & Loeb — COPPA 2025](https://www.loeb.com/en/insights/publications/2025/05/childrens-online-privacy-in-2025-the-amended-coppa-rule) — High
14. [Securiti — COPPA Amendments](https://securiti.ai/ftc-coppa-final-rule-amendments/) — High

### UX Onboarding
15. [Appcues — Onboarding UX Patterns](https://www.appcues.com/blog/choosing-the-right-onboarding-ux-pattern) — High
16. [DesignerUp — 14 Types of Onboarding UX](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/) — High
