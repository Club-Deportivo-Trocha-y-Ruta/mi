# Monthly Technical Report — Coach Runbook

**Audience:** coach and sports club administrator.
**Goal:** by the time **June 2026 closes** you have all the inputs captured during the month and, with just a few clicks, generate the PDF of the Monthly Technical Report (funder-style report), including the qualitative chapter of the high-performance group.

Technical detail in [`design.md`](design.md). Overall vision in [`workflow.md`](workflow.md).

---

## General Idea

The report is assembled with two types of work:

1. **During the month** you capture inputs as they occur (training sessions, photos, attendance, rubrics, round results).
2. **At month close** you configure the project profile once, generate the report, review/edit each block, approve it, and download the PDF.

The AI pre-drafts the narrative with **aggregated** data (never minors' names). You edit and approve it: the final PDF always goes through your review.

---

## Part A — During the Month (June): Capturing Inputs

### A1. Record Each Training Session with Type and Goals

When creating a training session in the form, also fill in:

- **Session type (`session_kind`)**: classify the activity.
  - `entrenamiento` — regular technical/physical training session for the group.
  - `actividad_conjunta` — activity with multiple groups, families, or partners.
  - `salida` — outing or ride outside the venue.
  - `otro` — any other activity relevant to the report.
- **Goals (`objectives`)**: one or two sentences about the session's focus.

> The type feeds the PDF separation: `entrenamiento` sessions go to the high-performance group chapter; `actividad_conjunta` and `salida` go to the joint activities and outings chapter.

### A2. Upload Consented Photos

Upload photos to sessions from the media gallery. Use **only images with informed consent** (Ley 1581/2012). The images feed the "Photo record" of the report, which is restricted distribution.

### A3. Record Attendance and Rubrics

Per session, mark each athlete's attendance and complete the rubric (effort, attitude, technique) and the RPE when applicable. This data:

- Supports the aggregated calculation (attendance percentage, group technical level).
- Feeds, already aggregated and anonymized, the narrative that the AI drafts.

> The AI only sees aggregates and pseudonyms: it never sees real names.

### A4. Ingest Round Results

When the official PDFs for the month's round are published (in June: **CD — Cto. Departamental, 12-jun, Ginebra**), ingest the results using the Copa Valle flow (results module, Phase 1.7 / Competitions module). The competition helper will automatically pick up the **club's podiums** from events whose date falls within the report month.

---

## Part B — At Month Close: Generate and Approve the Report

### B1. Configure the Project Profile (once only)

In **Project data** (`ProjectProfilePage`), fill in once per sports club:

- Project name, executing entity, report responsible person.
- Purpose, general goal, specific goals (list).
- Location and territory description.

This metadata heads **all** reports; no need to repeat it each month. If something changes, edit it and it will be reflected in the next PDF.

### B2. Generate the Period Report

Generate the report for the closed month (the current month and future months are not allowed). Generation:

- Pre-drafts with AI the six narrative blocks (period goal, activity development, results, conclusions, material support, group analysis).
- Automatically picks up the club's podiums for the month (competition block).
- Leaves the report in **`draft`** status.

If a block fails (timeout or privacy rejection), the rest are generated anyway; you can regenerate the failed block individually.

### B3. Review and Edit Each Block

In the report detail view (`ReportDetailPage`, block-by-block editor mode):

- Read the draft of each block and **edit the final text** (`final_text`).
- If a draft does not satisfy you, use **regenerate** for that block: the AI produces a new draft and your previous edit is preserved if you had already changed it.
- Pay special attention to the **High-performance group analysis** block (`analisis_grupo`): this is the qualitative chapter that the director will add to the consolidated report.

> Privacy rule: the AI never writes minors' names. If you need to mention a podium with a name, that already comes from the structured competition block, not from the narrative.

### B4. Approve

When the blocks are ready, **approve** the report (`draft → approved`). Approval is one-way (there is no reversion to draft). While in `draft`, the PDF carries a **DRAFT** banner.

### B5. Download and Distribute the PDF

Download the PDF (technical template). The document includes the institutional cover page, context, territory, high-performance group activities, competition with podiums, joint activities, material support, group analysis, conclusions, and photo record.

The PDF has **restricted distribution** (coach/admin) and carries the Ley 1581/2012 notice: contains minors' data, for exclusive use by the technical team, do not distribute externally. The coach downloads it and distributes it manually (no automatic email sending).

---

## Month-Close Checklist

- [ ] All sessions for the month recorded with `session_kind` and `objectives`.
- [ ] Consented photos uploaded to sessions.
- [ ] Attendance and rubrics complete.
- [ ] Round results for the month ingested.
- [ ] Sports club project profile configured (once only).
- [ ] Month's report generated (`draft` status).
- [ ] Each block reviewed and edited; `analisis_grupo` block refined.
- [ ] Report approved (`approved`).
- [ ] PDF downloaded and distributed via controlled channel.

---

## Notes

- **Population Served** does not appear in the report (omitted by the sports club's decision). The document is limited to the high-performance group, without segmentation by program.
- **Parents** do not see the internal narrative (`narrative_blocks`) or competition results (`competition_results`); their view is a filtered summary.
- Relevant June calendar: **CD — Cto. Departamental, 12-jun, Ginebra** (round A, full taper 7 days).
