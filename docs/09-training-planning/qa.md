# QA E2E — Módulo Sesiones de Entrenamiento

**Fecha:** 2026-05-06
**Módulo:** Sesiones de Entrenamiento (Fase 1.5)
**Ambiente objetivo:** Local con Docker Compose / Producción (https://mi-2yzi.onrender.com)

---

## Pre-requisitos

- [ ] `docker compose up` ejecutado y estable (todos los servicios healthy)
- [ ] Seed data aplicado (`APP_ENV=development` → `python -m scripts.seed`)
- [ ] Variables de entorno `.env` correctas (EMAIL_PROVIDER, RESEND_API_KEY, etc.)
- [ ] Al menos un atleta asignado al club con edad en rango u12 (10-12) o u15 (13-15)
- [ ] Padre vinculado al atleta (`parent_athlete` table) con email válido
- [ ] Cuenta admin: `admin@trochyruta.com` / `Admin2026!`
- [ ] Cuenta coach: `entrenador@trochyruta.com` / `Coach2026!`
- [ ] Cuenta parent: `padre@trochyruta.com` / `Parent2026!`
- [ ] Endpoint `/api/v1/docs` accesible y mostrando nuevos tags `training-sessions` y `monthly-reports`

---

## 1. Flujo Coach — Planificar sesión

### 1.1 Crear sesión planificada
- [ ] Login como coach → token JWT válido
- [ ] `POST /api/v1/training-sessions` con fecha futura, age_group=u15, convocados_athlete_ids=[id_atleta]
- [ ] Respuesta 201 con id de sesión y status=planned
- [ ] Verificar en DB: fila en `training_sessions` con status='planned'
- [ ] Verificar en DB: fila en `session_attendance` con athlete_id y status vacío (convocado)

### 1.2 Notificación a padre
- [ ] En logs del servidor: mensaje "Notificación enviada a padre X para sesión Y" (sin PII en el log body)
- [ ] Si `NOTIFICATION_SEND_EMAILS=true`: email llegó a la casilla del padre con asunto conteniendo fecha y lugar
- [ ] Si `NOTIFICATION_SEND_EMAILS=false`: solo log estructurado (sin error)
- [ ] Email contiene: fecha/hora, lugar, foco técnico, nombre del coach, sin datos de otros atletas

### 1.3 Validaciones de creación
- [ ] `POST` con `scheduled_date` pasada → 422 con mensaje en español
- [ ] `POST` sin `convocados_athlete_ids` (lista vacía) → 422
- [ ] `POST` con `strava_url` inválida (no regex `strava.com/activities/\d+`) → 422
- [ ] `POST` con `duration_min=5` (< 15) → 422
- [ ] `POST` con `duration_min=300` (> 240) → 422

---

## 2. Flujo Coach — Ejecutar sesión y registrar asistencia

### 2.1 Marcar sesión como ejecutada
- [ ] `POST /api/v1/training-sessions/{id}/execute` → 200, status=executed, executed_at poblado
- [ ] Intentar ejecutar sesión ya ejecutada → 409
- [ ] Intentar ejecutar sesión cancelada → 409

### 2.2 Registrar asistencia con rúbrica + RPE
- [ ] `PATCH /api/v1/training-sessions/{id}/attendance/{athlete_id}` con status=presente, rpe_omni=7, rubric_effort=4, rubric_attitude=5, rubric_technique=3, individual_feedback="Buen trabajo en bajadas"
- [ ] Respuesta 200, campos persistidos correctamente
- [ ] Atleta con status=ausente + excuse_reason="Enfermedad" → 200
- [ ] Atleta con status=ausente SIN excuse_reason → 422
- [ ] Atleta con status=presente + rpe_omni fuera de rango (11 o -1) → 422
- [ ] Atleta con status=ausente + rubric_effort → 422 (rúbrica solo si asistió)

### 2.3 Upload de archivo .gpx
- [ ] `POST /api/v1/training-sessions/{id}/route-file` con archivo .gpx válido (multipart) → 200, route_file_path poblado
- [ ] Upload con archivo > 5 MB → 413
- [ ] Upload con extensión `.txt` → 422
- [ ] Archivo .gpx con XXE payload (`<!DOCTYPE [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>`) → 422 rechazado
- [ ] Padre intenta upload → 403

### 2.4 Ver historial de asistencia por atleta
- [ ] `GET /api/v1/athletes/{id}/attendance` como coach → 200 con lista de registros
- [ ] `GET /api/v1/athletes/{id}/attendance` como padre (su atleta) → 200 con lista filtrada
- [ ] `GET /api/v1/athletes/{otro_id}/attendance` como padre (atleta ajeno) → 403

---

## 3. Flujo Coach — Generar reporte mensual con IA

### 3.1 Generación de reporte
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` body `{year: 2026, month: 4}` → 201
- [ ] Respuesta incluye `ai_summary` con 2-3 párrafos (no vacío)
- [ ] `ai_summary` NO contiene nombres completos de atletas
- [ ] `metrics_snapshot` contiene: total sesiones, % asistencia por atleta (iniciales), focos técnicos
- [ ] Repetir POST mismo mes → 409 (único por club/año/mes)
- [ ] POST mes futuro → 400
- [ ] POST mes actual antes del día 28 → 400 con mensaje "El mes no ha cerrado aún"

### 3.2 Reenvío de reporte
- [ ] `POST /api/v1/clubs/{id}/monthly-reports/{report_id}/send` → 200
- [ ] Log muestra envío a admin del club (sin PII)
- [ ] Padre intenta este endpoint → 403

### 3.3 Listar y ver reportes
- [ ] `GET /api/v1/clubs/{id}/monthly-reports` como coach → lista de reportes con year/month
- [ ] `GET /api/v1/clubs/{id}/monthly-reports/{year}/{month}` como coach → detalle completo

---

## 4. Flujo Parent — Lectura de sesiones

### 4.1 Ver sesiones del propio atleta
- [ ] Login como padre → token JWT válido
- [ ] `GET /api/v1/training-sessions?athlete_id={id_propio}` → 200, solo sesiones donde su atleta fue convocado
- [ ] `GET /api/v1/training-sessions/{id}` (sesión con su atleta) → 200 con info general de la sesión
- [ ] `GET /api/v1/training-sessions/{id}` (sesión SIN su atleta) → 403 o 404

### 4.2 Ver asistencia propia (solo su atleta)
- [ ] Detalle de sesión como padre muestra SOLO la fila de asistencia de su atleta
- [ ] Verificar en respuesta JSON: campo attendance solo contiene entries de su atleta
- [ ] Verificar en Network tab del browser: no aparecen datos de otros atletas en ninguna respuesta

### 4.3 Ver resumen mensual propio
- [ ] `GET /api/v1/parents/training/monthly-summary/{year}/{month}` → 200 con % asistencia de SU atleta
- [ ] Respuesta NO incluye narrativa IA agregada del club
- [ ] Respuesta NO incluye datos de otros atletas

---

## 5. Pruebas de privacidad (padre intentando URLs de coach)

### 5.1 Acceso a sesiones ajenas
- [ ] Padre A intenta `GET /api/v1/training-sessions/{id}` de sesión donde NINGUNO de sus atletas fue convocado → **esperado: 403 o 404**
- [ ] Padre A intenta `GET /api/v1/training-sessions` sin filtro → lista debe forzarse a solo sus atletas; si no se fuerza, recibe solo las suyas

### 5.2 Modificación de asistencia ajena
- [ ] Padre A intenta `PATCH /api/v1/training-sessions/{id}/attendance/{athlete_id_ajeno}` → **esperado: 403**
- [ ] Padre A intenta `POST /api/v1/training-sessions/{id}/execute` → **esperado: 403**
- [ ] Padre A intenta `POST /api/v1/training-sessions` → **esperado: 403**

### 5.3 Acceso al reporte agregado del club
- [ ] Padre A intenta `GET /api/v1/clubs/{id}/monthly-reports` → **esperado: 403**
- [ ] Padre A intenta `GET /api/v1/clubs/{id}/monthly-reports/{year}/{month}` → **esperado: 403**
- [ ] Padre A intenta `POST /api/v1/clubs/{id}/monthly-reports` → **esperado: 403**

### 5.4 Acceso a datos de atletas ajenos
- [ ] Padre A intenta `GET /api/v1/athletes/{athlete_id_ajeno}/attendance` → **esperado: 403**
- [ ] Verificar que el prompt enviado a la IA (en logs de nivel DEBUG, si habilitados) no contiene nombres completos

---

## 6. Edge cases

### 6.1 Sesión en el pasado
- [ ] Coach intenta crear sesión con `scheduled_date` pasada y `status=planned` → 422
- [ ] Coach puede crear sesión pasada con `status=executed` directamente (para log retroactivo) → verificar si el diseño lo permite; si no, 422

### 6.2 Sesión cancelada
- [ ] `DELETE /api/v1/training-sessions/{id}` → 200, status=cancelled
- [ ] Intentar ejecutar sesión cancelada → 409
- [ ] Intentar modificar asistencia en sesión cancelada → comportamiento definido (403 o 409)
- [ ] Sesión cancelada NO cuenta en métricas del reporte mensual

### 6.3 Sesión sin convocados
- [ ] `POST /api/v1/training-sessions/{id}/execute` sin ningún atleta convocado → debe ejecutarse sin error (coach olvidó agregar convocados; no bloquear flujo)

### 6.4 Reporte mensual mes sin sesiones
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` para mes sin sesiones ejecutadas → 200 o 204 con ai_summary vacío o nota "Sin sesiones en el período"

---

## 7. Performance (smoke tests)

- [ ] `GET /api/v1/training-sessions?from=2026-01-01&to=2026-01-31` con 50 sesiones en DB → respuesta < 300ms (medir con `time curl`)
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` con mock LLM (APP_ENV=development) → completado < 15s
- [ ] Frontend: página `/training/sessions` carga < 500ms con 100 sesiones (Network tab Slow 3G simulado)
- [ ] Frontend: `AttendanceTable` con 20 atletas, autosave debounce 500ms no provoca doble submit

---

## 8. Accesibilidad (smoke tests)

- [ ] Navegar `AttendanceTable` completamente con tecla Tab: todos los controles alcanzables
- [ ] Focus ring visible en todos los elementos interactivos de `AttendanceTable`
- [ ] Screen reader (VoiceOver/NVDA) anuncia correctamente el status de cada fila de asistencia
- [ ] `RubricSliders` tienen labels asociados (no solo placeholders)
- [ ] Formulario de sesión (`SessionFormPage`) sin errores axe-core en consola
- [ ] `MonthlyReportView` con narrativa IA marcada como `aria-live="polite"` si carga asíncrona

---

## 9. Verificación final en producción (post-deploy)

- [ ] `https://mi-2yzi.onrender.com/docs` muestra tags `training-sessions` y `monthly-reports`
- [ ] Login con coach seed funciona (si seed fue aplicado en dev, NO en producción)
- [ ] `GET /api/v1/training-sessions` con token válido retorna 200 (lista vacía es OK)
- [ ] Migración `6e189a7e1e51` y `b2c3d4e5f6a7` aparecen en `alembic_version` de la DB
- [ ] Render logs muestran "Aplicando migraciones..." y "Iniciando servidor..." sin errores
