<!--
Sync Impact Report
==================
Version change: 1.1.0 → 1.2.0
Rationale: MINOR amendment. A new domain principle (V. Youth Psychological Assessment
Safeguards) is ADDED for the Competitive Anxiety Assessment feature (CSAI-2R / SAS-2 /
CSAI-2). It is additive and does not remove, renumber, or redefine principles I–IV; it
is fully consistent with the existing minors-privacy and UX constraints → MINOR.

Amendment 2026-06-23 (1.1.0 → 1.2.0):
  - Added Principle V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE):
    age-driven instrument selection (SAS-2 forced/suggested for <13; CSAI-2R default
    for 13–15; CSAI-2 import-only); wellbeing-not-diagnosis; baseline-anchored
    interpretation; mastery climate; human-in-the-loop (no auto-messaging to
    athletes/parents); calendar-tied Race-A administration. Verification gates:
    item-by-item answer persistence, rule-based interpretation fallback, guardian
    consent + coach-only access, minors-privacy/data minimization. Sourced from
    Section 1 of the "Componente Ansiedad Competitiva (CSAI-2R)" Spec Kit package.

Amendment 2026-06-05 (1.0.0 → 1.1.0):
  - III. User Experience Consistency → language clause split into "product end-user
    copy = español neutro (Colombia)" and "AI dev-assistant working language +
    instruction corpus (CLAUDE.md, .claude/agents/*, docs/**) = English". Resolves the
    contradiction surfaced by feature 001-translate-claude-files-english.

Initial ratification 2026-06-01 (TEMPLATE → 1.0.0):
  - Principles I–IV adopted (I. Code Quality, II. Testing NON-NEGOTIABLE,
    III. UX Consistency, IV. Performance). Fifth principle slot intentionally omitted.
  - Added sections: Quality Gates & Compliance Constraints; Development Workflow &
    Review Process; Governance.

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — generic "Constitution Check" gate; the
    gate references this file, so Principle V is picked up automatically; no edit needed.
  - ✅ .specify/templates/spec-template.md — aligned; no edit needed.
  - ✅ .specify/templates/tasks-template.md — aligned; no edit needed.
  - ✅ .claude/agents/mental-performance-coach.md — updated in the same change with the
    Competitive Anxiety Assessment domain (instruments, scoring, baseline-anchored
    interpretation, hard safeguards) so the agent enforces Principle V.

Follow-up TODOs:
  - None for this amendment. The CSAI-2R feature spec (Section 2 of the package) is the
    next step via /speckit.specify.
-->

# Club Deportivo Trocha y Ruta Constitution

## Core Principles

### I. Code Quality & Maintainability

Every change MUST leave the codebase at least as readable and as well-structured as it
found it. Concretely:

- Code MUST pass the project linters and type checkers before merge (backend: `ruff` +
  `mypy` where configured; frontend: `eslint` + `tsc --noEmit`). A failing check is a
  blocker, never a follow-up ticket.
- Functions and components MUST be named for what they produce, not how they do it; if
  a reader needs a comment to know what a symbol does, rename the symbol first and add
  the comment only when the *why* is non-obvious.
- Duplication MUST be removed when a third copy appears (rule of three). Premature
  abstraction is also a defect — two similar blocks may stay.
- Pull requests MUST be reviewed by at least one human reviewer other than the author
  before merge to `main`. AI-only review does not satisfy this rule.
- Public modules (`backend/app/services/**`, shared frontend hooks, schemas) MUST have
  docstrings or short README notes describing inputs, outputs, and side effects.

**Rationale**: This project is maintained by a small team and assisted by AI. Readable,
typed, linted code is the only durable defense against regressions in a codebase that
multiple agents and humans modify concurrently.

### II. Testing Standards (NON-NEGOTIABLE)

Tests are part of the deliverable, not an optional follow-up.

- Backend changes MUST add or update `pytest` tests using `httpx.AsyncClient` against
  the FastAPI app and `aiosqlite` (or the real engine where required). Routers,
  services, and permission logic each require at least one test covering the happy
  path and at least one negative path (auth denied, validation error, or conflict).
- Frontend changes MUST add or update `vitest` + Testing Library tests for components
  with branching logic, hooks, and pages. Pure presentational components without
  branching are exempt.
- Accessibility MUST be exercised by `jest-axe` (or equivalent) on every page-level
  and dialog-level component; zero violations is required to merge.
- Any bug fix MUST land with a regression test that fails on the unfixed code and
  passes on the fix. No exceptions.
- Test suites MUST be deterministic. Flaky tests MUST be either fixed or quarantined
  with an open ticket within the same PR that observes the flake; silent skips are
  forbidden.
- Tests for code that handles minors' data MUST include explicit privacy invariants
  (no name leakage in responses, no PII in logs, consent gates honored).

**Rationale**: This is a juvenile-athlete platform. Untested code is a privacy and
safety risk, not just a quality risk. Regression tests for bug fixes prevent the same
incident from happening twice.

### III. User Experience Consistency

The product serves two distinct users — coaches (tablet, on the field) and parents
(mobile Android, intermittent 3G/4G). Consistency across both surfaces is mandatory.

- **Language policy**: A single, non-contradictory policy governs language across the
  project. **Product end-user copy** — anything a coach or parent reads in the running
  product (frontend UI strings, backend Jinja email/PDF templates, notification bodies)
  — MUST be in español neutro (Colombia), with full diacritics, and MUST avoid clinical
  or judgmental language about minors. **The AI development assistant's working
  language** — the assistant's reasoning and replies to the developer, plus the
  AI-facing instruction and documentation corpus (`CLAUDE.md`, `.claude/agents/*`,
  `docs/**`) — is **English**, to maximize prompt-engineering quality. Translating that
  instruction corpus to English MUST NOT change the language of any product end-user
  copy.
- UI components MUST be sourced from the shared `shadcn/ui` + Tailwind system already
  in `frontend/src/components`. Introducing a new component pattern requires a written
  justification in the PR description and a reusable location under `components/`.
- Forms MUST use React Hook Form + Zod with inline, localized error messages. Native
  HTML5 validation MUST NOT compete with Zod validation on the same field.
- Interactive targets MUST be at least 48×48 px on touch surfaces. Modal/sheet dialogs
  MUST trap focus and be dismissible by Escape and by an explicit close affordance.
- Loading, empty, and error states MUST be designed for every async surface — no
  unbounded spinners, no silent failures, no raw exception text shown to users.
- Color, badge, and status semantics MUST be consistent across the app: green =
  success/complete, amber = partial/attention, red = error/blocking, neutral gray =
  informational. Re-using these tokens for other meanings is a violation.
- WCAG 2.1 AA is the floor. Contrast, focus rings, and keyboard navigability are
  non-negotiable.

**Rationale**: Coaches use the app outdoors with gloves and sweat; parents use it on
modest Android phones with patchy reception. Consistency reduces cognitive load,
training cost, and support tickets, and accessibility is both a legal and ethical
baseline.

### IV. Performance Requirements

Performance budgets are part of the contract, not an aspiration.

- Backend API endpoints MUST respond within **p95 ≤ 500 ms** for cached/cold-warmed
  reads and **p95 ≤ 1500 ms** for transactional writes, measured against MySQL
  Hostinger in production. Endpoints that knowingly exceed these MUST document the
  budget exception in the route docstring and the plan's Complexity Tracking section.
- Database queries MUST avoid N+1 patterns. Any list endpoint returning related
  entities MUST eager-load via `selectinload` / `joinedload` or batch via explicit
  queries, and MUST be covered by a test that asserts query count or measured time.
- Frontend route bundles MUST stay under **250 KB gzipped** for the initial route
  and **150 KB gzipped** per additional lazy route. Bundle regressions ≥10% MUST be
  justified in the PR.
- Largest Contentful Paint (LCP) on a mid-tier Android device over simulated 3G MUST
  be ≤ **2.5 s** for the dashboard and athlete-list routes; ≤ **3.5 s** for
  data-dense routes (calendar, results, newsletters).
- Heavy components (charts, large tables, AI editors) MUST be lazy-loaded via
  `React.lazy` + Suspense. Static imports of >50 KB modules into shared layouts
  are a violation.
- Render's free-tier cold start (~50 s) MUST be assumed; the frontend MUST surface a
  clear "starting the server" state instead of a generic spinner or timeout error.

**Rationale**: Users access this product from rural Valle del Cauca on shared
Android phones over intermittent connections; the backend runs on a free Render tier
that is bandwidth- and CPU-constrained. Without explicit budgets, the product will
silently degrade for the very users it exists to serve.

### V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE)

Any feature that administers, scores, stores, or interprets psychological instruments for
minors — beginning with the Competitive Anxiety Assessment module (CSAI-2R / SAS-2 /
CSAI-2) — MUST uphold the following. These are domain safety rules; they complement, and
never override, Principles I–IV.

- **Age-driven instrument selection.** The instrument MUST be selected by the athlete's
  age band: SAS-2 (15 items) for ages 10–12, CSAI-2R (17 items, default) for ages 13–15,
  and CSAI-2 (27 items) supported ONLY to import/interpret historical results. The system
  MUST suggest/force SAS-2 for athletes under 13 and MUST warn when CSAI-2/2R is applied
  to that age (below its validated range). Item content and the item→subscale key MUST
  come from the licensed official source — items MUST NOT be invented.
- **Wellbeing tool, NOT a diagnosis.** No generated output MAY label an athlete with an
  "anxiety disorder" or any clinical condition. Extreme or persistent signals MUST raise
  a flag that recommends a conversation and, if it persists, referral to a health
  professional.
- **Baseline-anchored interpretation.** The CSAI-2 family measures intensity and has no
  universal clinical cutoffs. Interpretation MUST be anchored to the athlete's own
  baseline (established in April) and MAY use perceived direction (facilitative vs.
  debilitative). Absolute low/moderate/high bands are coarse guidance only and MUST NOT
  be presented as diagnostic thresholds.
- **Mastery climate always.** Every generated recommendation and athlete-facing message
  MUST be framed in process, effort, and coping strategies — never in results/podiums,
  rankings, or shaming comparisons between athletes.
- **Human in the loop.** The module informs the coach's conversation only. It MUST NOT
  send automatic messages to athletes or parents.
- **Calendar-tied administration.** The instrument is administered ~1–2 h before Race A
  events (IV Válida–Cali, Departamental–Ginebra, VI Válida–Roldanillo), where competitive
  pressure is highest.
- **Verification gates.** Item-by-item answers MUST be persisted (not only subscale
  scores) so scores can be recomputed; a rule-based interpretation fallback MUST exist
  for when the LLM is unavailable; access MUST be restricted to the coach and gated by
  registered guardian consent; minors-privacy and data minimization (Principle-level
  Quality Gates) apply in full, including to any AI-provider prompt.

**Rationale**: These are children in an identity-development stage, sensitive to social
comparison and external pressure. A psychological instrument misused as a diagnostic
label, or interpreted against population cutoffs instead of the child's own trajectory,
can cause real harm. Encoding these as non-negotiable principles keeps the feature a
supportive, coach-mediated wellbeing tool rather than an amateur clinical screen.

## Quality Gates & Compliance Constraints

These constraints apply across all principles and complement the project's existing
non-negotiables in `CLAUDE.md`.

- **Privacy (Ley 1581 — minors)**: No name, date of birth, medical detail, photo, or
  identifying metadata of a minor MUST appear in logs, error messages, commit
  messages, PR descriptions, public docs, fixtures committed to git, or any
  third-party service prompt (including AI providers). The `data-privacy-guard`
  audit is mandatory for any feature that reads or writes athlete-identifiable data.
- **Stack discipline**: New features MUST use the agreed stack — FastAPI +
  SQLAlchemy 2 async + Alembic + MySQL 8.4 (backend); React 19 + Vite + shadcn/ui +
  Tailwind + TanStack Query + Zustand + RHF + Zod (frontend). Adding a new runtime
  dependency requires written justification in the plan.
- **Security**: Authentication uses JWT (access + refresh) via `PyJWT` + `bcrypt`.
  RBAC checks MUST live in `services/permissions.py` or equivalent and MUST be
  exercised by tests. File uploads MUST validate magic bytes (not extensions) and
  strip EXIF before storage.
- **AI features**: Any AI-generated content about a minor MUST run through the
  documented guardrails (forbidden-names list from DB, word limits, term redaction,
  consent gate). `AI_LOG_PROMPTS` MUST remain `false` in production. Property tests
  MUST assert that real names never appear in AI output.
- **Observability**: Errors MUST be logged with correlation IDs and never with
  request/response bodies that may contain PII. Structured logs are required for
  any new long-running task or background job.

## Development Workflow & Review Process

- **Conventional Commits** (per `~/.claude/rules/git-conventions.md`): type in
  English, description in español latino. Breaking changes use `!`. Commits MUST NOT
  reference Claude Code or any AI tool.
- **Branching**: Feature work happens on branches named `<type>/<short-slug>`
  (e.g., `feat/season-panorama`). Direct commits to `main` are reserved for
  emergency fixes and MUST be followed by a retroactive PR description.
- **Pre-merge gate**: Lint, type-check, backend `pytest`, frontend `vitest`, and
  accessibility tests MUST all pass. A green CI is necessary but not sufficient — a
  human reviewer MUST also confirm Principles I–V are upheld.
- **Constitution Check (in `/speckit-plan`)**: Every implementation plan MUST list
  how it satisfies each of the five principles. Violations MUST be entered in the
  Complexity Tracking table with a justification and an explicitly rejected simpler
  alternative.
- **Deploys**: Backend auto-deploys to Render on push to `main`. The release MUST
  include a post-deploy smoke check of `/health` and one representative authenticated
  endpoint, plus visual confirmation that the dashboard route loads on a real device
  within the LCP budget defined in Principle IV.

## Governance

- This constitution supersedes ad-hoc conventions in code comments, READMEs, and
  agent prompts. Where a project document conflicts with this constitution, this
  document wins until amended.
- **Amendment procedure**: Amendments are proposed via a pull request that (a) edits
  this file, (b) updates the Sync Impact Report comment at the top, and (c) updates
  any templates flagged as affected. Amendments require approval from the project
  owner before merge.
- **Versioning policy**: This constitution follows semantic versioning.
  - MAJOR: a principle is removed, renumbered, or redefined in a way that
    invalidates prior compliance.
  - MINOR: a new principle or section is added, or guidance is materially expanded.
  - PATCH: clarifications, wording, typo fixes, or non-semantic refinements.
- **Compliance review**: Every PR description MUST contain a one-line statement
  confirming compliance with the five principles, or list the violations and link
  to the plan's Complexity Tracking entry. PRs that omit this statement MUST be
  requested-changes by the reviewer.
- **Runtime guidance**: `CLAUDE.md` at the project root is the authoritative runtime
  guidance file for AI-assisted development and is informative-but-binding alongside
  this constitution.

**Version**: 1.2.0 | **Ratified**: 2026-06-01 | **Last Amended**: 2026-06-23
