# E2E Tests — Monthly Technical Report Module

This document describes the end-to-end (E2E) tests for the **Monthly Technical
Report** module (refactor of the monthly club report), how to run them, and when
to use each mode.

There are two E2E modes for this module:

1. **Mocked E2E (Playwright + `page.route`)** — no backend, no network, fast
   and deterministic. These live in `frontend/e2e/monthly-technical-report-*.spec.ts`.
2. **Full-stack E2E (manual, against real backend)** — Docker Compose + seed +
   `AI_PROVIDER=fake`. Checklist at the end of this document.

---

## 1. Mocked E2E (Playwright)

### Files

| File | Coverage |
|---|---|
| `frontend/e2e/monthly-technical-report-coach.spec.ts` | Coach view: list, detail (7 blocks, metrics, competition), edit+save block (PATCH), regenerate block (POST), approve (PATCH status), download PDF (GET blob), project profile (PUT). |
| `frontend/e2e/monthly-technical-report-parent.spec.ts` | Privacy: the parent **cannot** access the report route (`[coach, admin]`); via direct URL they are redirected to `/my-athletes` and cannot see metrics, editors, Approve, PDF, or competition. |

### How They Work

- **No real backend.** All `**/api/...` endpoints are intercepted with
  `page.route(...)` and return deterministic fixtures. A mutable `state` object
  counts calls (`patchCalls`, `regenerateCalls`, `pdfCalls`, `putCalls`) and
  mutates the resource (e.g. on approve, `status` changes to `"approved"`; on
  regenerate, `ai_draft` changes).
- **Injected session.** `setupAuth(page)` writes the Zustand session to
  `sessionStorage` under the key `"auth-session"` (format
  `{state:{accessToken,refreshToken,user,isAuthenticated,isLoading},version:0}`),
  bypassing the UI login flow. The coach user has `role:"coach"` and
  `club_ids:[1]`; the parent has `role:"parent"` and `club_ids:[1]`.
- **Fixtures without real minors' data.** Fictional names such as
  "Valentina Garcia" / "Mateo Lopez" / "Madre Ficticia". No real TyR athlete data.
- **Parent privacy contract.** The Monthly Technical Report is an **internal**
  document for the technical team (coach/admin). The route
  `/training/reports/:year/:month` is protected with `allowedRoles
  [coach, admin]` and the sidebar link is also hidden from parents, so a
  parent who enters via direct URL is redirected to `/my-athletes` (see
  `ProtectedRoute`). The parent E2E validates that expulsion + the total
  absence of report UI. The parent mock is kept as a defensive net in case
  the SPA prefetches before resolving the guard.

  > Note (2026-06-03): `ReportDetailPage` no longer has a parent view. The
  > parent branch (`ParentReadOnlyView`) was unreachable due to routing/nav and
  > was removed; the entry point fallback is now a neutral "Report not
  > available" state for the only real defensive case (coach/admin with no
  > assigned sports club). Its dead-path unit test was replaced with one for the
  > new fallback.

### Requirements to Run (network environment)

The browser (Chromium) must be installed. In this repository the binary is
**not** versioned and the CI/sandbox container without network **cannot**
download it. To run in a networked environment:

```bash
cd frontend
npx playwright install chromium    # downloads the Chromium shell (requires network)
npm run test:e2e                    # runs the entire e2e/ folder
```

The `webServer` in `playwright.config.ts` automatically starts
`npm run dev -- --port 5173` (Vite dev at `http://localhost:5173`, which is the
`baseURL`). **No need** to start Vite manually: Playwright manages it and
reuses an existing instance outside CI (`reuseExistingServer`).

To run only this module:

```bash
cd frontend
npx playwright test e2e/monthly-technical-report-coach.spec.ts e2e/monthly-technical-report-parent.spec.ts
```

To point to a system Chromium without downloading (restricted environment):

```bash
PLAYWRIGHT_CHROMIUM_PATH=/path/to/chromium npm run test:e2e
```

(`playwright.config.ts` uses `executablePath` when that variable is defined.)

### Quick Validation Without Browser (offline smoke)

As a fast check — or in an environment without Chromium — you can verify that
the specs compile and collect (TypeScript + Playwright parsing) without
launching the browser:

```bash
cd frontend
npx playwright test --list e2e/monthly-technical-report-*.spec.ts
```

Expected output (8 tests, 2 files):

```
Listing tests:
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-001 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-002 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-003 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-004 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-005 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-006 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-007 ...
  [chromium] › monthly-technical-report-parent.spec.ts › ... › ITR-008 ...
Total: 8 tests in 2 files
```

### Scenario Map

| ID | Role | Scenario |
|---|---|---|
| ITR-001 | coach | List shows status badge + "Project data" link. |
| ITR-002 | coach | Detail: 7 editors in order, metrics table, competition table. |
| ITR-003 | coach | Edit `final_text` + Save → `PATCH .../blocks` (count + body). |
| ITR-004 | coach | Regenerate block → `POST .../regenerate` (count + `ai_draft` changes). |
| ITR-005 | coach | Approve → `PATCH status=approved`; "Approved" badge; editors disabled. |
| ITR-006 | coach | Download PDF → `GET .../pdf` blob `application/pdf`; no UI break. |
| ITR-007 | coach | Project profile: fill in, add/remove goal, Save → `PUT`. |
| ITR-008 | parent | Privacy: via direct URL redirected to `/my-athletes`; no metrics, no editors, no Approve, no PDF, no competition. |

---

## 2. Difference from Full-Stack E2E and When to Use Each

| | Mocked E2E (`page.route`) | Full-stack E2E (Docker + seed) |
|---|---|---|
| **Backend** | None. Endpoints intercepted. | Real FastAPI (`docker compose up`). |
| **DB** | None. | MySQL with seeded data (seed). |
| **AI** | Fixed responses in fixture. | `AI_PROVIDER=fake` (or real under control). |
| **Network** | Not required. | Requires stack running. |
| **Speed / flakiness** | Fast and deterministic. | Slower; sensitive to DB state. |
| **What they validate** | Route wiring + UI + API contract (request/response shape) + privacy invariants in the UI. | The real system end-to-end: metrics calculation, AI generation with guardrails, persistence, RBAC in the backend, real PDF. |

**When to use which:**

- **Mocked** — on every PR / frontend CI. Verify that the UI calls the correct
  endpoints with the correct payloads and renders/hides what it should based on
  role. These are the first line of defense against UI regressions and against
  privacy leaks in the parent view.
- **Full-stack manual** — before a module deployment, or after changes to the
  backend (metrics service, block builder, AI generation, PDF). Validate that
  real data flows correctly and that the generated PDF matches the target report.
  Use the checklist in section 3.

> Important: mocked E2E tests **do not** replace unit tests (vitest) or backend
> tests (pytest). Contract coverage, negative RBAC, and AI guardrails live there;
> the mocked E2E validates UI assembly.

---

## 3. MANUAL E2E Checklist (full-stack against real backend)

Goal: validate the module end-to-end with seeded data from **a closed month**
(all sessions from the period already executed/recorded).

### Environment Preparation

- [ ] Start the stack: `docker compose up` (applies migrations + seed).
- [ ] Confirm `APP_ENV=development` so the seed runs.
- [ ] Set `AI_PROVIDER=fake` (or `AI_ENABLED=false` to validate the path
      without AI) — **do not** use the real Gemini API in routine manual testing.
- [ ] Verify `AI_LOG_PROMPTS=false` and `NOTIFICATION_LOG_BODIES=false`
      (mandatory: minors privacy).
- [ ] Log in as coach (`entrenador@trochyruta.com` / `Coach2026!`).

### Seed Data for a Closed Month (via UI or seed)

- [ ] Record several **training sessions** for the month with `session_kind` and `objectives`.
- [ ] Record **attendance** per athlete (present/late/excused/absent/injured).
- [ ] Record **rubrics** (effort / attitude / technique) for executed sessions.
- [ ] Upload at least one **consented photo** to a session (`consent_ack`).
- [ ] Record the **result of a round** from the month (Copa Valle) to have
      `competition_results`.

### Project Data

- [ ] Go to **/training/reports → "Project data"**.
- [ ] Fill in name, executing entity, responsible person, purpose, general goal,
      territory.
- [ ] Add 2-3 **specific goals**; remove one; mentally reorder.
- [ ] Save → confirm success message and that it persists after reloading (PUT OK).

### Generate the Report

- [ ] In **/training/reports**, "Generate report" for the closed month (year/month).
- [ ] Confirm redirect to detail `/training/reports/{year}/{month}`.
- [ ] Verify **metrics**: executed/cancelled sessions, attendance per
      athlete, totals by status, rubric averages, technical focus areas.
- [ ] Verify that the **7 narrative blocks** appear in order:
      objetivo, desarrollo, resultados, conclusiones, apoyos_materiales,
      analisis_grupo, competencia.
- [ ] Verify the **competition table** with the round result.

### Edit / Regenerate / Approve Blocks

- [ ] Edit the `final_text` of a block and **Save** → confirm "Saved".
- [ ] **Regenerate** a block with AI → confirm that `ai_draft` changes and that
      the banner "AI-generated text — review it before approving" appears.
- [ ] Confirm AI guardrails: no proper names of minors in the text,
      no individual judgments, within the length limit.
- [ ] **Approve** the report → badge changes to "Approved"; editors become
      disabled (cannot edit or regenerate after approving).

### PDF

- [ ] **Download PDF** from the detail view → confirm `Content-Type: application/pdf`.
- [ ] Open the PDF and **compare it with the target report**: project header,
      metrics, narrative blocks, anthropometry (if applicable) only in the PDF,
      competition results, Ley 1581 footer.
- [ ] Confirm the file name is `informe-tecnico-{year}-{MM}.pdf`.

### Privacy — Parent View

- [ ] Logout and log in as parent (`padre@trochayruta.com` / `Parent2026!`).
- [ ] Confirm the parent sidebar **does not** show access to Reports /
      `/training/reports`.
- [ ] Try to enter via direct URL `/training/reports/{year}/{month}` →
      confirm **redirect to `/my-athletes`** (the report is internal to the sports club).
- [ ] Confirm the parent **does NOT see** anything from the report: metrics, block
      editors, Approve button, PDF download, or competition table.
- [ ] (Backend defense in depth) If the report endpoint is queried as a parent,
      confirm that `narrative_blocks` and `competition_results` arrive as
      `null` and that only their own athletes' metrics are exposed.

---

## 4. Validation Status

All 8 specs **actually run** with Chromium against the Vite dev server
(`webServer` in `playwright.config.ts`, without a real backend): **8/8 green**
(~2.5s). `npx tsc --noEmit` remains clean.

The first real run (which the prior `--list`-only validation could not detect)
revealed **2 selector/premise failures**, already fixed:

- **ITR-001** — `getByText("Borrador").first()` was picking the first DOM match,
  which is the mobile card (`ul md:hidden`), hidden in the viewport by
  default (1280px). Fixed with `.filter({ visible: true }).first()` to
  target the visible variant (desktop table).
- **ITR-008** — the spec assumed the parent saw a `ParentReadOnlyView` with
  metrics at `/training/reports/:year/:month`. In reality the app blocks parents
  from that route consistently (guard `[coach, admin]` + hidden nav link)
  and redirects them to `/my-athletes`. Rewritten to assert that expulsion
  as a privacy invariant (without changing the app). See the dead-code note
  about `ParentReadOnlyView` in section 1.

To reproduce:

```bash
cd frontend
npx playwright test e2e/monthly-technical-report-coach.spec.ts e2e/monthly-technical-report-parent.spec.ts
```
