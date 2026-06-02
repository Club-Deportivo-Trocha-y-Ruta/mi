<!--
Sync Impact Report
==================
Version change: TEMPLATE (uninitialized placeholders) → 1.0.0
Rationale: Initial ratification. Project transitions from unfilled template to first
adopted constitution; semver baseline begins at 1.0.0 per governance policy.

Modified principles:
  - [PRINCIPLE_1_NAME] → I. Code Quality & Maintainability
  - [PRINCIPLE_2_NAME] → II. Testing Standards (NON-NEGOTIABLE)
  - [PRINCIPLE_3_NAME] → III. User Experience Consistency
  - [PRINCIPLE_4_NAME] → IV. Performance Requirements
  - [PRINCIPLE_5_NAME] → REMOVED (user scoped to four principles)

Added sections:
  - Quality Gates & Compliance Constraints (privacy, stack, accessibility, security)
  - Development Workflow & Review Process
  - Governance

Removed sections:
  - Fifth principle slot (intentionally omitted per user scope)

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — "Constitution Check" section will be
    populated by /speckit-plan against these four principles. No structural edit
    required; the gate placeholder remains generic and will reference this file.
  - ✅ .specify/templates/spec-template.md — Aligned. Success Criteria section
    already supports measurable, technology-agnostic outcomes required by
    Principle IV.
  - ✅ .specify/templates/tasks-template.md — Aligned. "Tests" guidance in this
    template marks tests OPTIONAL; Principle II overrides this for code that
    ships, requiring tests for any merged change. The template's optionality
    refers to whether to include a separate Test phase, not whether to test.
  - ✅ CLAUDE.md (project) — No edit required; existing CLAUDE.md already
    encodes stricter operational policies (privacy, accessibility, stack)
    that act as informative context complementing this constitution.

Follow-up TODOs:
  - None. All placeholders resolved with concrete values.
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

- All user-facing copy MUST be in español neutro (Colombia), with full diacritics, and
  MUST avoid clinical or judgmental language about minors.
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
  human reviewer MUST also confirm Principles I–IV are upheld.
- **Constitution Check (in `/speckit-plan`)**: Every implementation plan MUST list
  how it satisfies each of the four principles. Violations MUST be entered in the
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
  confirming compliance with the four principles, or list the violations and link
  to the plan's Complexity Tracking entry. PRs that omit this statement MUST be
  requested-changes by the reviewer.
- **Runtime guidance**: `CLAUDE.md` at the project root is the authoritative runtime
  guidance file for AI-assisted development and is informative-but-binding alongside
  this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-06-01 | **Last Amended**: 2026-06-01
