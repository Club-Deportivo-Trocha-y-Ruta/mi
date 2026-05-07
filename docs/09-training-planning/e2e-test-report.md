# E2E Test Report — Módulo Sesiones de Entrenamiento
**Fecha de ejecución:** 2026-05-06  
**Rama:** feature/training-module  
**PR:** https://github.com/Club-Deportivo-Trocha-y-Ruta/mi/pull/4  
**Ejecutado por:** quality-engineer agent

---

## Entorno

| Componente | Estado | Detalle |
|---|---|---|
| Docker Compose (backend + MySQL + mailhog) | UP (sano) | 3 servicios healthy |
| Backend (`http://localhost:8000`) | UP | FastAPI + aiomysql |
| Frontend (`http://localhost:5173`) | UP | React 19 + Vite |
| playwright-cli | v0.1.7 | Chromium |
| Migraciones Alembic | INCOMPLETAS al inicio | `training_sessions` / `session_attendance` / `monthly_reports` faltaban. Se aplicaron durante el test con `docker exec ... alembic upgrade head`. |

> **Incidencia pre-vuelo:** Las migraciones `6e189a7e1e51` y `b2c3d4e5f6a7` no se habían aplicado porque el contenedor fue creado antes del commit del módulo. Se aplicaron manualmente. En producción esto se haría automáticamente al desplegar.

---

## Tier 1 — Smoke API (backend curl)

### 1.1 Sesiones — Autenticación y Permisos

| Test | Endpoint | Rol | Esperado | Obtenido | Resultado |
|---|---|---|---|---|---|
| T1.1 | `POST /api/training-sessions` | coach | 201 | 500 (sesión creada en DB, error en respuesta) | **FAIL** |
| T1.2 | `POST /api/training-sessions` | parent | 403 | 403 | PASS |
| T1.3 | `POST /api/training-sessions` | anon | 401 | 401 | PASS |
| T1.4 | `GET /api/training-sessions` | coach | 200 | 200 | PASS |
| T1.5 | `GET /api/training-sessions` | parent | 200 | 200 | PASS |
| T1.6 | `GET /api/training-sessions/{id}` | coach | 200 | 200 | PASS |
| T1.7 | `GET /api/training-sessions/{id}` (no convocado) | parent | 403 | 403 | PASS |
| T1.8 | `GET /api/training-sessions/999999` | coach | 404 | 404 | PASS |

### 1.2 Validaciones de creación

| Test | Validación | Esperado | Obtenido | Resultado |
|---|---|---|---|---|
| T1.5 | `scheduled_date` pasada | 422 | 422 | PASS |
| T1.6 | `duration_min=5` (< 15) | 422 | 422 | PASS |
| T1.7 | `duration_min=999` (> 240) | 422 | 422 | PASS |
| T1.8 | `strava_url` inválida | 422 | 422 | PASS |
| T1.8b | `convocados_athlete_ids=[]` | 422 | 422 | PASS |

### 1.3 Ejecución de sesiones

| Test | Endpoint | Rol | Esperado | Obtenido | Resultado |
|---|---|---|---|---|---|
| T1.9 | `POST /{id}/execute` | coach | 200 + status=executed | 200 + executed | PASS |
| T1.10 | `POST /{id}/execute` (ya ejecutada) | coach | 409 | 409 | PASS |
| T1.11 | `POST /{id}/execute` | parent | 403 | 403 | PASS |

### 1.4 Asistencia

| Test | Endpoint | Rol | Esperado | Obtenido | Resultado |
|---|---|---|---|---|---|
| T1.12 | `PATCH /{id}/attendance/{athlete_id}` (presente + rúbrica) | coach | 200 | 200 | PASS |
| T1.13 | `PATCH /{id}/attendance/{athlete_id}` (ausente + razon) | coach | 200 o 404 | 404 (atleta no en sesión) | INFO |
| T1.14 | `PATCH` ausente SIN `excuse_reason` | coach | 422 | 422 | PASS |
| T1.15 | `PATCH` con `rpe_omni=11` | coach | 422 | 422 | PASS |
| T1.16 | `PATCH /{id}/attendance/{athlete_id}` | parent | 403 | 403 | PASS |
| T1.17 | `GET /athletes/{id}/attendance` | coach | 200 | 200 | PASS |
| T1.18 | `GET /athletes/{id}/attendance` (propio atleta) | parent | 200 | 200 | PASS |
| T1.19 | `GET /athletes/{id_ajeno}/attendance` | parent | 403 | 403 | PASS |

### 1.5 Reportes mensuales

| Test | Endpoint | Rol | Esperado | Obtenido | Resultado |
|---|---|---|---|---|---|
| T1.22 | `POST /clubs/{id}/monthly-reports` (mes cerrado: marzo) | coach | 201 | 201 | PASS |
| T1.23 | `POST /clubs/{id}/monthly-reports` (mes futuro) | coach | 422 | 422 | PASS |
| T1.24 | `POST /clubs/{id}/monthly-reports` (mes actual) | coach | 422 | 422 | PASS |
| T1.24b | `POST /clubs/{id}/monthly-reports` (abril, < día 28) | coach | 400 | 400 | PASS |
| T1.25 | Reporte duplicado mismo mes | coach | 409 | 409 | PASS |
| T1.26 | `GET /clubs/{id}/monthly-reports/{year}/{month}` | parent | 200 (sin `coach_observations`) | 200 (campo `null`) | PASS |
| T1.27 | `POST /clubs/{id}/monthly-reports` | parent | 403 | 403 | PASS |
| T1.28 | `POST /clubs/{id}/monthly-reports/{y}/{m}/send` | parent | 403 | 403 | PASS |
| T1.29 | `POST /clubs/{id}/monthly-reports/{y}/{m}/send` | coach | 200 | 200 | PASS |
| T1.30 | `GET /parents/training/monthly-summary/{y}/{m}` | parent | 200 | 200 | PASS |
| T1.31 | `GET /parents/training/monthly-summary/{y}/{m}?athlete_id={ajeno}` | parent | 403 | 403 | PASS |

### 1.6 Upload de archivos

| Test | Escenario | Esperado | Obtenido | Resultado |
|---|---|---|---|---|
| T1.32 | Upload `.txt` (content-type prohibido) | 400 | 400 | PASS |
| T1.33 | Upload por parent | 403 | 403 (fallback: 000 curl issue) | PASS |
| T1.36 | Upload archivo >5 MB (6 MB) | 400/413 | 400 | PASS |
| T1.37 | Upload GPX con XXE | 400/422 | 500 (**defusedxml no instalado**) | **FAIL** |
| T1.38 | Upload GPX válido | 200 | 500 (**defusedxml no instalado**) | **FAIL** |

---

## Tier 2 — Frontend E2E (playwright-cli)

### Flow A — Coach happy path

| Paso | Descripción | Resultado | Snapshot |
|---|---|---|---|
| A1 | Login como coach → redirect a /dashboard | PASS | (login auto) |
| A2 | Navegar a `/training/sessions` — lista visible con tabla | PASS | `flow-a-02-sessions-list.yml` |
| A3 | Clic "+ Nueva sesión" → form en `/training/sessions/new` | PASS | — |
| A4 | Llenar form (U15, fecha futura, lugar, foco, descripción, 1 atleta) | PASS | `flow-a-03-session-form-filled.yml` |
| A5 | Submit → **500 del backend** (bug lazy loading) | **FAIL** — sesión creada en DB pero respuesta 500. UI no redirige ni muestra error. | — |
| A6 | Navegar a lista — sesión aparece en estado Planificada | PASS (sesión sí aparece) | — |
| A7 | Clic "Ver" → detalle. Clic "Marcar ejecutada" → status cambia a Ejecutada | PASS | `flow-a-04-session-executed.yml` |
| A8 | Tabla de asistencia muestra **error** "No se pudo cargar la lista de asistencia" | **FAIL** — frontend hace GET a endpoint inexistente (`/api/training-sessions/{id}/attendance`) | — |
| A9 | Logout | PASS | — |

### Flow B — Parent privacy check

| Paso | Descripción | Resultado | Snapshot |
|---|---|---|---|
| B1 | Login como parent → redirect a `/my-athletes` | PASS | — |
| B2 | Navegar a `/parents/training/sessions` → lista vacía (sin sesiones del propio atleta) | PASS | `flow-b-01-parent-sessions.yml` |
| B3 | Intentar navegar a `/training/sessions` (ruta de coach) → redirect a `/my-athletes` | PASS | `flow-b-02-parent-redirect.yml` |
| B4 | API: parent POST monthly-report → 403 | PASS | — |

### Flow C — Monthly report (coach)

| Paso | Descripción | Resultado |
|---|---|---|
| C1 | `POST /api/clubs/2/monthly-reports` (marzo 2026) → 201 | PASS |
| C2 | `ai_summary` presente y no vacío (237 caracteres approx) | PASS |
| C3 | AI usa proveedor `fake` (AI_PROVIDER=fake en docker-compose) | INFO — AI funcionó con mock |
| C4 | Re-send report → 200 | PASS |
| C5 | Reporte duplicado → 409 | PASS |

### Flow D — Privacy probes (API)

| Probe | Endpoint | Rol | Esperado | Obtenido | Resultado |
|---|---|---|---|---|---|
| D1 | `GET /api/training-sessions?club_id=99` | parent | 200 vacío (fuerza atletas propios) | 200 vacío | PASS |
| D2 | `GET /api/training-sessions/{id}` (sin atleta propio) | parent | 403 | 403 | PASS |
| D3 | `PATCH /api/training-sessions/{id}/attendance/{ajeno}` | parent | 403 | 403 | PASS |
| D4 | `GET /api/clubs/{id}/monthly-reports` | parent | 200 (design permite) | 200 | PASS |
| D5 | `GET /api/parents/training/monthly-summary/…?athlete_id={ajeno}` | parent | 403 | 403 | PASS |

---

## Tier 3 — Resiliencia

| Test | Escenario | Resultado |
|---|---|---|
| T3.1 | POST con fecha pasada → 422 | PASS |
| T3.2 | UI ante 500 del servidor | **FAIL** — No hay error toast/feedback visible al usuario |
| T3.3 | Parent PATCH attendance ajena → 403 | PASS |
| T3.4 | Parent POST execute → 403 | PASS |
| T3.5 | Rúbrica en ausente → 422 | PASS |
| T3.6 | XXE en GPX upload | **FAIL** — 500 por `defusedxml` no instalado (módulo faltante) |

---

## Tier 4 — A11y

**Vitest frontend:** 717 tests, 58 archivos — todos PASS.  
No existen tests específicos de axe-core en el proyecto (el flag `-t a11y` no encontró matches). Los 717 tests existentes cubren comportamiento funcional y ya incluyen tests de componentes de training (SessionFormPage, SessionDetailPage, AttendanceTable, ParentSessionCard, ReadOnlyAttendanceRow, etc.).

---

## Backend pytest

Corrido dentro del contenedor Docker (excluyendo `test_document_generator.py` que falla por fixture `mocker` no instalado):

- **35 FAIL** — todos relacionados con el módulo de training sessions
  - **Causa principal 1:** `MissingGreenlet` — bug de lazy loading en `create_session()` (el router llama `session.attendances` sin `selectinload` después de commit)
  - **Causa principal 2:** `ModuleNotFoundError: No module named 'defusedxml'` — dependencia declarada en código pero ausente en `requirements.txt` y no instalada en el contenedor
- **624 PASS** — resto del proyecto en buen estado
- **8 ERROR** — tests de email client con fixtures faltantes (preexistente, no relacionado con este módulo)

---

## Bugs encontrados

### CRITICAL

Ninguno que represente fuga de datos de usuarios. Privacidad estructural evaluada como APROBADA.

### HIGH

| ID | Severidad | Componente | Descripción | Impacto |
|---|---|---|---|---|
| BUG-001 | **HIGH** | Backend | `POST /api/training-sessions` retorna 500 aunque la sesión SÍ se crea en DB. El error ocurre en `_session_to_read()` al acceder `session.attendances` mediante lazy loading en contexto async post-commit. | Pérdida de confianza del usuario (error 500 en operación exitosa), frontend no puede redirigir al detalle, 35 tests del router fallan. |
| BUG-002 | **HIGH** | Backend | `defusedxml` y `gpxpy` están referenciados en `route_files.py` pero **no están en `requirements.txt`** ni instalados en el contenedor. Todo upload GPX retorna 500 y el XXE check no funciona. | Seguridad: ficheros GPX con XXE no son validados. Funcionalidad de recorridos completamente bloqueada. |
| BUG-003 | **HIGH** | Frontend | La `AttendanceTable` en el detalle de sesión hace `GET /api/training-sessions/{id}/attendance` que no existe (405 Method Not Allowed). El backend incluye la asistencia en el detalle de sesión como `attendances`, pero el schema de respuesta no expone ese campo. | Tabla de asistencia siempre muestra error. Coach no puede registrar asistencia desde la UI. |

### MEDIUM

| ID | Severidad | Componente | Descripción | Impacto |
|---|---|---|---|---|
| BUG-004 | **MEDIUM** | Frontend | Al fallar `POST /api/training-sessions` con 500, la UI no muestra ningún error toast ni feedback al usuario. El formulario permanece tal cual sin indicar que ocurrió un problema. | UX confuso — usuario no sabe si la sesión fue creada o no. |
| BUG-005 | **MEDIUM** | Backend | El schema `TrainingSessionRead` no expone el campo `attendances` (lista de `SessionAttendance`). Solo expone `attendance_summary` (resumen numérico). El frontend necesita los datos de cada atleta para renderizar la tabla de edición. | Contrato frontend-backend desincronizado. Requiere agregar `attendances: list[AttendanceRead]` al schema o crear un endpoint `GET /{id}/attendance`. |

### LOW

| ID | Severidad | Componente | Descripción |
|---|---|---|---|
| BUG-006 | **LOW** | DB | La fuente de datos `static/uploads/routes/` se monta localmente pero el docker-compose no define un volumen persistente para esa ruta. Los archivos GPX subidos se perderían al reiniciar el contenedor. |
| BUG-007 | **LOW** | Backend | El test `test_document_generator.py` usa la fixture `mocker` (de `pytest-mock`) que no está en `requirements-dev.txt`. Bloqueó el suite antes de aislar el archivo. |

---

## Veredicto de privacidad: **APROBADO**

Todos los controles de privacidad a nivel API funcionan correctamente:
- Parent no puede ver sesiones de atletas ajenos (403)
- Parent no puede modificar asistencia (403)  
- Parent no puede crear/ejecutar sesiones (403)
- Parent no puede crear reportes (403)
- `coach_observations` es omitido en respuestas para parent (campo `null`)
- Parent solo puede acceder al resumen de SUS atletas
- Datos de asistencia individual (rúbrica, RPE) NO aparecen en reportes agregados del club

---

## Recomendación: **BLOQUEAR PR**

El PR no debe mergearse en su estado actual. Los bugs HIGH deben resolverse primero:

1. **BUG-001:** Agregar `selectinload(TrainingSession.attendances)` en `create_session()` después del commit, o recargar la sesión usando `get_session()` antes de retornar.
2. **BUG-002:** Agregar `defusedxml` y `gpxpy` a `requirements.txt` y reconstruir la imagen.
3. **BUG-003:** Decidir entre: (a) agregar `attendances: list[AttendanceRead]` al schema `TrainingSessionRead` y asegurar que `get_session()` cargue la relación (ya lo hace con `selectinload`), o (b) crear un endpoint `GET /training-sessions/{id}/attendance`.

Una vez resueltos estos tres bugs, todos los 35 tests de router y servicio deberían pasar y la experiencia de usuario quedaría completa.

---

## Rutas de snapshots

- `docs/09-training-planning/snapshots/flow-a-02-sessions-list.yml`
- `docs/09-training-planning/snapshots/flow-a-03-session-form-filled.yml`
- `docs/09-training-planning/snapshots/flow-a-04-session-executed.yml`
- `docs/09-training-planning/snapshots/flow-b-01-parent-sessions.yml`
- `docs/09-training-planning/snapshots/flow-b-02-parent-redirect.yml`
