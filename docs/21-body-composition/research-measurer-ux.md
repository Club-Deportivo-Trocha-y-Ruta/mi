# Skinfold Capture — Measurer UX Research

> **Scope**: UX research for capturing skinfold (body-composition) measurements in the anthropometry module. Audience: coach on a tablet, 1024×768, at the club before training, acting as a non-certified measurer. Coach requirement: *"la medición debe ser ilustrativa para que la persona que tome las mediciones lo tenga muy claro."* No code changed. No implementation decisions are final — recommendations for `engineering-lead` → `react-ui-engineer` / `fastapi-architect`, and open product questions for the coach.
>
> Protocol facts (ISAK-derived) in this document are assumed context handed down for this research pass, not independently re-verified against ISAK source material — confirm with the protocol researcher's parallel output before implementation.

---

## 1. Reusable patterns found in the codebase

**Capture form.** `frontend/src/components/athletes/AnthropometryForm.tsx` is the only existing capture surface: one dense grid (weight, standing height, arm span, sitting height), React Hook Form + an inline Zod schema (not the separate `frontend/src/schemas/anthropometry.schema.ts`, which only mirrors the *read* shape for MSW/tests), a live-computed PHV panel below the form, single `useCreateAnthropometry` mutation. It is mounted inline (not a dialog) on the "Antropometría" tab of `frontend/src/routes/athletes/AthleteDetailPage.tsx:854-889`, toggled by a "+ Nueva medición" button that expands a card and collapses it again on `onSuccess`. No illustrations, no multi-step flow, no draft/autosave — a fast, single-screen path for four numbers a coach already knows how to take.

**Growth-tab vocabulary** (`frontend/src/components/athletes/growth/*`, from feature 040) is the closest thing to a body-metrics design language already in production, and should be reused rather than re-invented:
- `Sparkline.tsx` — pure inline SVG (no chart library), `values: number[]` + `ariaLabel`, last point accented in `--color-primary`. Exact fit for a Σ-skinfolds trend.
- `FamilyBandCards.tsx` — band + neutral narrative + `StatusBadge`, with the clinical term (if any) tucked behind an info tooltip, never a headline. This is the direct precedent for a parent-facing composition card (§8).
- `NextMeasurementCard.tsx` — "Próxima medición: {fecha} · cada {n} días en {etapa}" pattern, reusable verbatim for a skinfold recheck cadence if one is defined (§10 Q3).
- `PercentileInterpretationBlock.tsx` — band/narrative up front, a "Detalles técnicos" `aria-expanded` toggle reveals Z/percentile. Precedent for hiding %BF/technical numbers behind a click.
- `GrowthAlerts.tsx` shows the house style for alert copy: warning tone is always framed as actionable, never alarming.

**Shared primitives**: `components/shared/StatusBadge.tsx` (4-tone, icon+label, color never alone — Constitution III), `StatCard.tsx`, `Stepper.tsx` (contract: `specs/028-frontend-design-foundation/contracts/shared-components.md`), `EmptyState.tsx`/`ErrorState.tsx`.

**Multi-step guided capture** already exists and is battle-tested: `frontend/src/components/training/session-wizard/SessionWizard.tsx` + `StepGeneral/StepAthletes/StepRouteNotes/StepReview.tsx`. It gives, ready to reuse: the shared `Stepper`, per-step Zod validation via `trigger(fields, { shouldFocus: true })`, a jump-to-error `SessionErrorSummary.tsx` + `ERROR_TARGET_ID` map, and — most relevant here — a documented step-heading focus-management contract (`stepHeadingRef` + `tabIndex={-1}` + `useEffect` on step change, `SessionWizard.tsx:213-217`) so a screen-reader user isn't lost between steps.

**Autosave/draft**: `frontend/src/hooks/useFormDraft.ts` is a generic, already-shipped answer to "a half-finished measurement must not be lost" — localStorage, keyed `tyr:session-draft:v1:{userId}:{target}`, 800 ms debounce, try/catch-safe for quota/private-mode, with a restore/discard banner already implemented in `SessionWizard.tsx:507-531` ("Tienes un borrador sin guardar… Restaurar / Descartar"). Directly reusable with a different `target`.

**Printable field guide**: `frontend/src/components/intervals/InstructivoDownloadButton.tsx` (brand selector + download button + blob download, disabled-state copy, error copy) paired with `backend/templates/documents/pdf/session_instructivo.html` (Jinja → WeasyPrint, extends `documents/pdf/base/layout.html`, an amber callout box style for a must-not-miss step) is the exact precedent for §6.

**Illustration production — the one directly on-point precedent**: `specs/019-gymkhana-circuit-diagrams/` (Draft status, not yet built) already solved "how do we draw instructional diagrams in this stack" for the coach's technique library, superseding feature 018's ASCII `<pre>` (`docs/15-tecnica-gymkana-modulo/design.md` §"Illustrative circuit layout decision"). Its decision record (`specs/019-gymkhana-circuit-diagrams/research.md` R1/R3, `spec.md` "Chosen-Library Decision Record") is directly transferable:
- **One schema, two renderers** — a plain, library-agnostic JSON schema (`GymkhanaLayout`, Zod client-side / Pydantic server-side) drives both a hand-authored inline-SVG React component and a server-side Jinja inline-SVG partial (sibling to the already-shipped `backend/templates/documents/pdf/charts/*.svg.jinja` — I inspected `percentile_curves.svg.jinja`: `role="img"` + `aria-label`, `viewBox`, `preserveAspectRatio="xMidYMid meet"`, real `<text>` labels, zero external fetches).
- **No canvas/raster, no new client dependency** — rejected for exactly the reasons that would apply here too (print-friendliness, crispness on tablet pinch-zoom in sunlight, a11y tree).
- Element kinds are distinguished by shape/pattern + label, **never color alone**.

**What's missing.** A repo-wide grep for "pliegue"/"skinfold" returns nothing in `frontend/` or `backend/` — this is greenfield; `docs/21-body-composition/` was an empty directory before this file. No anatomical/landmark illustration exists anywhere in the product. `docs/05-design-system/design.md` §7 lists "no illustrations, abstract graphics, or decorative elements" as a Cal.com-inherited Don't — but the gymkhana precedent already establishes the operating distinction this proposal leans on: *functional, instructional* diagrams are an accepted exception to that rule (same logic as the "no gratuitous animation" non-negotiable — imagery must serve teaching, not decoration). There is also no existing "offline, will save when reconnected" UI component — `ConnectionStatusBadge.tsx` is Strava-connection-specific, not a generic offline-capture affordance (§5). And no per-field *soft* plausible-range warning exists yet; today's Zod schema only has hard min/max (e.g. weight 20–150 kg).

---

## 2. Capture flow proposal

**Where skinfolds live.** Recommend: **same `AnthropometricRecord`, same `evaluation_date`**, but body composition is an **optional, explicitly separate step appended after the existing fast save** — not a field added to the current dense grid, and not a fully separate top-level entity.

Rationale:
- Weight/height/PHV is a ~30-second task the coach already knows; skinfolds are a ~5–8 minute, error-prone, multi-site skill task for a *non-certified* measurer — exactly the coach's stated problem. Forcing every quick weight check through skinfold UI would slow down the common case.
- A fully separate flow/entity (disconnected from the anthropometry record) risks the same "two sources of truth for one measurement date" problem already flagged and fixed elsewhere in this module (`docs/18-growth-module-redesign/proposal.md` G-01/G-02: CDC-vs-WHO, oldest-vs-latest record bugs) — body-fat estimates need the same-date weight to compute FFM, so the two must stay attached to one record.
- Precedent for "attach a follow-on action to an already-saved record" already exists: `AnthropometryHistory.tsx`'s per-record AI explanation dialog (`HistoryRowWarningMarker`, `useMeasurementExplanationCached(athleteId, recordId, …)`) hangs off a specific `record_id` after the fact.

Concretely: after `AnthropometryForm`'s existing save succeeds, offer two exits instead of one: **"Guardar y terminar"** (today's behavior, unchanged) and **"Guardar y agregar pliegues"**, which opens the step-per-site wizard against the just-created `record.id` (a new sub-resource/PATCH, backend team's call — out of scope here).

**Step-per-site vs. one dense form**: recommend **step-per-site**, reusing the `SessionWizard`/`Stepper` pattern. A dense multi-column grid cannot legibly carry, per site, an illustration + two short instruction lines + a two-reading input + live diff feedback without either shrinking touch targets below the 48×48 px floor (`.specify/memory/constitution.md:117`) or overwhelming a sunlit tablet screen. One site at a time also matches the physical reality of the task — the measurer is already moving between body regions and rotating through sites rather than typing rapid-fire into a grid. The real cost (more taps) is mitigated by: draft/autosave (§5) against interruption, and a "Tabla" power-user shortcut in the Review step for a coach who has done this many times, mirroring `GrowthCurveSection`'s chart/table toggle.

Default step count stays small: **3 mandatory sites** (triceps, subscapular, medial calf) + a "+ Agregar sitio opcional" affordance for supraspinale/front thigh/iliac crest/biceps/abdominal, so the guided flow doesn't balloon to 8 steps by default.

```
┌─────────────────────────────────────────────────────────────────────┐
│ ● Precheq.  ● Tríceps  ○ Subescap.  ○ Pantorr.  ○ Revisar   Paso 2/5 │
├─────────────────────────────────────────────────────────────────────┤
│  Pliegue tricipital                                  [ Omitir sitio ]│
│                                                                       │
│   ┌────────────────────┐   Dónde:                                   │
│   │                     │   Cara posterior del brazo derecho, punto  │
│   │   [ilustración:     │   medio entre el hombro y el codo.         │
│   │    brazo derecho,   │                                            │
│   │    marca del punto  │   Cómo:                                   │
│   │    medio, pinza en  │   Pliegue vertical. Pellizca 1 cm arriba   │
│   │    posición]        │   de la marca. Lee la pinza a los 2 seg.   │
│   └────────────────────┘                                             │
│                                                                       │
│   Lectura 1 (mm)          Lectura 2 (mm)                             │
│   ┌──────────────┐        ┌──────────────┐    Diferencia: 0.5 mm ✓  │
│   │     8.5      │        │     9.0      │    (dentro del rango)     │
│   └──────────────┘        └──────────────┘                           │
│   Mediana provisional: 8.75 mm                                       │
│                                                                       │
│  [ ← Atrás ]                                    [ Siguiente sitio → ]│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Per-site illustration spec

Each illustration must show, unambiguously: **body region** (generic limb/torso silhouette only, cropped to the relevant area — never a full recognizable figure), the **landmark** (a marked point/line with its own short label, e.g. "punto medio acromion–olécranon"), the **fold orientation** (vertical or oblique dashed guideline), the **caliper position** (jaws shown ~1 cm from the marked line, in the pinch position, per the domain brief), and the **side** — always right, made explicit with a small "D" (derecha) tag or by only ever drawing the right limb engaged, since measuring the wrong side is a plausible novice error the diagram should pre-empt.

**Production approach — recommend hand-authored inline SVG, mirroring the gymkhana decision record (§1), not a licensed illustration set.** Concretely:
- One `<SkinfoldSiteDiagram kind="triceps" | "subscapular" | "medial_calf" | …>` React component per the codebase's existing SVG-illustration idiom, sharing a common base limb/torso silhouette so the ~8 site variants differ only in landmark + caliper marker (authoring cost stays low).
- A sibling server-side Jinja inline-SVG partial (next to `backend/templates/documents/pdf/charts/*.svg.jinja`) renders the *same* per-site landmark-coordinate data for the printable guide (§6) — one schema, two renderers, exactly as `GymkhanaLayout` does for circuits. No new client dependency either way.
- **Rejected**: stylized flat-illustration libraries (unDraw-style) — wrong register, no landmark/caliper convention, reads as decorative in a screen that must teach a precise technique. **Rejected**: tracing ISAK/kinanthropometry course diagrams — those are copyrighted training materials; use the ISAK *descriptions* (already summarized in the domain brief) as the drawing spec, not the source images, which sidesteps licensing risk entirely. Public-domain anatomical line-art (Wikimedia Commons/Openclipart CC0 base silhouettes) could seed the base body shape, but landmark/caliper marking still has to be hand-added regardless of source, so hand-authoring from the ISAK description is the lower-total-effort path, not just the safer one.

**Sizing / theming**: `viewBox`-based, no fixed pixel width, comfortable default around 280×280 logical units on the step card, stroke ≥2 px so it survives direct sunlight (thin hairlines wash out). Coach surfaces support a dark theme (`docs/05-design-system/design.md` §"Dark Theme Tokens"); illustration strokes/fills must reference theme tokens, not literal black/white, so the diagram stays legible in both. The parent portal is forced light-only, so no dark variant is needed for any family-facing copy of these illustrations (and per §8, none is recommended anyway).

**Alt text**: every diagram ships `role="img"` + `<title>`/`<desc>` **and** a written plain-language alternative, reusing the `layout_alt` precedent from feature 018/019 — e.g. for triceps: *"Pliegue tricipital: parte de atrás del brazo derecho, a la mitad entre el hombro y el codo. Se pellizca en vertical un centímetro arriba de la marca; la pinza se coloca sobre la marca."* Landmark and caliper are never color-only — always shape + label, so the diagram survives grayscale printing (§6) and color-blind viewing.

**Animation/GIF: recommend against a baked GIF.** Reasons: it would be the first motion-bearing, body-adjacent image in a product whose non-negotiables explicitly require every motion to "serve orientation or feedback" and respect `prefers-reduced-motion` — a looping pinch animation is defensible content (the 1 cm/2-second timing is genuinely hard to convey statically) but not defensible as a raster GIF, which is off the SVG-only precedent, heavier, and not vector-crisp on zoom. If the timing genuinely needs motion, prefer a short (~2 s), non-autoplaying, **opt-in** "Ver animación" toggle built as an SVG/CSS keyframe loop (freezes to the static frame under `prefers-reduced-motion`) — low-to-medium extra effort per site, worth doing only if usability testing (§ deliverable format this role normally produces) shows measurers mistime the pinch-to-read window from stills alone. Default should ship static-only first.

---

## 4. Inline protocol guidance

**Pre-check screen** (step 1, before any site): a plain checklist the measurer visually confirms — "¿Hace más de 2 horas que no entrena?", "Piel seca, sin loción ni protector solar", "El deportista está de pie, relajado" — framed as a checklist, not a blocking gate (these are data-quality conditions, not safety ones). One item is different in kind and **should gate "Siguiente"**: confirming a second adult is present. That is a child-safeguarding control, not a UX nicety, so it is called out explicitly as an open decision in §10 (Q1) rather than assumed. A same-sex-measurer-preferred line is advisory copy only — recommend *not* adding a "quién mide" field to enforce it (§9, data minimization). Comfort/consent is a single reassuring line plus the standing reminder that any site can be skipped; this screen does not own consent infrastructure, it only has to respect it in the moment.

**Per-site micro-instructions**, capped at two short lines each under "Dónde" / "Cómo" labels (see the §2 wireframe) — anything longer than that goes into the printable guide (§6), not the step card, so it survives a glance-read in sunlight.

**Two-reading input with live feedback**: as soon as both readings are filled, compute and show the difference inline. Within tolerance → a quiet green confirmation and the live median/mean. Outside tolerance → a **non-blocking amber** message ("Diferencia mayor a lo esperado — toma una tercera lectura") that reveals a third input; median of three computes live once entered. This must render as `warning`, never `danger` — going over tolerance is a normal, expected protocol branch, not a mistake, matching this codebase's own status-token rule (warning = recoverable/actionable, never destructive). Recommend externalizing this as a small, independently unit-testable helper (e.g. `computeSkinfoldReading(readings: number[]): { median: number; needsThirdReading: boolean }`) rather than inline component logic, mirroring how `lib/growth/lms.ts`/`lib/growth/bands.ts` already keep calculation out of components in this codebase. The exact tolerance rule from the domain brief ("> 5%, or > 1 mm on small folds") reads as *effective tolerance = the greater of 5% of the mean or 1 mm* — flagging this interpretation explicitly rather than asserting it, since it should be pinned down with concrete fixtures by whoever owns the protocol.

**Per-site "omitir"**: a full-weight, equally visible secondary action in the step header (see wireframe), not a small text link — this codebase's own audit history shows secondary actions are the ones that repeatedly ship under the 48 px floor, so flagging it here up front. No forced reason field on skip: asking "why did you decline" pressures the athlete to justify not being touched, which cuts against opt-out-first. Skipped sites appear as "Omitido" (neutral tone, never red/error) in the Review step and downstream results.

**End-of-flow summary**: a Review step (mirroring `StepReview.tsx`'s role) — a compact site → mm (median) → omitted table, the running Σ, and the existing "Guardar medición" action.

---

## 5. Input ergonomics

- **Numeric keypad**: same idiom `AnthropometryForm.tsx` already uses (`inputMode="decimal"`), `step="0.5"` to cover both 0.5 mm and 1 mm caliper resolutions from one control.
- **Touch targets**: both reading inputs and every step control (Siguiente/Atrás/Omitir) must clear the 48×48 px constitution floor — explicitly including the reading inputs and "Omitir", which are exactly the kind of "looks secondary" controls that have shipped undersized before in this codebase's AI-card components.
- **Typo prevention**: extend today's hard min/max convention with a **soft**, non-blocking, per-site plausible-range check (domain brief: 3–40 mm typical for this age group, narrower per site) — an inline amber "¿Seguro? Ese valor es alto/bajo para este pliegue" that never blocks submission, same tone as the two-reading diff warning. Exact per-site bands are a sports-science-advisor call (§10 Q4 overlaps here).
- **Autosave/draft**: reuse `useFormDraft` as-is (it is already generic over `<T>`), keyed by athlete + evaluation date instead of session id. The existing restore/discard banner UX transfers directly. Per-site mm readings carry no name/DOB, so this draft is lower-privacy-risk than the session wizard's athlete-id-bearing draft already shipped.
- **Offline tolerance**: a genuine gap, not a reuse — no "offline, will save when reconnected" component exists anywhere yet (`ConnectionStatusBadge.tsx` is Strava-connection-specific). Recommend a small new hook pairing the standard TanStack Query retry behavior with a passive `StatusBadge`-styled line ("Sin conexión — se guardará cuando vuelvas a tener señal") driven off `navigator.onLine`/mutation network errors. Flag to `engineering-lead` as new work, not a drop-in.

---

## 6. Printable field guide

Recommend yes — a laminated wall sheet at the measurement station, reusing the `InstructivoDownloadButton.tsx` + `session_instructivo.html` pattern verbatim (same download-button shape, same `documents/pdf/base/layout.html`, same amber callout box style already used for the auto-lap warning). Unlike the intervals instructivo, this one should be **club-wide and generic — no per-athlete data at all** — so it is generated once, printed once, and reused, not regenerated per session.

Content outline: (1) header — club name, "Instructivo de toma de pliegues cutáneos"; (2) the same pre-check checklist as §4, printed as a literal checklist; (3) one section per site — the server-rendered version of the §3 illustration plus the "Dónde"/"Cómo" copy plus the right-side reminder; (4) a shared reading-protocol callout box (two readings → tolerance check → median; third reading if needed; rotate sites, never repeat one twice in a row); (5) a footer privacy line matching the existing instructivo convention, plus an explicit note that the sheet itself is generic and carries no athlete data. Coach/admin-only, same RBAC posture as the intervals instructivo — no parent-facing version needed.

---

## 7. Results presentation for the coach

Extend the existing growth-tab vocabulary rather than inventing a new one — a `BodyCompositionCard` (name indicative) living alongside `MorphologyCard`/`GrowthStatusRow` in `GrowthTab.tsx`'s coach composition, built from the same `StatCard` + `Sparkline` + `StatusBadge` primitives already proven there.

```
┌──────────────────────────────────────────────────────────────────┐
│ Composición corporal                        [Ver detalle por sitio]│
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────────────────┐ │
│ │ Σ pliegues     │ │ Masa libre de │ │ Cambio desde la última     │ │
│ │ 42.5 mm ▂▃▄▅   │ │ grasa (est.)  │ │ medición                   │ │
│ │ 6 sitios       │ │ 34.8 kg       │ │ ● Dentro del margen de     │ │
│ │                │ │               │ │   medición (−1.1 mm)       │ │
│ └───────────────┘ └───────────────┘ └───────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

- **Σ skinfolds** as a `StatCard` with an inline `Sparkline` (`Sparkline.tsx` already takes `values: number[]` + `ariaLabel` — no changes needed) trending across records.
- **Per-site sparklines**: defer to a detail view (reuse `AnthropometryHistory`'s per-record dialog pattern) rather than crowding 6–8 sparklines onto the main tab — keeps the "decision first, evidence second" principle from `docs/18-growth-module-redesign/proposal.md` §4.
- **Delta framing — "dentro del ruido / cambio real"**: render through `StatusBadge`'s existing tones, neutral/gray for "within the measurement margin" vs. a colored, worded change for a real one — needs a measurement-error-aware threshold (likely related to the same tolerance used for the two-reading check, scaled for between-session comparison), which is a sports-science-advisor decision, not a UI one.
- **Fat-free-mass estimate**: a `StatCard` at the same visual tier as Σ skinfolds, but recommend computing it **server-side at save time** (persisted, like the existing PHV/percentile pipeline) rather than recomputed live client-side like the current PHV panel — the youth %BF/FFM equation choice (e.g. Slaughter et al.) is a clinical decision that shouldn't live hardcoded in a component.
- **Traffic-light band**: extend `lib/growth/bands.ts`'s `getBandVocabulary`/`getBandSpec` pattern with a sibling function rather than a new one-off color map — this codebase has already had to consolidate three redundant PHV color maps into one; don't recreate that problem here.

---

## 8. Family view

**Recommend: band + narrative only — no %BF numeral, and no Σ mm numeral either.** Mirror `FamilyBandCards.tsx` exactly: a single "Composición corporal" card with a `StatusBadge` band label and a narrative sentence, nothing numeric. Rationale: body-fat percentage in a 9–15-year-old context is precisely the kind of number that invites unsupervised comparison or anxiety — a bigger dignity risk than the height/BMI numerals `docs/18-growth-module-redesign/proposal.md` (decision D3) already chose to soften for families ("never *obesidad* as a headline"). A raw Σ mm figure is still a comparable, gameable number even without a %BF conversion, so hiding %BF alone isn't sufficient. This is a recommendation to confirm with the coach, not a settled decision — some clubs do expect to share a concrete trend number with families, and removing one changes what parents currently might expect to see (§10 Q5).

---

## 9. Accessibility and dignity checklist

- WCAG AA contrast on every illustration stroke/label (aim AAA per the club's sunlight heuristic); landmark/caliper marking is always shape + label, never color alone.
- Every diagram: `role="img"` + `<title>`/`<desc>` + a written plain-language alt (§3).
- Step-heading focus management on every transition, reusing `SessionWizard.tsx`'s exact contract (`stepHeadingRef` + `tabIndex={-1}` + `useEffect`) so a screen-reader user is never lost between sites.
- 48×48 px floor on **every** control, explicitly including "Omitir sitio" and the two reading inputs.
- `prefers-reduced-motion` respected on any optional animated illustration (§3), frozen to the static frame by default; none of this is required to understand the technique.
- No athlete photo, ever — generic, non-data-linked line-art only; the illustration must never appear "personalized" to the specific athlete being measured.
- Declining a site must look exactly as complete/successful as finishing it — neutral "Omitido," never red/error styling, no forced justification text.
- Private space + chaperone + per-site opt-out are first-class flow steps, not settings buried in a menu.
- Language throughout stays clinical-but-warm and body-neutral; route final wording through `parent-communicator`/`nutrition-advisor` before ship, same as the BMI-wording review already done for the growth tab.
- Data minimization: do not add a "quién midió" / measurer-sex field just to enforce the same-sex-measurer preference — that is a staffing/process control, not something the app needs to store, and every field must carry its own justification per the club's non-negotiables.

---

## 10. Open questions for the coach

1. **Chaperone confirmation** — hard-block "Siguiente" on the pre-check step (safeguarding gate), or a soft reminder like the other pre-check items?
2. **Default vs. optional sites** — confirm triceps/subscapular/medial calf as the only mandatory-by-default steps, with the rest behind "+ Agregar sitio opcional."
3. **Capture cadence** — does body composition get measured every time weight/height is (same record, always offered), or on its own slower cadence (e.g. tied to the existing Pre/Circa/Post-PHV measurement-interval logic)?
4. **%BF/FFM equation** — which youth equation (e.g. Slaughter et al.) should the estimate use? Determines what the "Masa libre de grasa (est.)" stat can claim.
5. **Family view numerals** — confirm band+narrative-only with zero numerals (§8), or does the club want families to see the Σ mm trend specifically?
6. **Printable guide scope** — club-wide generic wall poster only (as recommended in §6), or is a per-athlete take-home version also wanted?

---

**Summary of recommendation**: attach skinfolds as an optional post-save step on the existing `AnthropometricRecord` (not a new dense field set, not a separate entity); build it as a step-per-site guided wizard reusing `SessionWizard`/`Stepper`/`useFormDraft`; produce illustrations as hand-authored inline SVG sharing one schema between the in-app component and a server-side Jinja partial for print, following the gymkhana circuit-diagram precedent exactly; keep every warning non-blocking and every skip dignified; keep the family view numeral-free.
