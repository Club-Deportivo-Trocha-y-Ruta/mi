# Workflow — Implementación Módulo Sesiones de Entrenamiento

**Fecha:** 2026-05-06
**Diseño base:** [`design.md`](./design.md)
**Estado:** Pendiente kickoff

---

## Mapa rápido

```
PASO 1   Modelo datos + migración Alembic
PASO 2   Schemas Pydantic + permisos
PASO 3   Service layer (TrainingSessionService, AttendanceService)
PASO 4   Routers + endpoints CRUD sesión
PASO 5   Routers asistencia + endpoint upload .gpx
PASO 6   Tests backend (unit + integration)
PASO 7   Notificación padres al planificar (template + flow)
PASO 8   IA monthly report use case
PASO 9   Endpoint reporte mensual + envío email
PASO 10  Frontend coach: lista + form sesión
PASO 11  Frontend coach: detalle + asistencia + rúbrica
PASO 12  Frontend coach: reporte mensual UI
PASO 13  Frontend parent: lectura sesiones + reporte
PASO 14  Tests frontend (vitest + RTL)
PASO 15  E2E + deploy + docs
```

---

## Principios transversales (NO violar)

Tomados de `CLAUDE.md` y marco teórico:

1. Idioma respuestas API → mensajes de error en español.
2. Privacidad menores: NUNCA exponer feedback individual en reporte agregado club.
3. Reusar `services/notification/` y `services/ai/` (no duplicar plumbing).
4. RBAC con tests exhaustivos por endpoint.
5. Convention git: Conventional Commits (`feat(training):`, `fix(training):`, etc).
6. No introducir abstracciones de más. Tres líneas similares > prematura abstracción.
7. Diseño backend antes que frontend. Una capa a la vez.

---

## PASO 1 — Modelo de datos + migración

**Objetivo:** Crear tablas `training_sessions`, `session_attendance`, `monthly_reports` con enums.

### Tareas

1.1. Crear `backend/app/models/training_session.py`:
- `class AgeGroup(str, Enum)`: `U12`, `U15`
- `class SessionStatus(str, Enum)`: `PLANNED`, `EXECUTED`, `CANCELLED`
- `class AttendanceStatus(str, Enum)`: `PRESENTE`, `AUSENTE`, `JUSTIFICADO`, `TARDE`, `LESIONADO`
- `class TrainingSession(Base)` — campos según `design.md §3.1`
- `class SessionAttendance(Base)` — relación N:N con metadata
- `class MonthlyReport(Base)` — agregado club/mes
- Usar `values_callable` para enums (consistente con `MaturationStatus`).
- Relaciones SQLAlchemy con `back_populates` (no `backref`).

1.2. Registrar modelos en `backend/app/models/__init__.py`.

1.3. Generar migración:
```bash
cd backend && alembic revision --autogenerate -m "agrega tablas training_session, session_attendance, monthly_report"
```

1.4. Revisar migración a mano:
- Índices: `idx_training_session_club_date`, `idx_training_session_club_age_date`, `uq_session_attendance_session_athlete`, `uq_monthly_report_club_year_month`
- Constraint check para `rpe_omni 0-10`, `rubric_* 1-5`, `duration_min 15-240`.

1.5. Aplicar local:
```bash
alembic upgrade head
```

### Criterio aceptación
- [ ] Tres tablas creadas con FK correctas.
- [ ] Índices y unique constraints presentes.
- [ ] Tests modelo CRUD pasan (PASO 6 los cubre).

---

## PASO 2 — Schemas Pydantic + permisos

**Objetivo:** Capa contrato API + extensión RBAC.

### Tareas

2.1. Crear `backend/app/schemas/training_session.py`:
- `TrainingSessionCreate`, `TrainingSessionUpdate`, `TrainingSessionRead`
- `AttendanceCreate` (bulk convocatoria), `AttendanceUpdate`, `AttendanceRead`
- `MonthlyReportCreate`, `MonthlyReportRead`
- Validators: `_validate_consistency` en `AttendanceUpdate` (rúbrica solo si presente/tarde, razón si ausente).
- `route_file_path` solo lectura — upload en endpoint dedicado.

2.2. Extender `backend/app/services/permissions.py`:
- `can_view_session(user, session) -> bool`
- `can_edit_session(user, session) -> bool`
- `can_view_athlete_feedback(user, athlete) -> bool`
- `can_view_monthly_report(user, club, individual: bool) -> bool`
- Helper `parent_athlete_ids(user) -> list[int]` (cached).

### Criterio aceptación
- [ ] Schemas serializan/deserializan correctamente.
- [ ] Validators rechazan combinaciones inválidas.
- [ ] Tests `test_permissions_training.py` cubren matriz §6 del design.

---

## PASO 3 — Service layer

**Objetivo:** Lógica de negocio fuera de routers (mismo patrón `services/phv.py`).

### Tareas

3.1. `backend/app/services/training/__init__.py` (paquete nuevo).

3.2. `backend/app/services/training/sessions.py`:
- `create_session(db, payload, coach_id) -> TrainingSession` — crea sesión + filas asistencia para convocados.
- `update_session(...)`
- `execute_session(db, session_id)` — set `status=executed`, `executed_at=now`.
- `cancel_session(...)` — soft delete.
- `list_sessions(db, filters: SessionFilters)` — query con joins eficientes.

3.3. `backend/app/services/training/attendance.py`:
- `bulk_upsert_convocatoria(db, session_id, athlete_ids)`
- `update_attendance(db, session_id, athlete_id, payload)` — valida coach mismo club.
- `athlete_attendance_history(db, athlete_id, from_, to_)`.

3.4. `backend/app/services/training/metrics.py`:
- `compute_monthly_metrics(db, club_id, year, month) -> MonthlyMetrics` (dataclass):
  - Total sesiones planificadas / ejecutadas / canceladas
  - Por atleta: % asistencia, # sesiones presente
  - Focos técnicos cubiertos (lista única)
  - Promedio RPE / rúbrica (agregado, sin individuales)
  - Sesiones por grupo edad

3.5. `backend/app/services/training/route_files.py`:
- `save_route_file(file: UploadFile, session_id) -> str` — valida extensión, tamaño, parsea con `gpxpy`+`defusedxml` para detectar XXE, devuelve path relativo.
- Almacenamiento `static/uploads/routes/{session_id}/{uuid}.gpx`.

### Criterio aceptación
- [ ] Services no tocan FastAPI directamente (testeable sin TestClient).
- [ ] Inyección de DB via parámetro, no global.

---

## PASO 4 — Routers CRUD sesión

**Objetivo:** Endpoints REST `/training-sessions/*`.

### Tareas

4.1. Crear `backend/app/routers/training_sessions.py` con los endpoints §4.1 del design.

4.2. Registrar router en `backend/app/main.py`.

4.3. Cada endpoint:
- Depende de `get_db`, `get_current_user`.
- Aplica permiso correspondiente (PASO 2).
- Mensajes de error en español.
- Respuestas usan `*Read` schemas.

4.4. Manejo de errores:
- 403 si permisos no.
- 404 si no existe.
- 409 si conflicto (ej. ejecutar ya ejecutada).
- 422 si validation Pydantic.

### Criterio aceptación
- [ ] Swagger `/docs` muestra los endpoints con schemas.
- [ ] Smoke test manual con `Admin2026!` token.

---

## PASO 5 — Routers asistencia + upload `.gpx`

**Objetivo:** Endpoints §4.2 del design + multipart upload.

### Tareas

5.1. En `backend/app/routers/training_sessions.py` agregar:
- `PUT /training-sessions/{id}/attendance` (bulk)
- `PATCH /training-sessions/{id}/attendance/{athlete_id}`
- `POST /training-sessions/{id}/route-file` (multipart)

5.2. En `backend/app/routers/athletes.py` agregar:
- `GET /athletes/{id}/attendance` (delegado a service).

5.3. Validación archivo:
- `Content-Type` ∈ `application/gpx+xml`, `application/octet-stream`, `application/vnd.garmin.fit`.
- Extensión `.gpx`, `.fit`.
- Tamaño máx 5 MB (usar `Settings.MAX_UPLOAD_SIZE_BYTES`).
- Si `.fit` en MVP: guardar tal cual, **no parsear** (parser fase 2).

### Criterio aceptación
- [ ] Upload correcto guarda archivo y actualiza `route_file_path`.
- [ ] Upload de archivo malicioso (`<!DOCTYPE [...XXE...]>`) rechazado.
- [ ] Permisos validados (parent NO puede subir).

---

## PASO 6 — Tests backend

**Objetivo:** Cobertura ≥80% en services + routers.

### Tareas

6.1. `backend/tests/test_training_session_models.py`:
- CRUD básico, FK, constraints check.
- Soft delete cascade comportamiento.

6.2. `backend/tests/test_training_session_service.py`:
- `create_session` crea filas asistencia.
- `execute_session` rechaza si ya executed.
- `compute_monthly_metrics` con dataset fixture.

6.3. `backend/tests/test_training_session_router.py`:
- Cada endpoint × cada rol (admin, coach mismo club, coach otro club, parent, anónimo).
- 200 / 403 / 404 esperados.

6.4. `backend/tests/test_training_session_privacy.py`:
- **Crítico:** parent A NO ve sesiones de atleta B (otro padre).
- parent NO ve feedback individual de atletas no suyos.
- reporte mensual agregado NO incluye nombres ni feedback individual.

6.5. `backend/tests/test_attendance_validation.py`:
- Rúbrica + status=ausente → 422.
- Rúbrica + status=presente sin razón → 200.
- Status=justificado sin razón → 422.

### Criterio aceptación
- [ ] `pytest backend/tests -k training` todo verde.
- [ ] Cobertura `services/training/` ≥80%.

---

## PASO 7 — Notificación padres al planificar (Q7)

**Objetivo:** Cuando coach crea sesión `planned`, padres de atletas convocados reciben email.

### Tareas

7.1. Plantilla nueva:
- `backend/app/templates/notifications/training_session_invite.html` (HTML)
- `backend/app/templates/notifications/training_session_invite.txt` (fallback)
- Variables: `parent_name`, `athlete_name`, `session_date`, `session_time`, `location`, `technical_focus`, `duration_min`, `coach_name`.

7.2. Registrar en `template_registry.py` con kind `training_session_invite`.

7.3. En `services/training/sessions.py::create_session` después de commit:
- Para cada atleta convocado → buscar padres (`parent_athlete`).
- Para cada padre → `notification_service.send(NotificationRequest(...))` async via dispatcher.
- Log estructurado, NO PII en logs (CLAUDE.md `NOTIFICATION_LOG_BODIES=false`).

7.4. Throttle:
- Helper `should_throttle(parent_id, athlete_id, kind)` consultando `notification_log` (si existe). Skip si email igual enviado <60min.

7.5. Tests:
- Mock `NotificationService` y verifica llamadas.
- Verifica que coach planifica sesión cancelada → NO email.
- Verifica que padre con `notification_opt_out=true` NO recibe.

### Criterio aceptación
- [ ] Email llega con render correcto en cliente real (test manual con padre@trochyruta.com en local).
- [ ] No envía si `APP_ENV=production` y `NOTIFICATION_SEND_EMAILS=false`.

---

## PASO 8 — IA monthly report use case

**Objetivo:** Use case `monthly_report` siguiendo patrón `phv_explainer.py`.

### Tareas

8.1. `backend/app/services/ai/use_cases/monthly_report.py`:
- `class MonthlyReportContext(BaseModel)` — agregados `MonthlyMetrics` + meta (club_name, period, coach_name).
- `class MonthlyReportUseCase(BaseUseCase)`:
  - `build_context(...)` (privacy-safe: sin nombres atletas, solo iniciales o ID).
  - `render_prompt(context)` con `monthly_report.j2`.
  - `parse_output(raw)` valida estructura.
  - Hereda guardrails de `BaseUseCase`.

8.2. `backend/app/services/ai/prompts/monthly_report.j2`:
- Prologue con `system_principles.md`.
- Instrucciones explícitas:
  - "Genera resumen agregado, no juicios individuales."
  - "Máximo 500 palabras, 3 párrafos."
  - "Sin recomendaciones médicas ni nutricionales."
  - "No menciones nombres específicos."
- Datos input estructurados.

8.3. Extender `services/ai/guardrails.py`:
- Validar output sin nombres ∈ lista convocados (regex protección).
- Validar longitud y secciones.

8.4. Tests:
- `backend/tests/test_ai_monthly_report.py`:
  - Snapshot de prompt con datos de ejemplo.
  - Mock provider con respuesta dummy.
  - Guardrails rechazan output con nombre.

### Criterio aceptación
- [ ] Use case integrado en `factory.py`.
- [ ] Prompt no contiene PII.

---

## PASO 9 — Endpoint reporte mensual + envío email

**Objetivo:** Endpoints §4.3 + envío al admin del club.

### Tareas

9.1. `backend/app/routers/monthly_reports.py`:
- `POST /clubs/{id}/monthly-reports` — body `{year, month}`.
  - Valida year/month no futuro y mes ya cerrado.
  - 409 si ya existe (reusar via `force_regenerate=true` opcional).
  - Service: `compute_monthly_metrics` → `MonthlyReportUseCase.run` → persistir.
- `GET /clubs/{id}/monthly-reports` — listar.
- `GET /clubs/{id}/monthly-reports/{year}/{month}` — detalle.
- `POST /clubs/{id}/monthly-reports/{report_id}/send` — re-enviar email.

9.2. Plantilla email + PDF:
- `backend/app/templates/notifications/monthly_report.html`.
- Reusar `DocumentGenerator` (ya genera PDF) para adjunto.
- Email incluye: narrativa IA + tabla métricas (desde `metrics_snapshot`).

9.3. Variante padre:
- `GET /parents/training/monthly-summary/{year}/{month}` — devuelve solo sesiones de SUS atletas (no agregado del club).

9.4. Tests:
- `test_monthly_report_router.py` — happy path + errores.
- `test_monthly_report_privacy.py` — padre NO ve agregado club, sí ve resumen propio atleta.

### Criterio aceptación
- [ ] Reporte generado mes pasado con datos seed visible en `/docs` Swagger.
- [ ] Email + PDF llegan a admin@ del club.

---

## PASO 10 — Frontend coach: lista + form sesión

**Objetivo:** UI coach para CRUD sesiones (rutas `/training/sessions`, `/new`, `/:id/edit`).

### Tareas

10.1. API client:
- `frontend/src/api/trainingSessions.ts` — funciones tipadas + TanStack Query hooks (`useSessions`, `useCreateSession`, etc).

10.2. Tipos:
- `frontend/src/types/trainingSession.types.ts` — espejo de schemas Pydantic.

10.3. Schemas Zod:
- `frontend/src/schemas/trainingSession.schema.ts` — para RHF.

10.4. Páginas:
- `frontend/src/routes/training/SessionsListPage.tsx` — tabla con filtros (mes, age_group, status).
- `frontend/src/routes/training/SessionFormPage.tsx` — RHF + Zod + selector multi-atleta convocados (filtrado por age_group del club).

10.5. Componentes:
- `components/training/SessionsTable.tsx`
- `components/training/AthletesMultiSelect.tsx` (filtrado por age_group)
- `components/training/SessionStatusBadge.tsx`

10.6. Estado:
- TanStack Query cache invalidate en mutations.
- Zustand para filtros UI persistentes en sesión navegador.

### Criterio aceptación
- [ ] Coach crea sesión planificada en <30s.
- [ ] Lista carga <500ms con 100 sesiones.
- [ ] Atletas filtrados correctamente por age_group.

---

## PASO 11 — Frontend coach: detalle + asistencia + rúbrica

**Objetivo:** UI ejecución sesión (ruta `/training/sessions/:id`).

### Tareas

11.1. `routes/training/SessionDetailPage.tsx`:
- Header: fecha, lugar, foco técnico, duración, status, botón "Marcar ejecutada".
- Sección recorrido: render `route_text`, link Strava, viewer `.gpx` (leaflet).
- Tabla asistencia editable (un row por convocado).

11.2. `components/training/AttendanceTable.tsx`:
- Columnas: atleta | status select | razón (si no presente) | RPE 0-10 | rúbrica esfuerzo/actitud/técnica | comentario.
- Edición inline, autosave debounced 500ms.
- Atajos teclado: `P/A/J/T/L` para status rápido.

11.3. `components/training/RubricSliders.tsx`:
- 3 sliders 1-5 con etiquetas (1=Muy bajo, 5=Excelente).
- RPE OMNI 0-10 con visual emoji o caras.
- Textarea 500 chars con contador.

11.4. `components/training/RouteViewer.tsx`:
- Carga `.gpx` con `leaflet-gpx`. Fallback "no disponible" si solo `.fit`.

11.5. Tests vitest + RTL:
- `AttendanceTable` permite editar y autosave llama API.
- `RubricSliders` rechaza valores fuera rango.
- `SessionDetailPage` muestra "Marcar ejecutada" solo si planned.

### Criterio aceptación
- [ ] Coach completa asistencia 10 atletas en <2 min.
- [ ] Sin pérdida de datos al cambiar de fila (autosave).

---

## PASO 12 — Frontend coach: reporte mensual UI

**Objetivo:** Generar y visualizar reporte mensual (ruta `/training/reports`).

### Tareas

12.1. `routes/training/ReportsListPage.tsx`:
- Lista reportes existentes por mes.
- Botón "Generar reporte" con selector mes/año.

12.2. `routes/training/ReportDetailPage.tsx`:
- Sección "Resumen IA" (narrativa).
- Tabla métricas: # sesiones, % asistencia por atleta, focos cubiertos.
- Botón "Re-enviar al club".
- Banner advertencia: "Resumen generado por IA — revisar antes de enviar."

12.3. Componente `MonthlyMetricsTable.tsx` reusable.

### Criterio aceptación
- [ ] Coach genera reporte mensual en <10s (mock LLM).
- [ ] Edición narrativa NO permitida (read-only desde IA, override por coach via comentario adicional fase 2).

---

## PASO 13 — Frontend parent: lectura

**Objetivo:** Padres ven sesiones de su atleta.

### Tareas

13.1. `routes/parents/training/SessionsPage.tsx`:
- Lista sesiones donde su atleta fue convocado.
- Sin botones edición.

13.2. `routes/parents/training/SessionDetailPage.tsx`:
- Descripción general visible.
- Asistencia: solo fila de SU atleta (status, rúbrica, feedback).
- NO ve otros atletas.

13.3. `routes/parents/training/MonthlyOverviewPage.tsx`:
- Resumen mensual personalizado: % asistencia atleta, # sesiones, focos cubiertos.
- NO ve narrativa agregada del club.

13.4. Componente reutilizable `ParentSessionCard.tsx`.

### Criterio aceptación
- [ ] Padre A nunca ve datos de atleta B en network tab.
- [ ] Tests RTL verifican render filtrado correcto.

---

## PASO 14 — Tests frontend

**Objetivo:** Cobertura vitest ≥75% en componentes y rutas nuevas.

### Tareas

14.1. Component tests por cada componente nuevo (`*.test.tsx`).

14.2. Hook tests para queries TanStack (`useSessions`, `useAttendance`, `useMonthlyReport`).

14.3. Integration tests rutas con MSW mocks.

14.4. A11y tests:
- `AttendanceTable` accesible vía teclado (axe-core).
- Labels y aria correctos.

### Criterio aceptación
- [ ] `pnpm test` verde.
- [ ] Coverage report supera 75%.

---

## PASO 15 — E2E + deploy + docs

**Objetivo:** Verificar flujo completo y deploy producción.

### Tareas

15.1. E2E manual checklist (`docs/09-training-planning/qa.md`):
- Coach crea sesión → padre recibe email → padre abre portal → ve detalle → coach ejecuta → coach pone rúbrica → padre ve rúbrica de su atleta → coach genera reporte mensual → admin recibe PDF → padre ve resumen mes propio.

15.2. Deploy:
- PR con todos los cambios → review → merge a `main`.
- Render auto-deploy.
- Verificar `alembic upgrade head` corre OK en startup.
- Smoke test producción `https://mi-2yzi.onrender.com/docs`.

15.3. Actualizar docs:
- `docs/README.md` agregar entrada `09 — training-planning`.
- `CLAUDE.md` actualizar tabla "Estado de implementación Fase 1" con módulo training.
- Memoria proyecto: `~/.claude/projects/.../memory/training_module_done.md` con resumen de decisiones.

### Criterio aceptación
- [ ] Producción funcional con seed coach + atleta + padre dummy.
- [ ] Tabla docs actualizada.
- [ ] Memoria proyecto guardada.

---

## Comandos útiles durante desarrollo

```bash
# Backend
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload
cd backend && pytest -k training -v
cd backend && alembic revision --autogenerate -m "agrega <X>"
cd backend && alembic upgrade head

# Frontend
cd frontend && pnpm dev
cd frontend && pnpm test
cd frontend && pnpm test --coverage

# Stack completo
docker compose up

# Lint pre-commit
cd backend && ruff check . && black --check .
cd frontend && pnpm lint
```

---

## Métricas de éxito del módulo

Al cerrar PASO 15, deberíamos ver:

- **Adopción coach:** ≥1 sesión registrada por semana del entrenador real.
- **Asistencia padres:** ≥40% de padres abren al menos un email invitación.
- **Privacidad:** 0 incidentes de fuga datos cross-atleta (verificable con logs).
- **Performance:** Lista mes <300ms, generación reporte IA <15s.
- **Testing:** Backend ≥80% cobertura services, frontend ≥75% rutas.

---

## Decisiones diferidas (sprint 2 del módulo)

Anotar para no olvidar:
- `.fit` → `.gpx` server-side conversion.
- Sesiones recurrentes (cron coach: "todos los martes 5pm").
- Plantillas reutilizables ("Sesión técnica intervalos cortos").
- Push notifications móvil (PWA notif).
- Integración Intervals.icu para datos GPS de atletas con dispositivo propio.
- Upload fotos/videos sesión.
- Vista calendario (mes/semana) tipo agenda.
- Padre puede confirmar asistencia previa ("mi hijo NO podrá ir el martes").
- Estadísticas comparativas (atleta vs promedio club, agregado, anonimizado).

---

## Referencias

- Diseño: [`design.md`](./design.md)
- Marco teórico: [`../01-marco-teorico.md`](../01-marco-teorico.md) §2, §5, §6
- Patrón AI use case: `backend/app/services/ai/use_cases/phv_explainer.py`
- Patrón notification: `backend/app/services/notification/service.py`
- RBAC: `backend/app/services/permissions.py`
- Strava research: ver brainstorm previo (Nov 2024 ToS bloqueo coach reading athletes).
