# Research — feature 038

## R1. What families actually value in a monthly report

**Decision**: short, mobile-first, one specific highlight, three grounded observations, one action for home, what comes next. Data-dense tables (anthropometry, z-scores, season charts) move to an optional PDF annex.

**Rationale**: youth-sports communication guidance converges on the same shape — plain language, progress over results, "what is improving, what we are watching, how we will help next", a regular cadence and a single channel that works; feedback reports build trust when they tie a short written note to a clear rubric and a concrete next step. The current PDF inverts this: 11 sections, numbers first, generic tips last.

**Alternatives rejected**: keep the technical PDF and only restyle it (does not fix "no value"); drop the PDF entirely (some families print or forward it; multi-child email grouping already works).

Sources: [Playbook — communicating with parents and players](https://blog.callplaybook.com/blog/best-practices-for-communicating-with-parents-and-players-in-youth-sports) · [TeamGenius — feedback reports and trust](https://teamgenius.com/feedback-reports-athlete-parents-trust/) · [Spond — youth sports communication](https://www.spond.com/en-us/news-and-blog/youth-sports-communication-top-strategies-to-help-you-succeed/) · [Vanta — performance reporting for clubs](https://www.vantasports.ai/blog/what-is-performance-reporting).

## R2. "Wrapped"-style recaps: what to borrow, what to refuse

**Decision**: borrow the storytelling mechanics — one idea per screen, personal numbers, a celebratory "summit", a visual metaphor (the route) — and refuse the social-share loop entirely (no share buttons, no public links, no OG images).

**Rationale**: Strava's Year in Sport and Spotify Wrapped work because they turn usage data into a personal story with a clear visual identity; their engagement comes from sharing, which is incompatible with Ley 1581 for minors. The route metaphor keeps the narrative without the virality.

Sources: [TechRadar — Strava Year in Sport](https://www.techradar.com/computing/software/stravas-year-in-sport-is-rolling-out-now-its-like-spotify-wrapped-for-your-activities) · [Trophy — building a wrapped feature](https://trophy.so/blog/how-to-build-wrapped-feature) · [InfoQ — Wrapped 2025 and privacy](https://www.infoq.com/news/2026/04/spotify-wrapped-privacy/).

## R3. Concept: "Bitácora de ruta"

**Decision** (coach, 2026-09-02): the month is a stage of the season route. Waypoints = hitos, effort profile = altimetría, summit = highlight, next segment = what is coming, compass = family corner.

**Rationale**: it is the club's own domain language (trocha, ruta, etapa), it gives every block a place on one visual, it scales from "no race this month" (the summit becomes a training milestone) to a championship month, and it produces a natural season-end artefact later (all stages on one route). Alternatives shown and declined in the interview: player card (radar of attributes risks reading as a rating of the child), club magazine (formal, print-first), vertical "wrapped" stories (poor for print and email).

## R4. Why a single content model

**Decision**: `StageLog` is the only source for web, email and PDF; overrides and hidden blocks are applied server-side; renderers never compute.

**Rationale**: the 003 requirement "PDF, email and preview must share the design" failed in practice because each surface reads `metrics_snapshot` differently (preview cards vs 902-line PDF). One typed model removes the drift, makes the parent allow-list testable, and lets the coach preview be literally the parent component.

## R5. Reusing 037 for families

**Decision**: deterministic filter first (`filter_for_family`), then paraphrase inside the same v2 LLM call. Field-relative reading, coach question, watch signals and data gaps never reach the family surface.

**Rationale**: 037 AC-2.4 forbids naming or ranking other minors; the field reading (percentile, expected vs actual) is coach-only by design (037 out-of-scope note). The headline + one catalog-linked action are the two pieces a parent can act on. Grounding reuses `extract_numeric_tokens` so no new number can appear in the paraphrase.

## R6. Delivery feedback

**Decision**: web read receipt (P2) as the primary signal; Resend webhooks (P3, opt-in via secret) for delivered/bounced, with opened/clicked shown as best-effort.

**Rationale**: a receipt from the authenticated parent view is exact and private. Pixel-based opens are blocked or auto-fired by Apple Mail Privacy Protection and Gmail proxies; bounces, however, are actionable (wrong email). Resend signs webhooks with Svix headers (`svix-id`, `svix-timestamp`, `svix-signature`), which makes verification and idempotency straightforward. Alternative rejected: link-click tracking through a redirect endpoint (adds a public endpoint with tokens tied to a minor's newsletter).

## R7. Rendering the trail on three surfaces

**Decision**: React SVG component (web/coach), Jinja SVG macro with HTML labels (PDF, WeasyPrint), table-based list (email).

**Rationale**: WeasyPrint renders inline SVG but its SVG text handling and font fallback are weaker than HTML; keeping labels in HTML avoids clipped text (024 FR-010 lesson). Most email clients strip or ignore `<svg>`; a `role="presentation"` table with icons as text/emoji is the reliable option and stays under the 100 KB budget.

## R8. Visual tokens

**Decision**: existing tokens + a bounded "bitácora" layer (topographic pattern, dashed teal trail) + one proposed warm earth tone for terrain/summit only, validated by `ux-researcher` before adoption.

**Rationale**: design-system §2 formalises a single accent; the newsletter is the one surface where families, not the coach, are the audience and "llamativo" was an explicit ask. Limiting the exception to two non-status elements keeps status semantics intact (icon + label always).

## R9. Prompt method over prohibitions

**Decision**: v2 prompt = role → numbered method → 8 rules → data → one fictional worked example → JSON schema. One LLM call per newsletter; per-block regeneration reuses the same template with `only_block`.

**Rationale**: identical to the 037 finding (prohibition-only prompts yield boilerplate). The worked example anchors tone and specificity; structured output removes the free-text parsing that lost recommendations in 037 §6.

## Internal evidence used

- Screenshot of `/training/athlete-newsletters/2/6` (2026-09-02).
- `backend/templates/documents/pdf/athlete_monthly_newsletter.html` (902 lines, 11 sections), `templates/email/athlete_monthly_newsletter.html` (327 lines).
- `routers/athlete_monthly_newsletters.py` — all routes coach/admin; `attach_insights` writes `selected_race_insight_ids` with no consumer.
- `use_cases/athlete_monthly_newsletter.py` + `prompts/athlete_monthly_newsletter_v1.j2`.
- `models/athlete_badge.py` badge codes; `components/parents/ParentSidebar.tsx` nav; `routers/parent_athletes.py` `GET /my-athletes`.
- Latest migration `f7a8b9c0d1e3_ai_insights_v3_columns` (037 Wave 1).
