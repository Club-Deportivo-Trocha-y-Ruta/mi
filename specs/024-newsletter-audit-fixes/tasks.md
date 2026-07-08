# Tasks: Newsletter Audit Fixes — Boletín Mensual Individual

**Input**: Design documents from `/specs/024-newsletter-audit-fixes/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R16), data-model.md, contracts/metrics-snapshot.md, quickstart.md

**Tests**: INCLUDED — la constitución (Principio II, NON-NEGOTIABLE) exige test de regresión que falle sobre el código sin corregir para cada bug fix. Tests primero dentro de cada story.

**Organization**: Tareas agrupadas por user story (spec.md US1–US4), independientes y entregables por separado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Paralelizable (archivos distintos, sin dependencia pendiente)
- **[Story]**: US1–US4
- Cada tarea incluye **agente asignado y modelo** — regla del proyecto: agentes especializados corren en `sonnet`; tareas mecánicas simples en `haiku`. **Nunca `fable`.**

## Asignación de agentes

| Agente | Modelo | Ámbito |
|---|---|---|
| `fastapi-architect` | sonnet | Builder, servicios backend, templates Jinja PDF/email |
| `qa-engineer` | sonnet | Tests pytest/vitest, fixtures, regresión |
| `prompt-engineer` | sonnet | Prompt `.j2` de narrativa IA + registry |
| `react-ui-engineer` | sonnet | Preview frontend + mocks msw |
| `data-privacy-guard` | sonnet | Invariantes de privacidad (data URIs, email) |
| `technical-writer` | haiku | Docs / CLAUDE.md |
| `general-purpose` | haiku | Ediciones mecánicas de strings/CSS en templates |

---

## Phase 1: Setup

**Purpose**: Sin infraestructura nueva — feature es corrección sobre módulo existente. Única preparación: rama y baseline verde.

- [x] T001 Verificar baseline: `cd backend && pytest -q` y `cd frontend && npx vitest run` en branch `024-newsletter-audit-fixes`; anotar suites tocadas por el feature (agent: qa-engineer · sonnet)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Helpers compartidos y fixture de compatibilidad que consumen varias stories.

**⚠️ CRITICAL**: Bloquea US1–US4.

- [x] T002 [P] Crear util compartido `format_date_es(d: date) -> str` ("1 de agosto de 2026") en `backend/app/services/utils/dates_es.py`, portando el patrón `_MONTHS_ES` de `backend/app/services/notification/race_insight_dispatcher.py:135-151` (sin babel, sin locale), y registrarlo como filtro Jinja en `backend/app/services/notification/document_generator.py` (junto a `markdown`/`hms`) — R8 (agent: fastapi-architect · sonnet)
- [x] T003 [P] Tests unitarios de `format_date_es` (meses con tilde, límites de año) en `backend/tests/test_dates_es.py` (agent: qa-engineer · sonnet)
- [x] T004 [P] Crear fixture de snapshot pre-024 (dict `metrics_snapshot` con `streak_days`, sin `focus_groups`/`weekly_hours_avg`/`short_label`) en `backend/tests/fixtures/newsletter_snapshot_pre024.py` para tests de compatibilidad FR-015 — R15 (agent: qa-engineer · sonnet)

**Checkpoint**: Helpers y fixture listos — stories pueden arrancar en paralelo.

---

## Phase 3: User Story 1 — Datos correctos y confiables (Priority: P1) 🎯 MVP

**Goal**: Etiqueta CD/CN correcta (A1), género correcto en narrativa IA (A2), referencia RPE veraz (A4), cumplimiento LTAD semanal (A5).

**Independent Test**: Regenerar boletín junio 2026 de atleta femenina con resultado en Campeonato Departamental → KPI "CD", narrativa "su hija", RPE "base: 3-5", horas "≈6,4 h/sem ≤ 13,9 ✓" (quickstart §3 A1/A2/A4/A5).

### Tests for User Story 1 (escribir PRIMERO, deben FALLAR sobre código actual)

- [x] T005 [P] [US1] Test regresión A1: `_build_race_block` emite `short_label="CD"` para championship departamental y `"V3"` para cup; render del template PDF con snapshot championship NO contiene "V1" en el KPI card — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)
- [x] T006 [P] [US1] Test regresión A2: contexto IA incluye `athlete_reference="su hija"` para sex=F, `"su hijo"` para M, `"su hijo/a"` para None; prompt renderizado contiene la instrucción de género — en `backend/tests/test_athlete_monthly_newsletter_ai.py` (agent: qa-engineer · sonnet)
- [x] T007 [P] [US1] Test regresión A4+A5: template PDF no contiene "ideal 6-7"; snapshot con 27.5h y edad 13.9 emite `weekly_hours_avg=6.4`, `ltad_limit_hours=13.9`, `ltad_status="ok"`; mes sin sesiones → los tres campos null — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)

### Implementation for User Story 1

- [x] T008 [US1] A1 builder: añadir `short_label` (vía `_race_short_label`) a cada item de `results` en `_build_race_block`, `backend/app/services/training/newsletter_builder.py:503-520` — R1 (agent: fastapi-architect · sonnet)
- [x] T009 [US1] A1 template: KPI card usa `{{ last_race.short_label or ('V' ~ last_race.valida_num) }}` en `backend/templates/documents/pdf/athlete_monthly_newsletter.html:245` (fallback para snapshots viejos); verificar tabla/detalle ya usan `r.label` — R1/R15 (agent: fastapi-architect · sonnet)
- [x] T010 [US1] A2 use case: derivar `athlete_reference` desde `Athlete.sex` en `build_context_from_metrics` + `context_dict`, `backend/app/services/ai/use_cases/athlete_monthly_newsletter.py:119,263-280`; nunca loggear junto a nombre — R2/R16 (agent: fastapi-architect · sonnet)
- [x] T011 [US1] A2 prompt: instruir uso exacto de `{{ athlete_reference }}` y concordancia gramatical en `backend/app/services/ai/prompts/athlete_monthly_newsletter_v1.j2` + clave en `backend/app/services/ai/prompts/registry.py`; salida JSON sin cambio de schema — R2 (agent: prompt-engineer · sonnet)
- [x] T012 [P] [US1] A4 template: reemplazar referencia RPE por "0-10 (base: 3-5 · alta intensidad: 6-8)" en `backend/templates/documents/pdf/athlete_monthly_newsletter.html:455-457` — R4 (agent: general-purpose · haiku)
- [x] T013 [US1] A5 builder: calcular `weekly_hours_avg`, `ltad_limit_hours` (`compute_age_decimal(birth_date, generation_date)` de `backend/app/services/category.py:6`), `ltad_status` en `_build_technical_block`, `backend/app/services/training/newsletter_builder.py:386-454`; pasar fecha de generación — R5 (agent: fastapi-architect · sonnet)
- [x] T014 [US1] A5 template: fila de horas muestra "X,X h/sem (límite personal: ≤Y h/sem)" + ✓/⚠ (verde/ámbar según constitución III) con guard `is defined` para snapshots viejos, en `backend/templates/documents/pdf/athlete_monthly_newsletter.html:475-478` — R5/R15 (agent: fastapi-architect · sonnet)

**Checkpoint**: US1 completa — T005–T007 verdes, quickstart §3 filas A1/A2/A4/A5 OK.

---

## Phase 4: User Story 2 — Sin secciones vacías ni redundantes (Priority: P2)

**Goal**: Galería con imágenes embebidas o placeholder u omitida (A3), racha una sola vez con clave/etiqueta correcta (B12), nota de campeonatos en gráfico de puntos (B13).

**Independent Test**: Tres regeneraciones (sin fotos / con fotos / historial con CD) → sección ausente / imágenes visibles / nota al pie (quickstart §3 A3/B12/B13).

### Tests for User Story 2 (primero, deben FALLAR)

- [x] T015 [P] [US2] Test A3: gate de galería 3 estados (0 elegibles → sin sección; elegibles sin embebibles → placeholder con conteo; embebibles → `<img src="data:image/jpeg;base64`) mockeando SFTP — en `backend/tests/test_newsletter_gallery_embed.py` (agent: qa-engineer · sonnet)
- [x] T016 [P] [US2] Test privacidad: `metrics_snapshot` serializado y todo bloque email NUNCA contienen `"data:"` URIs; extiende `backend/tests/test_newsletter_privacy.py` — R16 (agent: data-privacy-guard · sonnet)
- [x] T017 [P] [US2] Test B12: builder emite `streak_sessions` (no `streak_days`); template PDF renderiza racha exactamente una vez con "sesiones seguidas"; snapshot pre-024 (fixture T004) sigue renderizando — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)
- [x] T018 [P] [US2] Test B13: `_build_charts_context` con historial que incluye championship emite `has_championship=True` y el PDF contiene la nota "no otorgan puntos" — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)

### Implementation for User Story 2

- [x] T019 [US2] A3 embedding: extraer helper de descarga+base64 del patrón spec-022 (`build_report_photo_evidence`, `backend/app/services/training/reports.py:430-550`) a `backend/app/services/notification/media_embedding.py` (presupuesto 2 MB, degradación por foto fallida) y consumirlo en render-time desde `backend/app/services/notification/athlete_newsletter_pdf.py` construyendo `photos_render` — R3; NO persistir data URIs (agent: fastapi-architect · sonnet)
- [x] T020 [US2] A3 template: gate de 3 estados sobre `photos_render` (`eligible_count`/`embeddable_count`) + `<img src="{{ photo.data_uri }}">` en `backend/templates/documents/pdf/athlete_monthly_newsletter.html:758-778`; placeholder "N fotos del mes disponibles en la plataforma" — R3 (agent: fastapi-architect · sonnet)
- [x] T021 [US2] B12 builder: renombrar emisión `streak_days`→`streak_sessions` (`backend/app/services/training/newsletter_builder.py:271,294,318`), eliminar `_compute_streak` duplicado (`:366`) reutilizando el de `backend/app/services/training/badge_evaluator.py:75` — R12 (agent: fastapi-architect · sonnet)
- [x] T022 [US2] B12 consumidores: actualizar clave en contexto IA (`backend/app/services/ai/use_cases/athlete_monthly_newsletter.py:87,140,162,270`, `backend/app/services/ai/prompts/registry.py:143`, `athlete_monthly_newsletter_v1.j2:38`); templates PDF+email leen `streak_sessions` con fallback `streak_days`; eliminar la línea duplicada "Racha de asistencia consecutiva" dejando solo el KPI card — R12/R15 (agent: fastapi-architect · sonnet)
- [x] T023 [P] [US2] B12 frontend: verificar `NewsletterPreviewBlocks.tsx` (ya lee `streak_sessions`) contra el contrato corregido; actualizar mock `frontend/src/test/msw/newsletterHandlers.ts:35` a `streak_sessions` y correr `NewsletterPreviewBlocks.test.tsx` + a11y (agent: react-ui-engineer · sonnet)
- [x] T024 [US2] B13: `has_championship` en `_build_charts_context` (`backend/app/services/training/newsletter_builder.py:974-1014`) + nota al pie bajo el gráfico de puntos en el template PDF, espejo de spec-022 (`training_monthly_report.html:445`) — R13 (agent: fastapi-architect · sonnet)

**Checkpoint**: US1+US2 funcionales e independientes.

---

## Phase 5: User Story 3 — Legibilidad para familias (Priority: P2)

**Goal**: Focos agrupados por familia de habilidad (B6), categoría legible (B7), fechas en español (B8).

**Independent Test**: Boletín junio 2026 → "Focos del mes" ≤10 grupos con conteo; "Prejuvenil A" en vez de "PJUV_A_F"; "1 de agosto de 2026" (quickstart §3 B6/B7/B8).

### Tests for User Story 3 (primero, deben FALLAR)

- [x] T025 [P] [US3] Tests de `group_focus_texts`: casi-duplicados de descenso/curvas → un grupo; "Zona 2 FC"/"Vo2 Max" → "Resistencia y acondicionamiento"; texto irreconocible → "Otros"; suma de counts == sesiones con foco; insensible a tildes/mayúsculas — en `backend/tests/test_focus_grouping.py` (agent: qa-engineer · sonnet)
- [x] T026 [P] [US3] Test B7+B8: resultado con `category_code="PJUV_A_F"` emite `category_label` desde seed y código crudo si no mapea; PDF y email muestran fechas "de {mes} de" sin ISO en secciones de familias — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)

### Implementation for User Story 3

- [x] T027 [US3] B6 helper: crear `backend/app/services/training/focus_grouping.py` — función pura `group_focus_texts(list[str]) -> list[FocusGroup]`, keywords accent-insensitive por familia, destinos = 8 familias de `backend/app/data/technique_catalog.py:88-145` + `resistencia_acondicionamiento` + `otros`, primera coincidencia gana, docstring (constitución I) — R6 (agent: fastapi-architect · sonnet)
- [x] T028 [US3] B6 builder+template: emitir `focus_groups` en `_build_technical_block` (lista por sesión, no dedup) y renderizar "Nombre — N sesiones" en el PDF con fallback a `focos_tecnicos` para snapshots viejos; email idem si muestra focos — R6/R15 (agent: fastapi-architect · sonnet)
- [x] T029 [US3] B7: lookup `race_categories.label` por `category_code` en `_build_race_block` (join en query o dict precargado) → `category_label` por resultado; templates PDF+email muestran label con fallback a código — R7 (agent: fastapi-architect · sonnet)
- [x] T030 [US3] B8: aplicar filtro `format_date_es` (T002) a fechas de familias en PDF (`próximas válidas`, `entrenamientos planificados`, resultados, medición antropométrica) y email (`athlete_monthly_newsletter.html` de `templates/email/`), guard para fechas null — R8 (agent: fastapi-architect · sonnet)

**Checkpoint**: US1+US2+US3 independientes y verdes.

---

## Phase 6: User Story 4 — Documento pulido (Priority: P3)

**Goal**: Página 1 aprovechada (B9), gráficos sin clipping (B10), tabla antropométrica legible (B11), tips por banda etaria con rotación mensual (B14).

**Independent Test**: Inspección visual del PDF regenerado + regeneración de dos meses distintos (quickstart §3 B9/B10/B11/B14).

### Tests for User Story 4 (primero, deben FALLAR donde aplique)

- [x] T031 [P] [US4] Test B14: `_build_support_block(age_decimal, month, athlete_reference)` — edad 11 → banda "10-12" (sueño 9-11h, sin mención 13-15); edad 14 → "13-15"; mismo mes+atleta → tips idénticos; meses distintos → algún tip distinto; ningún tip menciona suplementos/calorías — en `backend/tests/test_newsletter_builder_024.py` (agent: qa-engineer · sonnet)
- [x] T032 [P] [US4] Test B10: macros SVG con punto en posición 1 / valor máximo → ningún elemento `<text>` con `y < 0` ni fuera del viewBox; sin `title/desc/metadata` (invariante existente) — en `backend/tests/test_newsletter_svg_charts.py` (agent: qa-engineer · sonnet)

### Implementation for User Story 4

- [x] T033 [P] [US4] B9: quitar `break-inside: avoid` del wrapper completo de valoración (`backend/templates/documents/pdf/athlete_monthly_newsletter.html:331`), conservar `break-after: avoid` en h2 y `break-inside: avoid` solo por subsección (fortalezas/área/hito) — R9 (agent: general-purpose · haiku)
- [x] T034 [P] [US4] B10: `pad_top` 8→16 y clamp `y = max(pad_top - 2, cy - 6)` en `backend/templates/documents/pdf/charts/gap_pct.svg.jinja`, `points_accumulated.svg.jinja`, `line_positions.svg.jinja` — R10 (agent: fastapi-architect · sonnet)
- [x] T035 [P] [US4] B11: en tabla antro (`athlete_monthly_newsletter.html:620-655`) quitar `overflow-wrap:anywhere`/`word-break:break-word` de th, reequilibrar `<colgroup>` (IMC 9%, Z/P 10%) y headers con `<br>` explícito — R11 (agent: general-purpose · haiku)
- [x] T036 [US4] B14: refactor `_build_support_block(age_decimal, month, athlete_reference)` en `backend/app/services/training/newsletter_builder.py:693-737` + variantes de tips (2-3 por categoría, ambas bandas) en `backend/app/services/training/newsletter_static_copy.py`; rotación `month % len(variants)`; emitir `age_band`/`rotation_index`; "hijo/a" → `athlete_reference`; principios no negociables en toda variante — R14 (agent: fastapi-architect · sonnet)

**Checkpoint**: Las 4 stories completas.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T037 Test de compatibilidad FR-015: renderizar PDF y email completos con fixture pre-024 (T004) sin excepción — en `backend/tests/routers/test_athlete_monthly_newsletters_router.py` (agent: qa-engineer · sonnet)
- [x] T038 Suites completas + lint: `cd backend && pytest -q && ruff check app tests`; `cd frontend && npx vitest run && npx eslint src && npx tsc --noEmit` — cero regresiones (constitución I/II) (agent: qa-engineer · sonnet)
- [x] T039 Validación E2E quickstart.md: regenerar boletín junio 2026 en dev, checklist visual de 14 ítems (§3) + verificación email (§5) (agent: qa-engineer · sonnet)
- [x] T040 [P] Auditoría de privacidad final: correr `backend/tests/test_newsletter_privacy.py` + revisión de logs de generación sin PII ni data URIs (agent: data-privacy-guard · sonnet)
- [x] T041 [P] Actualizar `CLAUDE.md` (fila del módulo en Implementation status) y `docs/implementation-status.md` con feature 024 (agent: technical-writer · haiku)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → **Foundational (P2)** → bloquea US1–US4
- **US1 (Phase 3)**: solo depende de Phase 2 (T013 usa `compute_age_decimal`, ya existente)
- **US2 (Phase 4)**: independiente de US1; T022 toca el mismo `.j2` que T011 — si corren en paralelo, coordinar merge (archivo compartido)
- **US3 (Phase 5)**: T030 depende de T002 (filtro Jinja registrado)
- **US4 (Phase 6)**: T036 reutiliza derivación `athlete_reference` de T010 (importa helper; si US4 corre antes, duplicar derivación local y unificar en polish)
- **Polish (Phase 7)**: tras las stories deseadas

### Within Each User Story

Tests primero (fallan sobre código actual) → builder/servicios → templates → integración. Regla constitución II: cada bug fix con test de regresión genuino.

### Parallel Opportunities

- Phase 2: T002, T003, T004 en paralelo
- US1: T005–T007 en paralelo; luego T008+T009 (secuencia), T010→T011, T012 [P], T013→T014
- US2: T015–T018 en paralelo; T019→T020; T021→T022; T023 [P]; T024 [P respecto a galería]
- US3: T025, T026 en paralelo; T027→T028; T029, T030 [P]
- US4: T031–T035 mayormente [P]; T036 al final de la story
- Stories completas US1/US3/US4 pueden avanzar en paralelo con agentes distintos; US2 comparte `.j2` con US1 (ver arriba)

---

## Parallel Example: User Story 1

```bash
# Tests primero (paralelo):
Task qa-engineer(sonnet): "T005 regresión short_label CD en test_newsletter_builder_024.py"
Task qa-engineer(sonnet): "T006 regresión athlete_reference en test_athlete_monthly_newsletter_ai.py"
Task qa-engineer(sonnet): "T007 regresión RPE+LTAD en test_newsletter_builder_024.py"

# Implementación (tras tests rojos):
Task fastapi-architect(sonnet): "T008+T009 short_label builder+template"
Task fastapi-architect(sonnet): "T010 athlete_reference en use case"   # luego T011 prompt-engineer
Task general-purpose(haiku):    "T012 string RPE en template"
Task fastapi-architect(sonnet): "T013+T014 LTAD semanal builder+template"
```

---

## Implementation Strategy

### MVP First (US1 solamente)

1. Phase 1–2 (T001–T004)
2. Phase 3 completa (T005–T014)
3. **STOP y VALIDAR**: quickstart §3 filas A1/A2/A4/A5 — los dos bugs más visibles para familias quedan corregidos
4. Entregable por sí solo (deploy opcional)

### Incremental Delivery

1. US1 → validar → (MVP)
2. US2 → validar (galería + racha + nota)
3. US3 → validar (legibilidad)
4. US4 → validar (pulido visual)
5. Polish T037–T041 → suites, E2E, privacidad, docs

### Modelos — regla dura

Todas las tareas asignadas a `sonnet` o `haiku` según tabla. **Prohibido `fable`/`claude-fable-5` como modelo de agentes de implementación** (instrucción del usuario).

---

## Notes

- [P] = archivos distintos sin dependencia pendiente
- Commit por tarea o grupo lógico (Conventional Commits, tipo inglés + descripción español latino, sin mención de IA)
- Verificar que los tests de regresión FALLAN antes de implementar
- No tocar: informe mensual técnico (spec 022), ingestión de resultados, módulo de competencias, lógica de puntos/rankings
- Sin migración Alembic; sin cambios de schema API
