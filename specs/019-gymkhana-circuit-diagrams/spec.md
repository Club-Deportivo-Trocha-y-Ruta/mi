# Feature Specification: Gymkhana Circuit Diagrams & Joint Session Authoring

**Feature Branch**: `claude/spec-kit-agent-setup-poepvz` (developed on the designated session branch; spec directory `019-gymkhana-circuit-diagrams`)

**Created**: 2026-06-30

**Status**: Draft

**Input**: Coach request: "Upgrade the Technique & Gymkhana Library (feature 018) so the illustrative circuit layouts are proper 2D graphical diagrams — cones, lines/paths, gates, obstacles ('minas'), balance beams ('equilibrio'), the 'círculo de la muerte' ring, and bike movement-direction arrows — instead of ASCII; and let me compose several individual exercises into a single combined gymkhana session ('crear sesiones de trabajo de gymkanas en conjunto'), ideally by dragging circuit elements onto a canvas, reusing the existing Training Sessions session-assembly flow rather than duplicating it."

## Overview

Feature 018 (Technique & Gymkhana Library) shipped a searchable catalog of ~24 drills/gymkhana exercises with an **illustrative ASCII circuit layout** (`layout_ascii` + `layout_alt`) rendered in a monospace `<pre>` and seeded from `docs/14-tecnica-gymkana-7-15/research.md`. The coach has asked to raise that fidelity along two axes:

1. **Graphical circuit diagrams** — replace the monospace ASCII croquis with proper **2D graphical diagrams** that draw the club's real circuit vocabulary: cones (*conos*), free/technical paths (*trayectos*), gates (*puertas*), obstacles / "minas", balance beams (*equilibrio*), the "círculo de la muerte" ring, and bike movement-direction arrows.
2. **Joint / group gymkhana session authoring** — let the coach **compose multiple individual exercises into one combined gymkhana session** ("sesiones de gymkanas en conjunto"), with **drag-and-drop placement** of circuit elements onto a canvas, feeding the result into the **existing Training Sessions module** session-assembly flow already built in feature 018 (no parallel session store).

The keystone is a single, library-agnostic **`GymkhanaLayout` JSON schema** that decouples the persisted diagram format from any rendering library. The same `GymkhanaLayout` drives (a) a presentational inline-SVG renderer used in-app **and** in the existing PDF/email document pipeline, and (b) — later — a drag-and-drop editor. The diagram representation is the *only* substantive change to the data model; everything else reuses feature 018.

This feature directly advances the club's first non-negotiable, **skills before fitness**: a clearer, more legible circuit makes age-appropriate technical work faster to set up in the field. It also serves **fun first** — gymkhanas are the play-based heart of the 7–12 methodology, and a readable combined circuit lets the coach run a single engaging station-rotation rather than disconnected drills.

> **Language note**: This spec is a development artifact written in English per the project working-language policy (Constitution Principle III / `CLAUDE.md` "Language"). All coach- and admin-facing product copy in the running product — UI strings, element labels, diagram legends, the editor palette, PDF/email captions — MUST be in **español neutro (Colombia)**. Example legend strings appear in Spanish throughout this spec.

> **Scope note (relationship to feature 018)**: This feature **extends** feature 018; it does not re-specify the catalog, filtering, exercise detail content, session-reuse mechanics, per-athlete progress, curation, RBAC, or privacy posture. Those remain as specified in `specs/018-technique-gymkhana-library/spec.md` and are referenced here only where the diagram/composer touches them.

## Phasing summary *(read first)*

This feature is deliberately split into two independently shippable phases. The functional requirements below are tagged **[Phase A]** or **[Phase B]**.

- **Phase A — Graphical diagrams (priority / MVP)**: the `GymkhanaLayout` Zod/Pydantic schema; a presentational `<CircuitDiagram>` inline-SVG component (palette: cone, line/path, gate, mine, beam, ring, direction arrow); a server-side Jinja inline-SVG partial that renders the **same** layout in the existing PDF/email pipeline; backfill of the ~24 seeded drills' ASCII layouts into `GymkhanaLayout` JSON; and a new `layout_json` column persisted on the exercise record (Alembic migration required). ASCII remains as a fallback during transition.
- **Phase B — Joint session authoring (later)**: a `react-konva` drag-and-drop `/technique/composer` editor that reads/writes the **same** `GymkhanaLayout` JSON, lets the coach lay out a combined gymkhana circuit, and binds the composed exercises into a single combined gymkhana session through the existing Training Sessions session-assembly flow (feature 018 `TechniqueSessionExercise` link, `SessionAssembler`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a graphical circuit diagram for a gymkhana exercise (Priority: P1) — Phase A

The coach, on a tablet in the field, opens a gymkhana exercise and sees a clean **2D graphical diagram** of the circuit instead of an ASCII croquis: cones, the free and technical path segments, gates, "minas", a balance beam, the "círculo de la muerte" ring, and arrows showing which way the rider moves — each with a readable legend in Spanish. The diagram is crisp when zoomed and legible in sunlight.

**Why this priority**: This is the concrete upgrade the coach asked for and the minimum standalone value. Every seeded gymkhana already references a circuit; rendering it graphically makes the existing library materially more usable in the field without any new authoring capability.

**Independent Test**: Sign in as a coach, open any seeded gymkhana exercise, and confirm a 2D graphical diagram renders (not a `<pre>` ASCII block) with the club's element vocabulary and a Spanish legend; pinch-zoom/scale and confirm it stays crisp; confirm a non-gymkhana exercise shows no diagram.

**Acceptance Scenarios**:

1. **Given** a seeded gymkhana exercise with a backfilled `GymkhanaLayout`, **When** the coach opens its detail, **Then** a 2D graphical circuit diagram is rendered from `layout_json` (not the ASCII `<pre>`).
2. **Given** the diagram, **When** the coach inspects it, **Then** cones, path segments (free vs. technical), gates, minas, beams, the ring, and direction arrows are visually distinguishable and labeled via a Spanish legend.
3. **Given** the diagram on a narrow tablet screen, **When** the coach zooms in, **Then** the diagram remains crisp (vector, not raster) and does not overflow or break the page layout.
4. **Given** a non-gymkhana exercise (no layout), **When** the coach opens it, **Then** no diagram is shown (parity with feature 018 behavior).
5. **Given** an exercise whose `layout_json` is absent but whose legacy `layout_ascii` exists, **When** the coach opens it during the transition window, **Then** the legacy ASCII croquis is shown as a graceful fallback (no blank space, no error).

---

### User Story 2 - Circuit diagrams appear in the PDF/email document pipeline (Priority: P1) — Phase A

When a gymkhana exercise (or a technique session that contains gymkhanas) is rendered into one of the club's documents — the printable session sheet or any report/newsletter that embeds circuit content — the **same** graphical diagram appears, print-clean and accessible, produced from the identical `GymkhanaLayout` by a server-side renderer.

**Why this priority**: The club's documents are produced server-side as PDF/HTML email via Jinja inline-SVG partials (e.g. `templates/documents/pdf/charts/*.svg.jinja`). The diagram is only as valuable as the surfaces it reaches; a diagram that renders in-app but not in print would force the coach back to ASCII for field printouts. Rendering from one schema on both the client and the server is the architectural payoff.

**Independent Test**: Render a document that embeds a gymkhana circuit (printable session sheet) and confirm the circuit appears as a vector diagram in the PDF/email output, visually equivalent to the in-app diagram, with a text alternative present in the markup.

**Acceptance Scenarios**:

1. **Given** a gymkhana with a `GymkhanaLayout`, **When** a document embedding its circuit is rendered server-side, **Then** the circuit appears as an inline-SVG vector diagram produced from the same `layout_json`.
2. **Given** the server-rendered diagram, **When** the document is opened, **Then** the diagram is print-clean (no clipping, no external image fetch, no canvas/raster) and carries a text alternative for accessibility.
3. **Given** an exercise without a `GymkhanaLayout`, **When** a document is rendered, **Then** the circuit section is omitted gracefully (no broken image, no empty box).

---

### User Story 3 - Compose multiple exercises into one combined gymkhana session by dragging elements onto a canvas (Priority: P2) — Phase B

The coach opens a composer, drags circuit elements (cones, paths, gates, minas, beams, the ring, arrows) onto a canvas to lay out a **combined** gymkhana circuit assembled from several individual exercises, and saves it. On save, the result is a **normal club training session** created through the existing Training Sessions module — appearing in the calendar/session list and supporting attendance and rubric — that references the composed exercises (feature 018 `TechniqueSessionExercise`), with the combined `GymkhanaLayout` attached.

**Why this priority**: This is the "gymkanas en conjunto" authoring the coach wants, but the library is already materially improved by Phase A alone. The editor is heavier (new rendering library, drag-and-drop UX) and depends on the Phase A schema, so it is a deliberate later slice.

**Independent Test**: Open the composer, drag at least three element kinds onto the canvas, add two or more catalog exercises to the combined session, save, and confirm a single training session is created in the existing module (visible in calendar/session list), references the chosen exercises, supports attendance/rubric, and persists the combined `GymkhanaLayout` round-trippable back into the editor.

**Acceptance Scenarios**:

1. **Given** the composer canvas, **When** the coach drags cone/path/gate/mina/beam/ring/arrow elements onto it and positions/rotates them, **Then** the canvas state is captured as a `GymkhanaLayout` (the same schema the static renderer consumes).
2. **Given** a composed layout plus a selection of catalog exercises arranged into warm-up / main set / cool-down, **When** the coach saves, **Then** a single club training session is created **through the existing Training Sessions module** (no parallel session store) and references those exercises.
3. **Given** a saved combined session, **When** the coach reopens it, **Then** the combined `GymkhanaLayout` re-loads into the editor (round-trip) and renders identically in the static `<CircuitDiagram>`.
4. **Given** a saved combined session, **When** it is opened from the calendar/session list, **Then** it supports the existing attendance and rubric flows unchanged.
5. **Given** a combined session that mixes age bands, **When** the coach saves it, **Then** the system allows it but surfaces the existing feature-018 mixed-age-band notice.
6. **Given** the coach edits the layout after first save, **When** they save again, **Then** the updated `GymkhanaLayout` replaces the prior one on the same session without creating a duplicate session.

---

### Edge Cases

- **Legacy ASCII, no JSON**: any gymkhana not yet backfilled must fall back to its `layout_ascii`/`layout_alt` (US1 #5); no blank diagram, no error.
- **Malformed / out-of-bounds layout**: a `GymkhanaLayout` with elements outside `width`/`height`, an unknown `kind`, or a non-finite coordinate must be rejected by schema validation (client and server) and never half-render.
- **Empty layout**: a `GymkhanaLayout` with zero elements is valid (e.g. a placeholder) and renders an empty bounded canvas with the legend suppressed.
- **Very dense circuit**: a layout with many elements must remain legible (zoom/scroll) in-app and must not clip in the PDF page box.
- **Cold start / intermittent 3G**: opening a diagram or the composer against a cold Render backend must present the shared "server starting" / loading state (feature 012), never a spinner-forever or raw error.
- **Composer on a small tablet**: the drag-and-drop canvas must be usable at tablet width; if pointer-drag is impractical, an accessible non-drag fallback (add element + nudge controls) MUST exist (see Accessibility).
- **Element label is free text**: any per-element `label` is coach-authored and MUST be treated as non-PII content; the system MUST NOT require or suggest entering a minor's name onto a diagram.
- **Referenced exercise hidden/edited later**: per feature 018 FR-020, hiding or editing a composed exercise MUST NOT corrupt the previously saved combined session or its stored layout.

## Requirements *(mandatory)*

### Functional Requirements

Each requirement is tagged **[Phase A]** (MVP) or **[Phase B]** (later). Phase B requirements depend on the Phase A schema and renderer.

**Graphical diagram schema & rendering**
- **FR-001 [Phase A]**: The system MUST define a single, library-agnostic **`GymkhanaLayout`** data structure (see *Data Model*) that fully describes a 2D circuit: a bounded canvas plus a list of placed elements, each with a kind, position, optional rotation, and optional label. This structure is the persisted source of truth and is independent of any rendering library.
- **FR-002 [Phase A]**: The element vocabulary MUST cover at least: **cone** (`cono`), **line/path** (`trayecto`, distinguishing free vs. technical/precision), **gate** (`puerta`), **mine/obstacle** (`mina`), **balance beam** (`equilibrio`/`viga`), **ring** ("círculo de la muerte"), and **direction arrow** (`flecha` — bike movement direction).
- **FR-003 [Phase A]**: The system MUST provide a presentational **`<CircuitDiagram>`** component that renders a `GymkhanaLayout` as **inline SVG** (vector), with no canvas/raster dependency and no heavy new client library, used in the exercise detail and anywhere the in-app circuit is shown.
- **FR-004 [Phase A]**: The diagram MUST include a Spanish legend mapping each rendered element kind to its meaning (e.g. "Cono", "Trayecto libre", "Trayecto técnico", "Puerta", "Mina", "Equilibrio", "Círculo de la muerte", "Dirección de recorrido").
- **FR-005 [Phase A]**: The system MUST render the **same** `GymkhanaLayout` server-side as inline SVG within **the printable session sheet only** (the one document target for Phase A), consistent with `templates/documents/pdf/charts/*.svg.jinja`, with no external image fetch and print-clean output. *(Per O-1: the monthly technical report and the newsletter are explicitly out of scope for embedded circuit diagrams in this feature; a later spec may extend them.)*
- **FR-006 [Phase A]**: Both client and server renderers MUST be driven by the identical `GymkhanaLayout`; there MUST NOT be a divergent second diagram format. The renderers MUST be visually equivalent for the same input.
- **FR-007 [Phase A]**: The system MUST validate `GymkhanaLayout` on both client (Zod) and server (Pydantic): reject unknown `kind`, non-finite or out-of-bounds coordinates, and malformed structure; a valid empty layout (zero elements) MUST be accepted.

**Persistence & seed backfill**
- **FR-008 [Phase A]**: The exercise record MUST persist an optional structured `layout_json` (a `GymkhanaLayout`) alongside the existing `layout_ascii`/`layout_alt`; this requires an **Alembic migration** (additive column; see *DB Changes*).
- **FR-009 [Phase A]**: The ~24 seeded drills/gymkhana exercises' existing ASCII circuit layouts MUST be backfilled into equivalent `GymkhanaLayout` JSON, preserving the meaning of each croquis from `docs/14-tecnica-gymkana-7-15/research.md`. Backfill MUST be idempotent (re-runnable) and MUST NOT destroy `layout_ascii`/`layout_alt`.
- **FR-010 [Phase A]**: Where a `GymkhanaLayout` exists, the in-app and document renderers MUST prefer it; where it is absent but `layout_ascii` exists, they MUST fall back to the legacy ASCII croquis (transition compatibility).

**Joint session authoring (composer)**
- **FR-011 [Phase B]**: The system MUST provide a drag-and-drop composer (`/technique/composer`) where the coach places, repositions, rotates, and removes circuit elements on a bounded canvas, producing a `GymkhanaLayout`.
- **FR-012 [Phase B]**: The composer MUST read and write the **same** `GymkhanaLayout` schema as the static renderer (full round-trip): a saved layout reopened in the editor and re-rendered in `<CircuitDiagram>` MUST be equivalent.
- **FR-013 [Phase B]**: The coach MUST be able to assemble **several individual catalog exercises into one combined gymkhana session**, arranged into warm-up / main set / cool-down, with a combined `GymkhanaLayout` attached.
- **FR-014 [Phase B]**: On save, the combined session MUST be persisted **through the existing Training Sessions module** (reusing feature 018's `TechniqueSessionExercise` link and session-assembly flow) as a normal club training session — it MUST NOT create a separate, parallel session store.
- **FR-015 [Phase B]**: A saved combined session MUST appear where club training sessions already appear (calendar/session list) and MUST support the existing attendance and rubric flows; editing its layout again MUST update the same session, not create a duplicate.
- **FR-016 [Phase B]**: The composer MUST honor feature 018's mixed-age-band behavior: a combined session spanning age bands is allowed but visibly flagged.

**Accessibility, privacy & principles (both phases)**
- **FR-017 [Phase A]**: Every rendered diagram (in-app and document) MUST expose an accessible text alternative (`role="img"` + `<title>`/`<desc>` or equivalent, reusing/deriving from `layout_alt`), meeting the project's WCAG 2.1 AA commitment; the diagram MUST NOT rely on color alone to distinguish element kinds.
- **FR-018 [Phase B]**: The drag-and-drop composer MUST provide a keyboard- and screen-reader-accessible path to add, position (nudge), and remove elements (not pointer-drag only), preserving WCAG AA operability on the coach's tablet.
- **FR-019 [both]**: `GymkhanaLayout` content (including any element `label`) is non-sensitive circuit data and MUST NOT contain minor PII; the system MUST NOT prompt for or store an athlete's name/DOB/medical data in a diagram, and MUST NOT leak minor PII via diagrams in logs, documents, or any AI/third-party path (no AI is involved in this feature).
- **FR-020 [both]**: All diagram/composer copy, legends, palette labels, and document captions MUST be in español neutro (Colombia), consistent with feature 018.
- **FR-021 [both]**: Access to the diagram/composer surfaces MUST remain restricted to coach/admin (inheriting feature 018 RBAC); no athlete- or parent-facing surface is introduced. *(Note: gymkhana circuit diagrams may appear in coach/admin-rendered documents per existing document RBAC; this feature does not create a new parent-facing diagram surface.)*
- **FR-022 [both]**: Content rendered or authored MUST stay consistent with the club's non-negotiables (fun first; skills before fitness; biological > chronological age; differentiated age-band methodology). The diagram is descriptive of placement only and MUST NOT introduce intensity/load prescription.
- **FR-023 [Phase A]**: In Phase A, circuit elements MUST NOT accept free-text labels. Phase A uses only a **controlled label set** — the element-kind name (e.g. "Cono", "Puerta", "Mina", "Equilibrio") and an optional sequence number (`#n`) for ordering stations. Free-text `label` is deferred to the Phase B editor, where it MUST be guarded against minor PII (no athlete name/DOB; see FR-019). *(O-5 resolved — minimizes any PII-entry temptation on the diagram surface from day one.)*

### Key Entities *(include if feature involves data)*

- **GymkhanaLayout** *(new — the keystone)*: a JSON document describing one 2D circuit. Persisted on a Technique Exercise (Phase A) and on a combined technique session's exercise set (Phase B). Library-agnostic; the single source of truth for every renderer and the editor. *(Konva's own `toJSON()` is explicitly NOT used as the persisted format — see Decision Record.)*
- **Circuit Element** *(new — embedded in GymkhanaLayout)*: a placed item on the canvas with a `kind` (cone | line | gate | mine | arrow | beam | ring), an `x`/`y` position, an optional `rotation`, and an optional non-PII `label`.
- **Technique Exercise** *(extended, feature 018 `TechniqueExercise`)*: gains an optional `layout_json` (`GymkhanaLayout`) field beside the existing `layout_ascii`/`layout_alt`. No other field changes.
- **Combined Gymkhana Session** *(Phase B — not a new entity)*: a club training session created through the existing Training Sessions module, referencing several exercises via the existing `TechniqueSessionExercise` link. Its combined circuit is **derived at view time** from the linked exercises' `GymkhanaLayout`s (O-3) — it is **not** persisted separately. No parallel session table, no new column.

### GymkhanaLayout Data Model

The canonical, library-agnostic schema (mirrored as Zod on the client and Pydantic on the server):

```
GymkhanaLayout {
  width:  number            // canvas units (e.g. logical cm or grid units), > 0
  height: number            // canvas units, > 0
  elements: CircuitElement[]
}

CircuitElement {
  kind:      'cone' | 'line' | 'gate' | 'mine' | 'arrow' | 'beam' | 'ring'
  x:         number         // 0 ≤ x ≤ width
  y:         number         // 0 ≤ y ≤ height
  rotation?: number         // degrees, optional (default 0)
  style?:    'dashed' | 'solid'   // line only: dashed = guía/libre, solid = técnico (O-2)
  label?:    string         // Phase B only; Phase A uses a controlled set (see O-5/FR-023)
}
```

Notes:
- `kind` values are stable identifiers; their **display** labels are Spanish legend strings resolved at render time (not stored), keeping the schema language-neutral while product copy stays español neutro.
- **Single `line` kind (O-2 resolved)**: there is **one** `line` kind. The free-vs-technical distinction is conveyed by the optional `style` field — `dashed` = trayecto guía/libre, `solid` = trayecto técnico/precisión — plus the legend. There is **no** `line_free` / `line_technical` split; the palette stays minimal.
- Coordinates are validated `0 ≤ x ≤ width`, `0 ≤ y ≤ height`; out-of-bounds or non-finite values are rejected (FR-007).
- The schema is intentionally flat and serializable so it round-trips between the static SVG renderer, the Jinja server renderer, and the Konva editor without lib-specific fields.

### DB Changes / Migration

- **Additive column** `layout_json` (JSON / nullable) on `technique_exercises`, beside the existing `layout_ascii` (Text, nullable) and `layout_alt` (Text, nullable). No column is dropped in Phase A (ASCII retained for fallback, FR-010).
- **Alembic migration required (Phase A)**: add the nullable `layout_json` column. The current Alembic head is the single head `e1f2a3b4c5d6` (`e1f2a3b4c5d6_technique_gymkhana_library.py`) — confirmed via `alembic heads` (one head, **no merge migration needed**). The new revision chains `down_revision='e1f2a3b4c5d6'`. Migration verified on SQLite via tests per project convention; runs in prod via `entrypoint.sh` (`alembic upgrade head`).
- **Seed/backfill (Phase A)**: an idempotent data step (migration data step or re-runnable seed) populates `layout_json` for the seeded gymkhana exercises from their ASCII croquis, leaving `layout_ascii`/`layout_alt` intact.
- **Phase B — no new migration (O-3 resolved)**: the combined session's circuit is **derived at view time** from the `GymkhanaLayout`s of its linked exercises (via `technique_session_exercises`); it does **NOT** persist its own layout. `training_sessions` gains **no** new column. The combined session reuses `training_sessions` + `technique_session_exercises` exactly as feature 018. Phase B therefore adds **zero** migrations.

### Integration Points

- **Feature 018 (Technique & Gymkhana Library)**: extends `TechniqueExercise` (adds `layout_json`); replaces the in-app `CircuitLayout.tsx` ASCII `<pre>` with `<CircuitDiagram>` (SVG), keeping ASCII fallback; reuses the existing skill taxonomy, filtering, catalog, RBAC, privacy posture, and the `SessionAssembler` / `TechniqueSessionExercise` session-assembly flow for the Phase B composer.
- **Training Sessions module (Phase 1.5)**: the Phase B combined gymkhana session is a normal `TrainingSession` (calendar/list, attendance, rubric) — no parallel store (FR-014/015), exactly as feature 018 US3.
- **PDF/email document pipeline**: a new Jinja inline-SVG partial under `templates/documents/pdf/` (sibling to `charts/*.svg.jinja`) renders `GymkhanaLayout` server-side (FR-005), reusing the existing brand tokens and the established print-clean inline-SVG approach.
- **Feature 012 (Perceived Performance Cache / cold-start)**: diagram and composer async surfaces reuse the shared loading / "server starting" states.

### Chosen-Library Decision Record

Adopted from the completed deep-research pass (24 adversarially-verified claims). **Two tools for two jobs — static diagrams ≠ interactive editor.**

- **(a) Static drill diagrams → declarative inline SVG** (hand-authored React components; **no canvas library, no new heavy dependency**). Rationale: no mature drop-in tactic-board library exists (the open-source options are all <16 stars); inline SVG is print/PDF-friendly — which matters because diagrams must render in the existing Jinja inline-SVG PDF/email pipeline — crisp at any zoom, and accessible via `role="img"` + `<title>`/`<desc>`. Canvas does neither print nor a11y well.
- **(b) Coach drag-and-drop authoring (Phase B) → `react-konva` (Konva)** — MIT-licensed, actively maintained, pinned to React 19 (peer dep `react ^19.2.0`), declarative React bindings, built-in `draggable` nodes + `Transformer`, and all needed shape primitives. Lower priority than the static diagrams.
- **Architectural keystone**: define **one** plain `GymkhanaLayout` JSON schema that drives BOTH the static SVG renderer AND the later Konva editor and is what is persisted. **Konva's own `toJSON()` is explicitly NOT sufficient** (verified: it drops images/handlers/custom logic), so we own the schema and decouple DB format from rendering lib.
- **Rejected alternatives**:
  - **tldraw** — proprietary; dev-only default license; ~$6,000/yr commercial; watermark. Non-starter for a youth club on a Render free tier.
  - **Excalidraw** — general whiteboard; wrong UX for a structured circuit palette.
  - **Pixi.js** — WebGL; overkill; poor print/a11y story.
  - **Fabric.js** — no first-class React bindings.
- **Stack confirmation**: shadcn/ui officially supports Tailwind v4 + React 19 (matches the project stack).

### Accessibility (WCAG 2.1 AA)

- Every diagram (in-app and document) exposes a text alternative (`role="img"` + `<title>`/`<desc>` from/derived from `layout_alt`); element kinds are distinguished by shape/pattern + label, **not color alone** (FR-017).
- The Phase B composer provides a keyboard- and screen-reader-operable path to add/position/remove elements beyond pointer-drag (FR-018), so the tablet-in-the-field coach is never blocked by a drag-only interaction.
- Legends, palette labels, and captions are real text (not baked into raster), keeping them translatable and SR-readable.

### Privacy (minors)

- `GymkhanaLayout` is non-sensitive circuit geometry. In Phase A, elements carry **no free-text label** — only the controlled kind name + optional `#n` (FR-023), removing any PII-entry surface. In Phase B, the editor's free-text `label` MUST be guarded against minor PII (no athlete name/DOB); the UI MUST NOT prompt for athlete names on a diagram (FR-019).
- No athlete data flows through diagram rendering. **No AI/LLM is involved in this feature** (consistent with feature 018), so there is no model-prompt exposure surface.
- A `data-privacy-guard` review is still required before close (per project constraint) to confirm no minor PII path is introduced via labels, logs, or document captions.

### Out of Scope

- Re-specifying feature 018 (catalog, filters, exercise detail content, per-athlete skill progress, curation/hide, RBAC) — unchanged here except the explicit extensions above.
- Any **AI/LLM** generation or auto-layout of circuits — explicitly excluded (feature 018 had no AI; this keeps that stance).
- Real-time multi-user collaborative editing of the canvas.
- Importing/exporting third-party diagram formats (e.g. tldraw/Excalidraw files), or generating GPX/real-world geo-coordinates from a circuit.
- A parent- or athlete-facing diagram surface or a public share link.
- Rich media on the canvas (photos/video of minors) — diagrams are vector geometry only.
- Animation of bike movement (arrows indicate direction statically, not animated paths).
- Removing the legacy `layout_ascii`/`layout_alt` columns — **retained** (O-4 resolved) as the screen-reader text-alternative source and as transition fallback; dropping them is deferred to a later cleanup spec once backfill coverage is universally verified.
- Embedding circuit diagrams in the monthly technical report or the newsletter (O-1 resolved — Phase A targets only the printable session sheet).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 [Phase A]**: 100% of seeded gymkhana exercises that currently have an ASCII croquis render a graphical 2D diagram from `layout_json`, with the ASCII fallback exercised only when `layout_json` is absent.
- **SC-002 [Phase A]**: The same `GymkhanaLayout` renders visually equivalent diagrams in-app and in the server-side PDF/email pipeline (verified by inspecting both surfaces for the same exercise), with **zero** external image fetches in the document output.
- **SC-003 [Phase A]**: Every rendered diagram exposes a non-empty text alternative and distinguishes element kinds without relying on color alone (verified by automated a11y checks + inspection); **zero** WCAG AA violations on the diagram surfaces.
- **SC-004 [Phase A]**: A coach opening a gymkhana exercise sees the diagram render correctly at tablet width and stays crisp on zoom (vector), with no layout overflow.
- **SC-005 [Phase B]**: A coach can compose a combined gymkhana session from ≥2 catalog exercises with a drag-and-drop circuit and save it in a single flow; **100%** of such sessions appear as normal club training sessions in the existing calendar/session list (no parallel/duplicate session records).
- **SC-006 [Phase B]**: A combined `GymkhanaLayout` round-trips losslessly: saved → reopened in the editor → re-rendered statically with no loss of elements, positions, rotations, or labels.
- **SC-007 [both]**: **Zero** minor-PII leakage via diagrams (labels, logs, documents) and **zero** athlete-/parent-facing diagram surface introduced (coach/admin only), confirmed by privacy audit.

## Assumptions

- **Phasing**: Phase A (graphical diagrams + backfill + schema) ships first and is independently valuable; Phase B (Konva composer + joint-session authoring) follows and depends on the Phase A schema. The coach prioritized the diagrams over the editor.
- **One schema, two renderers**: the persisted format is the project-owned `GymkhanaLayout`, not any library's serialization; both the React SVG component and the Jinja SVG partial consume it.
- **ASCII retained during transition**: `layout_ascii`/`layout_alt` stay as fallback; they are not dropped in this feature.
- **No AI**: consistent with feature 018, there is no LLM in this feature.
- **Access**: coach/admin only; athletes do not log in; no new parent surface.
- **Connectivity**: tablet-in-the-field over intermittent 3G/4G against a cold-startable backend; reuse feature 012 loading/"server starting" states.
- **Document surfaces**: the printable session sheet is the primary document target for embedded circuit diagrams; `/speckit-plan` confirms exactly which existing documents embed circuits.
- **Backfill fidelity**: the ASCII→`GymkhanaLayout` backfill preserves the *meaning* of each croquis (element placement/sequence) from the research report; pixel-perfect reproduction of the ASCII art is not required.
- **Coordinate system**: `GymkhanaLayout` uses abstract logical canvas units (not real-world meters); a future enhancement could attach a scale, out of scope here.

## Resolved Decisions *(closed by coach/PM, 2026-06-30 — were Open Questions)*

- **O-1 — Resolved**: Phase A embeds the diagram in **the printable session sheet only**. The monthly technical report and the newsletter are **out of scope** for embedded circuit diagrams (a later spec may extend them). Reflected in **FR-005** and Out of Scope.
- **O-2 — Resolved**: **One** `kind: 'line'`, distinguished by an optional `style` field (`dashed` = guía/libre, `solid` = técnico) plus the legend. **No** `line_free` / `line_technical` split. Reflected in the *GymkhanaLayout Data Model* palette and legend.
- **O-3 — Resolved**: For Phase B the combined session's circuit is **derived at view time** from the linked exercises' `GymkhanaLayout`s; it does **NOT** persist its own layout. `training_sessions` gains **no** new column → **no second migration**. Reflected in *DB Changes* and the Combined Gymkhana Session entity.
- **O-4 — Resolved**: **Retain** `layout_ascii`/`layout_alt` as the screen-reader text-alternative source and transition fallback; defer their removal to a later cleanup spec. Reflected in Out of Scope.
- **O-5 — Resolved**: Phase A diagrams carry **no free-text labels** — only a controlled set (element-kind name + optional `#n` sequence number). Free-text `label` is deferred to the Phase B editor with anti-PII guards. Reflected in **FR-023** and the *Privacy* section.
- **O-6 — Resolved (coach/PM, Phase B kickoff)**: resolves the tension between FR-011/FR-012/SC-006 (free-form, round-trippable combined circuit) and O-3 (derived, no persistence). The Phase B composer's free-form combined `GymkhanaLayout` is **persisted in a hidden synthetic `technique_exercises` row** (`is_hidden=True`, `is_gymkhana=True`, `layout_json=<combined>`) — it **reuses the existing `layout_json` column, so there is STILL no new migration**. The combined session links this synthetic exercise **plus** its component exercises via the existing `technique_session_exercises`. This supersedes O-3's "derived at view time" for the free-form case: re-opening loads the synthetic exercise's `layout_json` (lossless round-trip, SC-006); re-editing updates that same row (no duplicate session, FR-015). The synthetic row is kept out of the catalog via the existing `is_hidden` flag. Phase-B element `label`s are allowed but anti-PII validated; the Phase A strict no-free-text guard (FR-023) and its tests are **unchanged** (a separate Phase-B validation path).

## Dependencies

- **Feature 018 (Technique & Gymkhana Library)** — the catalog, `TechniqueExercise`, `CircuitLayout`/detail surfaces, `SessionAssembler`, and `TechniqueSessionExercise` link this feature extends.
- **Training Sessions module (Phase 1.5)** — the combined gymkhana session is a normal training session (calendar/list, attendance, rubric).
- **PDF/email document pipeline** — existing Jinja inline-SVG partials (`templates/documents/pdf/charts/*.svg.jinja`, `_brand_tokens.html`) the server-side circuit renderer mirrors.
- **Feature 012 (cold-start UX)** — shared loading / "server starting" states for diagram and composer surfaces.
- **`react-konva` (Phase B only)** — MIT, React 19-compatible drag-and-drop editor library (new client dependency, Phase B).
- **`docs/14-tecnica-gymkana-7-15/research.md`** — source of the seeded circuits to backfill into `GymkhanaLayout`.
