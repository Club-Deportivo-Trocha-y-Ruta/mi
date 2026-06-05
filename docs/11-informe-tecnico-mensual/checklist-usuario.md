# ✅ Manual Testing Checklist — Monthly Technical Report

*(coach's view, as end user)*

This is the guide for testing the module **by hand, from the interface**, without
any technical knowledge (no Docker, no environment variables). For the development
version (stack running, data seeded) see `e2e.md` §3.

## Before You Start

- [ ] Open the app wherever it is published (Render or local) in the browser.
- [ ] Have your **coach account** (local seed: `entrenador@trochyruta.com` / `Coach2026!`).
- [ ] Make sure **a month with already-recorded activity exists**: several training sessions,
      attendance marked, and rubrics. The report summarizes that data; without data, it comes
      out empty. Ideally a month that is already closed.
- [ ] For the competition section: at least **one round from that month** with
      results loaded.

> ⏱ On Render (free plan) the first click after ~15 min of inactivity takes ~50s to
> wake up. This is not an error — just wait.

---

## A. Project Data *(once per sports club)*

- [ ] Side menu → **Monthly reports**.
- [ ] Click on **Project data**.
- [ ] Fill in: project name, executing entity, responsible person, purpose,
      general goal, territory.
- [ ] Add 2-3 **specific goals**; remove one to test.
- [ ] **Save** → confirm success message.
- [ ] Reload the page → data is still there (it really saved).

## B. Generate the Month's Report

- [ ] In **Monthly reports**, click **+ Generate report**.
- [ ] Choose **year and month** of the closed month → confirm.
- [ ] You are taken to the detail view of that month's report.
- [ ] In the list, the report appears with a **Draft** badge.

## C. Review Metrics *(calculated automatically)*

- [ ] Training sessions **executed** and **cancelled** for the month.
- [ ] **Attendance per athlete** (present / late / excused / absent / injured).
- [ ] Rubric averages (effort / attitude / technique).
- [ ] **Technical focus areas** covered.
- [ ] Verify the numbers match what you recorded that month.

## D. Narrative Blocks *(AI + your editing)*

7 blocks appear **in this order**:

1. Period goal
2. Activity development
3. Results obtained
4. Conclusions
5. Material support and outings
6. Group analysis
7. Competition participation

- [ ] On a block, **Generate with AI** → text appears with the notice
      *"AI-generated text — review it before approving."*
- [ ] **Regenerate** the same block → the proposed text changes.
- [ ] **Edit** the text by hand and **Save** → the button changes to *Saved*.
- [ ] Reload → your edit persists.
- [ ] 🔒 Check that the AI text **does not mention minors' names** or individual
      judgments (privacy rule). If a real name appears → report it.

## E. Approve

- [ ] Click **Approve**.
- [ ] The badge changes to **Approved**.
- [ ] The blocks become **disabled**: they can no longer be edited or regenerated.

## F. PDF

- [ ] Click **Download PDF**.
- [ ] The file `informe-tecnico-AÑO-MES.pdf` downloads.
- [ ] Open it and compare with what is on screen: institutional cover page, project
      context/territory, metrics, competition podiums, narrative blocks, photo
      record.
- [ ] Footer with **Ley 1581** notice (restricted distribution).
- [ ] If you downloaded the PDF in **Draft** (before approving): it must carry a
      **DRAFT** watermark.

## G. Training Sessions with Type and Goals *(feeds the report)*

- [ ] Menu → **Training** → create/edit a training session.
- [ ] Verify the **Session type** and **Goals** fields.
- [ ] Save → that data is later reflected in the month's report.

---

## H. 🔒 Privacy — parent/guardian view

*(use a parent account; local seed: `padre@trochayruta.com` / `Parent2026!`)*

- [ ] The parent menu **does NOT** show "Monthly reports".
- [ ] Type the report URL manually in the browser
      (`/training/reports/2026/5`) → you are **redirected to your athletes**
      (`/my-athletes`). The report is internal to the sports club.
- [ ] The parent **does not see** metrics, blocks, Approve, or Download PDF.

---

## I. If Something Fails, Note Down

- [ ] Which screen, which button, what you expected vs. what happened.
- [ ] Screenshot.
- [ ] Approximate time (to cross-reference with logs).
