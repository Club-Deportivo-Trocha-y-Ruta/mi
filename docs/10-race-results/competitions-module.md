# Módulo Competencias — Diseño técnico

**Proyecto:** Club Deportivo Trocha y Ruta — XCO juvenil
**Módulo:** `routers/race_events.py` + `services/race_events.py` + `frontend/src/routes/competitions/`
**Fecha:** 2026-05-27
**Audiencia:** entrenador (UX), arquitecto/dev (mantenimiento), QA
**Entrada autoritativa previa:** `docs/10-race-results/upload-design.md` (Fase 1.7 — ingesta PDF) y `docs/10-race-results/upload-design.md §14` (Fase 1.7+ — condiciones de carrera).

---

## 0. Resumen ejecutivo

El módulo **Competencias** es la capa de **gestión** de las válidas de la Copa Valle XCO. Permite al entrenador y al administrador planificar válidas antes de tener PDFs oficiales (pre-tapering, convocatoria, calendario), asociarlas a eventos del calendario y disparar el flujo de importación de resultados.

Hasta esta fase, una válida solo nacía cuando se ingestaba el PDF oficial (`scripts/ingest_race.py` → `RaceIngestor`). El coach no podía planificar una válida futura ni editar metadata después de la ingesta. Esta entrega abre el ciclo de vida completo del `RaceEvent`: crear vacío → planificar → importar PDF → analizar → eventualmente cancelar.

**Apuesta arquitectónica:** capa CRUD HTTP delgada sobre `RaceEvent`, reutilizando el modelo y los enums existentes. Ningún cambio de schema en MySQL: las columnas y el enum `RaceEventStatus.CANCELLED` ya existían desde la migración `64c263edd07f`.

- **Backend:** 5 endpoints CRUD nuevos + 1 endpoint preexistente de condiciones, 1 servicio nuevo, 5 schemas nuevos, 32 tests, 0 migración Alembic.
- **Frontend:** 4 páginas (List/Form/Detail/Import), 5 componentes reutilizables (FiltersBar/StatusBadges + 5 tabs URL-driven), wizard de importación reubicado, 69 tests vitest nuevos.
- **Privacidad:** los `race_events` son metadata pública de federación; no contienen datos PII de menores.

**No hace:** crear/editar resultados individuales (`PATCH /race-results/{id}`), gestionar `race_series` desde UI (el coach asume Copa Valle), tipificar válidas A/B/C de periodización en el modelo (campo solo en `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx`).

---

## 1. Competencias vs Resultados — separación funcional

| Aspecto | **Competencias** (este módulo) | **Resultados** (Fase 1.7) |
|---|---|---|
| Verbo dominante | Gestionar | Analizar |
| Sidebar | "Competencias" | "Análisis IA" (insights post-ingest) |
| Casos de uso | Crear válida vacía, editar fecha/sede, asociar a calendario, lanzar wizard de import, cancelar | Tablas de posiciones, gap a podio, evolución del atleta, ranking del club, proyección |
| Persistencia primaria | `race_events` (metadata) | `race_results`, `riders`, `race_competitors` |
| Endpoints | `/api/race-analysis/race-events/*` (CRUD) | `/api/race-analysis/imports/*` (ingesta) + `/api/race-analysis/athletes/*` (analítica) |
| Crea datos | Sí (el evento contenedor) | Sí (resultados + competidores) pero condicionado a un `race_event` existente |
| Borra datos | Sí (admin only, si no hay dependencias) | No — el coach no borra resultados; reingesta el PDF |
| Audiencia | Coach + admin | Coach + admin (parents ven solo sus propios datos a través de boletines / portal padres) |

**Punto de unión:** desde el detalle de una competencia, el coach hace clic en "Importar resultados" y arranca el wizard de Fase 1.7 con el `race_event_id` precargado. La importación adjunta `race_results` al `race_event` ya creado, en vez de inferirlo del PDF.

---

## 2. Arquitectura

### 2.1 Componentes nuevos

```
backend/
├── app/
│   ├── routers/race_events.py          # NUEVO — 5 endpoints CRUD + 1 preexistente
│   ├── services/race_events.py         # NUEVO — lógica de negocio + guards
│   └── schemas/race_event.py           # NUEVO — 5 schemas Pydantic v2
└── tests/routers/test_race_events_crud.py  # NUEVO — 32 tests

frontend/
├── src/
│   ├── api/raceEvents.ts                       # EXTENDIDO — get/create/update/delete/list
│   ├── hooks/race/useRaceEvents.ts             # NUEVO — query keys + invalidaciones cruzadas
│   ├── routes/competitions/
│   │   ├── CompetitionsListPage.tsx            # NUEVO
│   │   ├── CompetitionFormPage.tsx             # NUEVO (create + edit)
│   │   ├── CompetitionDetailPage.tsx           # NUEVO (header + 5 tabs URL-driven)
│   │   └── CompetitionImportPage.tsx           # NUEVO (monta wizard, con/sin :id)
│   ├── components/competitions/
│   │   ├── CompetitionFiltersBar.tsx           # NUEVO
│   │   ├── CompetitionStatusBadges.tsx         # NUEVO
│   │   ├── tabs/{InfoTab,ResultsTab,           # NUEVO — 5 tabs extraíbles
│   │   │       ConditionsTab,AthletesTab,
│   │   │       InsightsTab}.tsx
│   │   └── import/{ImportWizard,RaceUploadZone,DiffTable}.tsx
│   │                                           # MOVIDO desde components/ai/
│   └── test/msw/raceEventsHandlers.ts          # EXTENDIDO
```

### 2.2 Endpoints backend

Todos bajo prefix `/api/race-analysis/race-events/`.

| Método | Ruta | Propósito | RBAC | Códigos |
|---|---|---|---|---|
| `GET` | `/` | Listado con filtros `season`, `status`, `is_championship`, `location`. Devuelve `RaceEventListItem[]` con flags derivados `has_results`, `has_calendar_event`, `conditions_completeness`. | coach + admin | 200, 403 |
| `GET` | `/{race_event_id}` | Detalle completo con flag `has_calendar_event` calculado vía EXISTS. | coach + admin | 200, 404, 403 |
| `POST` | `/` | Crea evento vacío (sin resultados). Valida FK `series_id` (422) y unicidad `(series_id, sequence_number)` (409). | coach + admin | 201, 404, 409, 422, 403 |
| `PATCH` | `/{race_event_id}` | Update parcial de metadata (`name`, `event_date`, `location`, `sequence_number`, `status`, `is_championship`). **No toca condiciones.** | coach + admin | 200, 404, 409, 422, 403 |
| `DELETE` | `/{race_event_id}` | Borra evento sin dependencias. Verifica primero `race_results` y `calendar_events` para devolver 409 con mensaje legible antes de que MySQL rechace el RESTRICT. | **admin only** | 204, 404, 409, 403 |
| `PATCH` | `/{race_event_id}/conditions` | **Preexistente (Fase 1.7+)** — actualiza clima, temperatura, superficie, altitud, notas. | coach + admin | 200, 404, 422, 403 |

**Convención del 409 en DELETE:** el coach que necesita "ocultar" una válida pasada usa `PATCH /{id}` con `status=cancelled`, no DELETE. DELETE es para eventos creados por error que aún no tienen historial.

### 2.3 Schemas Pydantic v2 (`backend/app/schemas/race_event.py`)

| Schema | Uso | Notas |
|---|---|---|
| `_ConditionsFields` | Mixin con los 5 campos de condiciones | Reutilizado por `RaceEventCreate` para permitir capturar condiciones desde el form de creación si el coach las conoce. |
| `RaceEventCreate` | Body de `POST /` | `extra="forbid"`, `str_strip_whitespace=True`. Requiere `series_id`, `sequence_number` (1-99, 99 = CD por convención), `name`, `event_date`. |
| `RaceEventUpdate` | Body de `PATCH /` | Todos los campos opcionales; `exclude_unset=True` para distinguir "no envió" de "envió null". |
| `RaceEventRead` | Response de POST/PATCH/GET | Incluye `has_calendar_event` calculado en el endpoint (no es columna). |
| `RaceEventListItem` | Item del listado | Incluye `has_results`, `has_calendar_event`, `conditions_completeness: Literal["complete", "partial", "empty"]`. |
| `RaceEventListResponse` | Wrapper de `GET /` | `{items: [...], total: N}` — total = `len(items)` (no paginación: 7 válidas/año × pocas temporadas). |

### 2.4 Servicio (`backend/app/services/race_events.py`)

| Función | Responsabilidad | Guards |
|---|---|---|
| `create_race_event` | INSERT con valor por defecto `status=SCHEDULED`. | `_check_series_exists` (422) + `_check_sequence_unique` (409). |
| `update_race_event` | UPDATE parcial vía `setattr`. | Si cambia `sequence_number`, vuelve a verificar unicidad excluyendo el propio id. Body vacío → no-op (devuelve estado actual). |
| `delete_race_event` | DELETE + flush. | Verifica `RaceResult.event_id` y `CalendarEvent.race_event_id` con EXISTS antes de ejecutar. |
| `list_race_events` | SELECT con subqueries escalares correlacionadas para `has_results` y `has_calendar_event`. | Filtro `season` via JOIN a `race_series.season_year`. `location` con `ILIKE` parcial. Orden por `event_date ASC`. |
| `_completeness(event)` | Helper privado | Cuenta cuántos de los 5 `_CONDICIONES_CAMPOS` no son `None`: 0=empty, 5=complete, otro=partial. |

---

## 3. Flujos del coach

### 3.1 Flujo pre-PDF: planificar una válida futura

1. El coach abre **Sidebar → Competencias**.
2. Pulsa **"Nueva competencia"** → `CompetitionFormPage` en modo create.
3. Selecciona `sequence_number` (1-7 o 99 si CD), captura nombre, fecha, sede.
4. La altitud se autocompleta desde `VENUE_ALTITUDES` (`frontend/src/types/raceEvents.types.ts`) — catálogo de 7 sedes Copa Valle (Sevilla, Ginebra, La Cumbre, Cali, Palmira, Roldanillo, Yumbo).
5. `POST /api/race-analysis/race-events/` con `series_id=1` (Copa Valle hardcoded — ver §6 TODOs).
6. Redirección a `CompetitionDetailPage` con `status=SCHEDULED`, sin tabs de resultados aún.
7. (Opcional) Pulsa **"Asociar a calendario"** → navega a `/calendar/events/new?race_event_id={id}` y rellena formulario de `CalendarEvent` precargado.

### 3.2 Flujo post-PDF: importar resultados

1. Desde la lista, el coach abre el detalle de la competencia ya creada (o crea una nueva inline desde el wizard si no existe).
2. Pulsa **"Importar resultados"** → `CompetitionImportPage` carga `ImportWizard` con `race_event_id` precargado (sin requerir paso 2 del wizard si la metadata ya está completa).
3. El wizard sigue el flujo de Fase 1.7 (parse → dry-run → commit), guardando PDF en SFTP Hostinger.
4. Al commit, las invalidaciones cruzadas (`useRaceEvents` + `useImports`) refrescan el detalle: aparecen las tabs **Resultados**, **Atletas** e **Insights**.
5. El coach captura condiciones de carrera vía la tab **Condiciones** (PATCH `/{id}/conditions`).

### 3.3 Flujo de cancelación o borrado

| Caso | Acción | Endpoint |
|---|---|---|
| Válida pospuesta o suspendida con histórico | Coach edita status → `cancelled` | `PATCH /{id}` |
| Válida creada por error sin resultados ni calendario | Admin borra | `DELETE /{id}` → 204 |
| Válida tiene resultados ingestados | Borrado bloqueado | `DELETE /{id}` → 409 |

---

## 4. Frontend — rutas y RBAC

| Ruta | Componente | RBAC | Notas |
|---|---|---|---|
| `/competitions` | `CompetitionsListPage` | coach + admin | Tabla densa en desktop, cards en mobile. Filtros temporada/estado/sede/championship. Kebab por fila: editar, importar, asociar calendario, borrar (admin). |
| `/competitions/new` | `CompetitionFormPage` (create) | coach + admin | RHF + Zod. Auto-altitud. Maneja 409 inline. Soporta query `?returnTo`. |
| `/competitions/:id` | `CompetitionDetailPage` | coach + admin | Header + 5 tabs URL-driven (`?tab=info|results|conditions|athletes|insights`). Tabs Athletes e Insights cargan lazy. |
| `/competitions/:id/edit` | `CompetitionFormPage` (edit) | coach + admin | Reuso del form en modo edit con `useRaceEvent(id)`. |
| `/competitions/import` | `CompetitionImportPage` (sin id) | coach + admin | Wizard para crear válida nueva desde el PDF. |
| `/competitions/:id/import` | `CompetitionImportPage` (con id) | coach + admin | Wizard precargado con metadata del `race_event` existente. |

**Parent guard:** los 6 paths usan `<ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>` en `frontend/src/App.tsx`. Un padre que pegue la URL recibe 403.

**Sidebar:** ítem **"Competencias"** entre **Boletines** y **Análisis IA** (`frontend/src/components/layout/*.tsx`).

---

## 5. Tabs reutilizables — `components/competitions/tabs/`

Extraídos del `CompetitionDetailPage` en archivos separados para facilitar reuso y testing aislado. Cada tab recibe `raceEventId` y consume sus propios hooks de TanStack Query.

| Tab | Archivo | Carga | Consume |
|---|---|---|---|
| `InfoTab` | `tabs/InfoTab.tsx` | Inmediata | `useRaceEvent(id)` |
| `ResultsTab` | `tabs/ResultsTab.tsx` | Inmediata | Embebe `RaceAnalysisPage` filtrado por `race_event_id` (refactor mecánico, sin tocar la lógica). |
| `ConditionsTab` | `tabs/ConditionsTab.tsx` | Inmediata | `useRaceEventConditions(id)` + `EditConditionsDialog` (sheet lateral). |
| `AthletesTab` | `tabs/AthletesTab.tsx` | Lazy | `useAthleteRaceAnalysis` filtrado por evento. |
| `InsightsTab` | `tabs/InsightsTab.tsx` | Lazy | Embebe `ClubInsightsByRacePage` (refactor mecánico). |

**Selector URL-driven:** el tab activo vive en `?tab=...` (no estado local) para permitir compartir links profundos y respetar back/forward del navegador.

---

## 6. Decisiones de diseño relevantes

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| **Pre-crear válidas sin PDF** (`POST /race-events` admite cuerpo vacío de condiciones) | Solo crear vía ingesta del PDF (Fase 1.7) | El coach necesita planificar tapering, convocar atletas y asociar `calendar_events` semanas antes del evento. Bloquear esto hasta tener PDF rompe el flujo de planificación. |
| **DELETE admin only** | Coach puede borrar | El coach tiene `PATCH status=cancelled` para "ocultar" eventos; el DELETE es definitivo y rompe trazabilidad. Concentrar el privilegio en admin reduce el blast radius. |
| **No `PATCH /race-results/{id}` individual** | Endpoint dedicado para corregir un tiempo o posición | La re-ingesta del PDF es idempotente (`RaceIngestor.ingest_event` usa SHA256 + UNIQUE constraints). Corregir un dato en el PDF y re-subir es más auditable que parchar filas sueltas. **Out of scope** documentado. |
| **No campo "tipo A/B/C"** en `race_events` | Agregar columna `priority` enum | La periodización A/B/C vive en el `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx` y depende del calendario completo del año. Modelarlo aquí duplicaría la fuente de verdad. Cubierto a futuro con `is_championship: bool` para CD. |
| **ToggleGroup vs select** en filtros y form | `<Select>` clásico | Sedes Copa Valle son 7 fijas + estados son 4 enums — caben como chips ≥48px (touch-friendly en móvil, alineado con accesibilidad). |
| **Auto-altitud desde `VENUE_ALTITUDES`** | Pedir altitud manualmente | El coach no debería tener que conocer 1485 m vs 1024 m. Cuando elige sede del catálogo, el form rellena altitud; si edita después, el valor se respeta. |
| **`series_id=1` hardcoded en frontend** | GET `/api/race-analysis/race-series` | No hay endpoint expuesto aún. El club solo participa en Copa Valle. Documentado como TODO (ver §9). |
| **Tabs URL-driven** | Estado local + tabs no compartibles | Permite links profundos (`/competitions/12?tab=results`), respeta back/forward, simplifica QA E2E. |
| **Lazy load `AthletesTab` e `InsightsTab`** | Carga eager | Ambas hacen requests pesadas (`race_competitors` + club ranking). Lazy reduce TTI del detalle inicial. |

---

## 7. Integraciones cruzadas

### 7.1 Calendar

- Botón **"Asociar a calendario"** en `CompetitionDetailPage` aparece solo si `has_calendar_event=false`.
- Click → navega a `/calendar/events/new?race_event_id={id}`.
- `EventFormPage` lee `?race_event_id` y precarga el form con `prefillRaceEventId`.
- El backend ya soporta la FK `calendar_events.race_event_id` (Fase 1.5).
- Invalidaciones cruzadas en `useRaceEvents.ts`: al crear/editar `CalendarEvent` que apunte a un `race_event_id`, invalidar también `raceEvents.detail(id)` para refrescar el flag `has_calendar_event`.

### 7.2 Import wizard (reubicación CF1)

- **Antes (Fase 1.7):** `frontend/src/components/ai/ImportWizard.tsx` + helpers en `components/ai/`.
- **Ahora:** `frontend/src/components/competitions/import/{ImportWizard,RaceUploadZone,DiffTable}.tsx`.
- Codemod aplicado sobre 4 imports en consumidores; tests movidos con `__tests__` adjunto.
- La ruta `/competitions/import` permite crear válida nueva desde el wizard sin pre-crear el `race_event` (el commit lo crea).
- La ruta `/competitions/:id/import` monta el wizard con `race_event_id` precargado y oculta el paso 2 si el evento ya tiene metadata completa.

### 7.3 Inline create desde el wizard

El `EventForm` interno del wizard tiene un link **"Crear nueva válida"** que abre `/competitions/new?returnTo=/competitions/import`. Al guardar, vuelve al wizard con `?race_event_id={id}` recién creado.

---

## 8. Tests

| Capa | Cantidad | Ubicación | Cobertura |
|---|---|---|---|
| Backend funcional | **32** | `backend/tests/routers/test_race_events_crud.py` | Los 5 endpoints CRUD + matriz RBAC (admin/coach/parent) + casos 404/409/422 + guards de DELETE. |
| Backend regresión race | 802 | `backend/tests/` (módulo race completo) | 0 regresiones tras esta entrega (834 total race incluyendo los 32 nuevos). |
| Frontend unitario + integración | **69** | `frontend/src/{routes,components,hooks,api}/**/__tests__/` | List/Form/Detail/Import pages, FiltersBar, StatusBadges, tabs, hooks de TanStack Query con MSW. |
| Frontend a11y axe | **4** | (incluidos en los 69) | `CompetitionsListPage`, `CompetitionFormPage`, `CompetitionDetailPage`, `CompetitionImportPage` — 0 violaciones. |
| Frontend total post-entrega | 1682 | `frontend/src/**/__tests__/` | Sin regresiones. |

**Fixtures backend** (`backend/tests/routers/test_race_events_crud.py`): factory de `RaceSeries` + `RaceEvent` con datos sintéticos (sin nombres reales de atletas). Usa `AsyncSession` real sobre SQLite in-memory.

**MSW frontend:** `frontend/src/test/msw/raceEventsHandlers.ts` con handlers de los 5 endpoints + casos de error (409 unicidad, 409 dependencias, 422 sequence inválido).

---

## 9. Limitaciones conocidas y TODOs

| Tema | Estado | Issue futuro |
|---|---|---|
| `PATCH /api/race-results/{id}` | **Fuera de alcance.** El coach corrige el PDF en el origen y re-ingesta. | Si se vuelve necesario por corrección Federación, evaluar endpoint con auditoría `race_result_revision`. |
| `GET /api/race-analysis/race-series` | No expuesto. Frontend hardcodea `series_id=1`. | Cuando se incorpore otra serie (Cto. Nacional, Copa Pacífico), agregar endpoint y `<Select>` en `CompetitionFormPage`. |
| Tipificación A/B/C de periodización | No modelado. Solo `is_championship: bool` para CD. | Evaluar agregar enum `RacePriority` si el coach necesita filtrar por tipo en analítica. |
| Paginación del listado | No implementada (devuelve `total = len(items)`). | A escala 7 válidas × N temporadas no es necesaria; revisar si supera 100 eventos. |
| Endpoint `parse` recibe `race_event_id` precargado | El wizard aún reparseado completo en la ruta `/competitions/:id/import`. | Optimización: saltarse paso 2 del wizard si `race_event_id` está presente y la metadata coincide. |
| Auditoría CX1 (privacy review) | En curso al cierre de esta entrega. | Reflejar resultado en CLAUDE.md y este doc cuando esté el reporte final. |

---

## 10. Referencias

- `backend/app/routers/race_events.py` — implementación de los 5 endpoints.
- `backend/app/services/race_events.py` — lógica de negocio + guards.
- `backend/app/schemas/race_event.py` — DTOs Pydantic v2.
- `backend/tests/routers/test_race_events_crud.py` — 32 tests funcionales + RBAC.
- `backend/app/models/race_event.py` — modelo SQLAlchemy preexistente (Fase 1.7).
- `frontend/src/routes/competitions/` — 4 páginas.
- `frontend/src/components/competitions/` — componentes específicos del módulo.
- `frontend/src/api/raceEvents.ts` — wrappers axios.
- `frontend/src/hooks/race/useRaceEvents.ts` — query keys + invalidaciones.
- `frontend/src/types/raceEvents.types.ts` — tipos TS + `VENUE_ALTITUDES`.
- `docs/10-race-results/upload-design.md` — diseño técnico de la ingesta (Fase 1.7) + extensión condiciones (§14).
- `docs/10-race-results/runbook-ops.md` — operación CLI `scripts/ingest_race.py`.
