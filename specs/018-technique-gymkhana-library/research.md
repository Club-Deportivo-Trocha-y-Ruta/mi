# Phase 0 Research: Technique & Gymkhana Library + Session Builder

**Method**: best-practices research via **MCP** (Context7 — SQLAlchemy 2 async relationship/loading docs) and **web search** (ASCII-vs-SVG rendering & accessibility; async many-to-many filtering), plus codebase precedent. Each decision below resolves a spec-deferred unknown or a key technology choice.

---

## D1 — Illustrative circuit-layout representation (resolves the spec's deferred "how")

- **Decision**: Store each layout as **preformatted monospace text** (`layout_ascii`) — the ASCII croquis already authored in §4 of `docs/14-tecnica-gymkana-7-15/research.md` — plus a shared, structured **legend** and a plain-language **text alternative** (`layout_alt`) for screen readers. The frontend renders it in a responsive `<pre>` (horizontal scroll on narrow screens, monospace font, `white-space: pre`) wrapped with `role="img"` + `aria-label`/visually-hidden description. SVG generation and image upload are **explicitly deferred**.
- **Rationale**:
  - **Zero manual data entry to seed** (SC-002): the croquis text exists verbatim in the verified report and seeds directly.
  - **No new dependency** and **offline/low-bandwidth friendly** (Constitution IV): a few hundred bytes of text vs. generated graphics, ideal for tablet-in-the-field over 3G with ~50 s cold starts.
  - **Accessible** (Constitution III, WCAG AA): a `<pre>` block is not screen-reader-friendly on its own, so we ship a text alternative; web guidance recommends pairing ASCII art with a described alternative rather than relying on the glyphs.
  - Trivially **editable** by coach/admin (it's just text), satisfying US5 curation without a diagram editor.
- **Alternatives considered**:
  - *Generated SVG* (svgbob/goat/aasvg-style): prettier and zoomable, but adds a build/runtime conversion step, larger payloads, and per-glyph SVG that is *harder* for screen readers — rejected for v1, kept as a future enhancement.
  - *Uploaded image per exercise*: needs the existing SFTP media path, bandwidth-heavy on 3G, and reintroduces manual data entry for seeding — rejected for v1.

## D2 — Catalog data model & filtering (skill / age band / difficulty / materials)

- **Decision**: Normalize with three relationships off `technique_exercises`: a **many-to-many to `technique_skills`** and **many-to-many to `technique_materials`** (each via a Core `secondary` association table), and an **age-band join** (`technique_exercise_age_bands`, one row per band an exercise targets). Eager-load all three with `selectinload`. Implement the materials filter as a **subset/superset** query: "show exercises whose *required* materials are all within the coach's *available* set" via a correlated `NOT EXISTS` (no required material lies outside the available set), and treat **"sin material"** exercises as always-matching.
- **Rationale**:
  - Context7 / SQLAlchemy 2 docs confirm `relationship(secondary=association_table)` for M2M and that **`selectinload` is the best loader for one-to-many / many-to-many** in async (one extra `SELECT ... IN (...)`, original query unaffected, no N+1) — matching Constitution IV and the codebase's existing use of `selectinload`.
  - Normalized joins (vs. JSON arrays) let the DB filter by skill/material with indexes and express the "available materials" subset cleanly; the catalog is small so query cost is negligible.
  - Difficulty is a small enum (`facil` / `media` / `avanzada`) plus an `is_game` flag (the "🎉 juego puro" engagement exercises); progression ranges like "①→③" live in the how-to text.
- **Alternatives considered**:
  - *JSON columns for skills/materials*: simpler to seed but awkward and unindexed for the combined filters and the materials subset rule — rejected.
  - *`joinedload`*: risks row multiplication across two M2M legs and requires `.unique()`; `selectinload` is cleaner for collections — rejected.

## D3 — Pre-seeding the catalog (≈24 exercises, A–H skills, materials, layouts)

- **Decision**: Seed via a **single idempotent Alembic data migration** that reads a Python seed module (`backend/app/data/technique_catalog.py`) encoding the A–H skill taxonomy (§2), the materials list (§3 "Materiales base"), the 24-exercise bank (§3 table), and the circuit layouts (§4). The migration **skips if exercises already exist** (guard select), flags seeded rows `is_seeded = true`, and inserts in español neutro verbatim from the report. Content is extracted by `data-analyst` and methodology-checked by `technique-coach` / `sports-science-advisor`.
- **Rationale**: Direct precedent exists — `alembic/versions/c4d5e6f7a8b9_seed_race_categories.py` seeds reference rows in a migration, and `entrypoint.sh` runs `alembic upgrade head` on Render, so the catalog populates on deploy **with no manual entry** (SC-002) and in prod (unlike `scripts/seed.py`, which is dev-only).
- **Alternatives considered**:
  - *Seed in `scripts/seed.py`*: never runs in production (`APP_ENV != development`) — rejected.
  - *Runtime "seed on first request"*: adds startup complexity and a race on cold start — rejected; migration-time seeding is deterministic.

## D4 — Session assembly reuses the existing Training Sessions module (FR-011)

- **Decision**: Add a thin assembler service + endpoint that **calls the existing `training_svc.create_session`** to create an ordinary `TrainingSession` (`session_kind = entrenamiento`, technical_focus/objectives derived from the assembled set), then writes the chosen exercises into a new **`technique_session_exercises`** link table (FK → `training_sessions.id` `ON DELETE CASCADE`; FK → `technique_exercises.id` `ON DELETE RESTRICT`) carrying `segment` (warmup / main / cooldown) and `position`. The response is a normal training session that shows up in the existing calendar/list and supports the existing attendance + rubric flows.
- **Rationale**: This **does not fork** session management (FR-011, SC-006); the link table records "which exercises this session was built from" (FR-013) and the `RESTRICT` + hide-not-delete rule guarantees a saved session stays intact when an exercise is later hidden/edited (FR-020). Mixed-age detection (FR-014) is computed server-side from the assembled exercises' age bands and returned as a boolean notice flag.
- **Alternatives considered**:
  - *New `technique_sessions` table*: a parallel store — explicitly forbidden by FR-011 — rejected.
  - *Embed exercise IDs as JSON on the session*: loses referential integrity and the hide/edit-safety guarantee — rejected.

## D5 — Per-athlete skill progress shape (US4, P2)

- **Decision**: Model `athlete_skill_progress` as **append-only events**: one row per `(athlete_id, skill_id, recorded_at)` with `status` ∈ {`introducido`, `en_progreso`, `dominado`}, optional `coach_note`, `recorded_by_user_id`, and a `season` (year). **Current status** = the latest row per `(athlete, skill)`; **season evolution** = the ordered set of rows. No comparison/ranking view or export exists anywhere (enforced by API shape + tests). Tracking is available **only** for athletes who have a record; 7–9 riders without a record are handled gracefully (the progress surface is simply unavailable for them).
- **Rationale**: Append-only gives the season history (FR-016) for free and keeps an auditable trail; latest-per-skill is a cheap windowed read. The 3-state status matches the wording in SC-004 and the spec's resolved Assumption. Anchoring framing to biological age reuses existing PHV/maturation data (no recompute). This is the **only minors-data surface**, so it is coach/admin-only and privacy-audited (`data-privacy-guard`).
- **Alternatives considered**:
  - *Single mutable current-status row*: loses history; would need a separate audit table anyway — rejected.
  - *Numeric level or reuse of the session rubric scale*: set aside for v1 per the spec's Assumption; revisit in `/speckit-clarify` if a finer scale is wanted.

## D6 — Access control & privacy

- **Decision**: Restrict the whole module to **coach/admin** via the existing `require_role([admin, coach])` + club-scoped `user_club_role` checks in `services/permissions.py`; **no parent/athlete views or routes** (FR-021). No minor PII in logs/errors; **no AI/LLM** is used by this feature, so there is no external-prompt surface to scrub.
- **Rationale**: Reuses the proven RBAC helpers; the absence of any athlete/parent surface and of AI keeps the privacy footprint minimal (SC-007). Negative-path tests assert parent/athlete and cross-club denial.

---

## Resolved unknowns summary

| Unknown (from spec) | Resolution |
|---|---|
| Layout rendering (text / graphic / image) | **Preformatted monospace text + legend + a11y text alternative**; SVG/image deferred (D1) |
| Catalog filter modeling | Normalized M2M join tables + `selectinload` + NOT-EXISTS material subset (D2) |
| Seeding mechanism | Idempotent **Alembic data migration** from a seed module (D3) |
| "Through the existing Training Sessions module" | Wrap `create_session` + `technique_session_exercises` link table (D4) |
| Progress granularity & history | Append-only 3-state events; latest = current, set = history (D5) |
| Access & AI/privacy footprint | Coach/admin-only RBAC; **no AI**; US4 is the sole minors surface (D6) |

**No remaining NEEDS CLARIFICATION.**

## Sources

- [SQLAlchemy 2.0 — Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html) (Context7 + web): `selectinload` is the recommended loader for one-to-many / many-to-many.
- [SQLAlchemy 2.0 — Asyncio extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html): eager-load collections (`selectinload`) in async sessions.
- [SQLAlchemy — Basic Relationships (`secondary` association table)](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html): M2M via a Core `Table` as `secondary`.
- [Don Marti — Responsive ASCII art](https://blog.zgp.org/responsive-ascii/) & [IETF Author Resources — Diagrams](https://authors.ietf.org/diagrams): pair ASCII diagrams with a described text alternative; render monospace with `white-space: pre`.
- Codebase precedent: `backend/alembic/versions/c4d5e6f7a8b9_seed_race_categories.py` (migration-time seeding), `backend/app/services/training/sessions.py` (`create_session` reuse), `backend/app/services/permissions.py` (RBAC helpers).
