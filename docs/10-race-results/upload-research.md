# Research — Upload UI de PDFs Copa Valle

**Fecha**: 2026-05-20
**Strategy**: deep
**Para informar**: /sc:design upload race-results
**Branch**: race-results-v2-foundation

---

## Estado actual ingesta

### Pipeline determinista F1.7 lista para envolver en HTTP

La capa de servicio es **autosuficiente** y desacoplada del CLI. Quien la consuma solo necesita reproducir lo que hace `scripts/ingest_race.py` paso a paso.

`backend/app/services/race/ingestor.py:138-402` — `RaceIngestor.ingest_event(...)`:

- **Inputs**: `EventMeta`, `results_by_category: dict[str, list[ResultsRow]]`, `general_by_category` (opcional), `match_decisions: dict[str, Optional[int]]`, `pdf_results_sha256`, `pdf_general_sha256`, `ingested_by_user_id`.
- **Salida**: `IngestReport` (`event_id, series_id, competitors_created, competitors_updated, results_inserted, results_skipped, tyr_count, warnings: list[str]`).
- **Transaccionalidad**: un único `await self.db.commit()` al final del método (`ingestor.py:378`); cualquier excepción dispara `rollback()` (`ingestor.py:400-402`).
- **Idempotencia**: si `RaceImport` ya existe con `status=committed` y mismo `sha256`, aborta sin escribir filas y retorna `IngestReport` con `results_inserted=0` y warning explicativo (`ingestor.py:220-238`).
- **No auto-asigna**: aplica `athlete_id` solo si el coach lo confirmó en `match_decisions` (regla inviolable — `ingestor.py:298-310`).

`backend/app/services/race/pdf_parser.py:211-302` y `:340-435` — `parse_results_pdf(Path) -> dict[code, list[ResultsRow]]` y `parse_general_pdf(Path) -> dict[code, list[GeneralRow]]`:

- Aceptan **rutas a disco** (no buffers). Esto obliga a escribir el upload a tmp antes de parsear, o a refactorizar la firma para aceptar `BinaryIO` (decisión para `/sc:design`).
- `parse_event_header(Path)` extrae `valida_num + location + event_date` autocompletando 80% del `EventMeta`.
- Tamaño esperado: fixtures reales `valida_iv_2026_resultados.pdf` = 246 KB (10 págs, 26 cats, 227 corredores), `valida_iv_2026_general.pdf` = 160 KB (12 págs, 339 filas). Cualquier PDF Federación entra holgadamente en 1-2 MB.

`backend/scripts/ingest_race.py:266-330` — comando `ingest`:

- Flujo interactivo (default): parse → header auto → prompts (clima, temp, surface, altitud, notas) → top-3 por TyR → confirm → ejecutar.
- Modo `--non-interactive`: lee `--event-meta YAML` + `--match-decisions YAML` para CI/tests determinísticos.
- **NO existe** un subcomando `ingest validate` separado. El concepto "dry-run" lo tiene el enum `RaceImportStatus.dry_run` (`race_import.py:36-48`) pero el código nunca lo emite — siempre hace `pending → committed`. Falta exponer dry-run real desde el ingestor (importante para el wizard preview).

`backend/app/services/race/normalizer.py` + `matcher.py`:

- `is_trocha_y_ruta(club, threshold=85)` decide si un competidor pertenece al club (fuzzy híbrido `ratio`/`partial_ratio` con guard de longitud — `normalizer.py:176-208`).
- `match_athletes(competitor_name, competitor_club, competitor_category, athletes, threshold=90)` retorna top-3 `MatchCandidate(athlete_id, full_name, score, age_decimal, reason)`. **No toca DB** (matcher.py:131-227); el caller pre-carga athletes.
- Outputs típicos: 100% match (~score 95 con age boost), no candidato (lista vacía), homónimos (2-3 candidatos con scores cercanos → coach desempata).

---

## Storage SFTP — viable?

**Respuesta corta**: sí, con caveats. El wrapper existente sirve casi sin cambios pero hay limitaciones a documentar.

### Lo que sí funciona

`backend/app/services/training/storage_sftp.py`:

- **No es SFTP real**: a pesar del nombre, es **FTPS** (FTP sobre TLS, puerto 21) — Hostinger Shared no expone SFTP/SSH en puerto 22 (`storage_sftp.py:1-16`).
- API pública genérica: `upload_bytes(content: bytes, relative_path: str) -> tuple[storage_path, storage_url]` y `delete_object(storage_path)`.
- **No discrimina por extensión** — sube cualquier `bytes`. PDFs funcionan igual que JPGs.
- **Fallback local automático**: si faltan envs `HOSTINGER_SFTP_*`, escribe en `static/uploads/media/` y construye URL `/static/uploads/media/...` (montada en `main.py:53-55`). Cero configuración para dev/tests.

### Caveats importantes

1. **URL pública sin auth**: `storage_url` es público (`hostinger_public_base_url/...`). Para PDFs con resultados estos son **información ya pública** (la Federación los publica), pero el storage es accesible por path-guessing. Mitigación: prefix con UUID (como hace `media_files.py:180`), no usar filename original.
2. **Sin verificación TLS** (`storage_sftp.py:50-61`): Hostinger Shared usa cert genérico sin SAN, así que `check_hostname=False, verify_mode=CERT_NONE`. La sesión queda cifrada pero no autenticada. Aceptado por el proyecto para fotos/videos; aplica igual aquí.
3. **Render free tier compatibilidad**: el wrapper hace `asyncio.to_thread(...)` para no bloquear el event loop (`storage_sftp.py:188`). Cold start de ~50s al despertar Render no afecta el FTPS post-warm-up. **Confirmado que funciona en producción** — es el mismo wrapper usado por F1.6 media.
4. **Envs requeridas en Render** (pendiente paso 9 de F1.6 según `CLAUDE.md`): `HOSTINGER_SFTP_HOST/PORT/USER/PASS/REMOTE_DIR` + `HOSTINGER_PUBLIC_BASE_URL`. Si no se configuran, F1.6 media y este nuevo upload caerán al fallback local — que en Render free tier es **efímero** (filesystem se borra al redeploy). **Bloqueador operativo** para usuarios reales si no se setean primero.
5. **Sin tamaño máximo en el wrapper**. El cap viene del caller (`media_files.py:154-166` lee `settings.media_max_photo_mb`/`max_video_mb`). Para PDFs hay que introducir `settings.race_max_pdf_mb` (sugerencia: 8 MB).
6. **Sin generación de URL firmada / signed URLs**: la URL es estática y permanente. Para PDFs es probablemente OK (ya son públicos).

### Patrón de uso real referencia

`backend/app/services/training/media_files.py:140-199` — `save_session_media`:

- Lee bytes con cap defensivo (`max_bytes + 1`).
- Valida magic bytes por extensión (`_check_magic_bytes`).
- Genera `base_name = uuid.uuid4().hex` → `relative_path = f"sessions/{session_id}/{base_name}{ext}"`.
- Sube via `storage_sftp.upload_bytes`, retorna `StoredMedia(storage_url, storage_path, mime_type, size_bytes, ...)`.

Para PDFs el patrón se simplifica (sin thumbnail, sin EXIF strip, sin width/height). Sí sigue aplicando: magic bytes, cap de tamaño, UUID en path.

---

## Modelo de datos — gaps

### Lo que ya tiene `RaceImport`

`backend/app/models/race_import.py`:

- `id, filename(200), sha256(CHAR 64), series_id, status(enum), stats_json, error_log(text), imported_by_user_id, imported_at`.
- Índices: `imported_at`, `sha256`, `(status, sha256)`. Adecuados para deduplicación rápida.
- Ya guarda **`imported_by_user_id`** → resuelve "quién subió".
- Ya guarda **`filename`** (200 chars) → resuelve "nombre original".
- Status enum incluye `dry_run` — **soportado en modelo pero nunca usado en código**.

### Gaps a llenar para el upload UI

1. **No guarda `storage_path` ni `storage_url`** del PDF subido. Esto significa que tras la ingesta no podemos volver a descargar el PDF original desde la UI. Decisión para `/sc:design`: agregar `pdf_storage_path: String(500) NULL` + `pdf_storage_url: String(500) NULL`, o no almacenarlo (re-cargar siempre desde local del coach).
2. **No diferencia RESULTADOS vs GENERAL**: hay `filename` + `sha256` pero un solo registro por ingesta. Hoy el ingestor solo dedupe sobre el sha de RESULTADOS (`ingestor.py:220-238`). Si queremos trazabilidad del GENERAL, necesitamos columnas adicionales (`general_filename`, `general_sha256`, `general_storage_path`) o un patrón `kind: enum('results','general')` con dos filas. **Decisión sugerida**: extender la fila única — el sha del GENERAL ya se pasa pero solo se loggea (`ingestor.py:175`), guardarlo en columna deduplicaría también ese PDF.
3. **`RaceImport` no enlaza directo a `RaceEvent`**: solo via `series_id`. La asociación con el evento concreto se descubre indirectamente por `imported_at` o por `RaceResult.imported_from_id` (FK que sí existe en migración delta — confirmado en `ingestor.py:357`). Para la UI esto fuerza un JOIN — agregar `event_id NULL` a `RaceImport` simplificaría queries del historial.
4. **`RaceEvent.pdf_results_filename` / `pdf_general_filename`** (`race_event.py:120-121`) ya existen como `String(255) NULL` y se popsulan en el upsert (`ingestor.py:460-461, 484-486`). **Solapamiento con `RaceImport.filename`** — actualmente ambos guardan lo mismo. No es bug, es redundancia barata.

### Conclusión modelo

Migración mínima sugerida (a confirmar en design):

```sql
ALTER TABLE race_imports
  ADD COLUMN event_id INT NULL,
  ADD COLUMN kind ENUM('results','general') NOT NULL DEFAULT 'results',
  ADD COLUMN storage_path VARCHAR(500) NULL,
  ADD COLUMN storage_url VARCHAR(500) NULL,
  ADD FOREIGN KEY (event_id) REFERENCES race_events(id) ON DELETE SET NULL;
```

Si la decisión es "no guardar PDFs" (solo procesar y descartar), bastan `event_id` + `kind`.

---

## Patrones existentes proyecto

### Backend — endpoint upload de referencia

`backend/app/routers/training_sessions.py:690-786` — `POST /training-sessions/{id}/route-file`:

Patrón directo para multipart + magic bytes + size cap + RBAC. Reusable casi 1:1:

- Firma: `file: Annotated[UploadFile, File(...)], db, current_user = Depends(require_role([admin, coach]))`.
- Validación de extensión: `filename.endswith(".gpx") / .fit`.
- Validación de content-type (whitelist por extensión).
- Cap defensivo: `raw = await file.read(max_size + 1)` → si excede, 400.
- Magic bytes: FIT requiere primer byte `0x0E` + header ≥14 (`training_sessions.py:756-761`).
- Rebobinado para handoff al service: `file.file = io.BytesIO(raw)` (`training_sessions.py:764-765`).
- Service call: `await training_svc.route_files.save_route_file(file, session_id)`.

`backend/app/routers/training_sessions.py:835-926` — `POST /training-sessions/{id}/media`:

Patrón más completo (multipart con campos adicionales tipo `athlete_ids: Form(str)`, `consent_ack: Form(bool)`). Útil si queremos subir **2 archivos + meta event en un solo POST** o usar `Form` para `match_decisions` JSON. Sospecho que necesitamos **2 endpoints** (paso de wizard) y no un mega-POST.

### Frontend — drag-and-drop ya construido

`frontend/src/components/training/MediaUploadZone.tsx`:

- Drag & drop nativo con keyboard support (Enter/Space en `role="button"`).
- Validación pre-upload: extensión + tamaño (constantes `MAX_PHOTO_MB = 10`, `MAX_VIDEO_MB = 50`).
- UI: dropzone idle → form con `pendingFile` + caption + athlete chips + consent checkbox + submit con loader.
- `data-testid` consistentes (`media-upload-dropzone`, `media-file-input`, `media-submit-button`) — facilita E2E.
- **Reusable casi 1:1** cambiando: tipos aceptados (`.pdf`), cap (8 MB), campos de form (resultados-pdf / general-pdf / event meta).

`frontend/src/api/sessionMedia.ts:23-41` — `uploadSessionMedia(sessionId, payload)`:

Patrón axios + `FormData` + `multipart/form-data` ya validado. Para 2 archivos: `formData.append("resultados_pdf", f1); formData.append("general_pdf", f2);`.

`frontend/src/api/raceAnalysis.ts:24-32` y `:106-136` — convenciones específicas de race-analysis (`/api/race-analysis/...`, descarga blob autenticada). **El nuevo endpoint debería vivir bajo el mismo prefix** para coherencia (`POST /api/race-analysis/imports/...`).

### Frontend — landing donde injectar

`frontend/src/routes/results/RaceAnalysisPage.tsx:111-209`:

3 tabs actuales: `new` (Nuevo análisis), `active` (Runs activos), `history` (Insights históricos). El upload entra naturalmente como **4ta tab "Cargar resultados"** (ver §UX). El tab "history" es placeholder — también podría reutilizarse esa pestaña para "Ingestas previas + insights" si queremos minimizar tabs.

---

## Security PDF upload

Checklist OWASP File Upload + estado del proyecto:

| Control | Estado en proyecto | Nota |
|---|---|---|
| **Magic bytes verification** | Patrón existe en `media_files.py:65-87` y `training_sessions.py:756`. Para PDF: validar `%PDF-` (`b"%PDF-"`) en primeros 5 bytes. | A implementar en service de PDFs. |
| **Tamaño máximo** | Patrón `await file.read(max_bytes + 1)` validado. Recomendación 8 MB (fixture real = 246 KB; deja 32x margen). Render free tier acepta uploads grandes sin config explícita; el cuello de botella es timeout HTTP, no body size. | A implementar; settings nuevo `race_max_pdf_mb`. |
| **Whitelist extension** | Patrón `filename.endswith(".pdf")` validado. | Trivial. |
| **Whitelist content-type** | Patrón en `_GPX_CONTENT_TYPES`. Para PDFs: `application/pdf`, `application/octet-stream`. | Trivial. |
| **defusedxml para XXE** | `defusedxml>=0.7` ya en `requirements.txt`. `pdfplumber` NO usa XML interno expuesto; PDF es binario propio. **No aplica directamente** a este pipeline — pdfplumber procesa streams binarios + extracción texto via PDFMiner. Riesgo XXE bajo en pdfplumber, no documentado como vector activo. | OK por ahora; documentar como riesgo aceptado. |
| **Path traversal en filename** | Patrón `uuid.uuid4().hex + ext` en `media_files.py:180`. **Crítico**: no usar `file.filename` para construir `storage_path`. Guardar el original en `filename_original` (columna separada). | A implementar. |
| **RBAC: solo coach + admin** | Patrón `Depends(require_role([UserRole.admin, UserRole.coach]))` consistente en todos los routers. Padres bloqueados. | A aplicar. |
| **Rate limiting** | **NO existe middleware global** (verificado en `app/main.py` y grep `slowapi/RateLimit`). Hay throttle ad-hoc en notificaciones (`calendar/notifications.py`) — patrón in-memory simple. Upload de PDFs es operación poco frecuente (1-2 por mes); ataque DoS por upload no es realista. **Riesgo aceptable sin rate limit MVP**; aún así, considerar un guard tonto: max 5 uploads/min por user_id en memoria. | Opcional MVP. |
| **Sandbox parsing** | `pdfplumber` corre in-process. Si un PDF malicioso explota CVE de pdfminer, comprometería el worker. Mitigación: **try/except amplio** + timeout (a evaluar — pdfplumber no expone API de timeout nativa, requeriría `asyncio.wait_for(...)` en thread). | A considerar para hardening F2. |
| **Auditoría del subidor** | `RaceImport.imported_by_user_id` ya cubre. Log estructurado: `logger.info("race_pdf_uploaded user_id=%d filename=%s sha=%s", ...)` sin PII. | A implementar en service. |
| **Logs sin PII** | Restricción inviolable (CLAUDE.md). Patrón ya seguido por ingestor (warnings usan `bib + cat_code`, no nombres). | OK by design. |

### Riesgos altos identificados

- **Single point of failure parser**: si pdfplumber lanza excepción no contemplada con un PDF malformado, el endpoint debe retornar 422 con mensaje accionable ("PDF corrupto o no oficial"), no 500. Verificar que `parse_results_pdf` no haga `raise` silenciosos.
- **Memory bloat con PDFs grandes**: pdfplumber carga páginas en memoria. Con cap 8 MB y free tier 512 MB de RAM en Render, el riesgo es teórico — pero abrir 3 PDFs concurrentes podría ahogar. Mitigación: serializar uploads con un lock o semáforo si el patrón se vuelve común (no MVP).

---

## UX referencia

### Decisión recomendada: pestaña nueva "Cargar resultados"

En `RaceAnalysisPage.tsx`, insertar como segunda tab (entre "Nuevo análisis" y "Runs activos"). Justificación:

- "Nuevo análisis" arranca un agente sobre datos ya ingestados → conceptualmente posterior.
- La carga es operación periódica (1-2 por mes, tras cada válida) y dispara el resto del flujo.
- Tab dedicada permite mostrar **historial de ingestas previas** abajo (consultando `RaceImport` filtrado por series 2026) — feature pequeña y útil que el CLI no tiene.

Estructura del wizard (3 pasos):

```
Paso 1: Seleccionar archivos
  ├── Dropzone RESULTADOS (.pdf, máx 8 MB)
  ├── Dropzone GENERAL (.pdf, máx 8 MB, opcional)
  ├── Auto-detect header → muestra "Válida IV · Cali · 17-may-2026"
  └── [Siguiente]

Paso 2: Confirmar metadata + matches
  ├── Form EventMeta pre-rellenado (valida_num, location, event_date editables;
  │   climate/temperature/surface/altitude/notes opcionales)
  ├── Tabla de matches TyR: bib | nombre PDF | top-3 candidatos (radio buttons) |
  │   "skip" | "new athlete"
  ├── Banner de warnings (categorías desconocidas, tiempos anómalos)
  └── [Atrás] [Siguiente]

Paso 3: Preview + commit
  ├── Resumen tipo IngestReport (categorías, corredores, TyR, decisiones tomadas)
  ├── Dry-run: backend valida sin escribir (requiere implementar dry-run real
  │   en ingestor — gap detectado)
  ├── Si idempotente (sha ya committed): banner amarillo "Este PDF ya fue
  │   ingestado el YYYY-MM-DD. ¿Re-procesar?" → No por default
  └── [Confirmar e ingestar] → loading → IngestReport final
```

### Componentes a reusar

- **Dropzone**: clonar `MediaUploadZone` simplificado (sin thumbnails, sin athlete chips, sin consent).
- **Stepper**: no existe componente reutilizable en `components/ui/`. `RaceAnalysisPage` usa `@radix-ui/react-tabs` para pasos no-secuenciales — para wizard secuencial el patrón canónico shadcn es `Stepper` custom o reutilizar `Tabs` con `disabled` en pasos no alcanzados.
- **Tabla de matches**: clonar patrón visual de `AttendanceTable.tsx` (`frontend/src/components/training/`); soporta selección y feedback inline.
- **Banner warnings**: reusar `ExplainModeBanner` / banners shadcn (`Alert`).
- **Spinner / loading**: `Loader2` de `lucide-react`, patrón ya usado.

### Estados a manejar

| Estado | UX |
|---|---|
| Idle pre-upload | Dropzone vacío con CTA |
| Drag-over | Borde resaltado (patrón ya en MediaUploadZone) |
| Parsing (post-upload) | Spinner "Analizando PDF..." (parsing puede tardar 2-5s con pdfplumber) |
| Header no detectado | Form vacío + warning "Pudimos parsear el PDF pero no detectamos el header. Completa los datos manualmente." |
| Categoría desconocida | Warning no-bloqueante en paso 2 con código raw |
| Bib sin match top-3 | Radio "skip" preseleccionado, link "→ Crear nuevo atleta" (diferir creación a UI separada) |
| Dry-run OK | Banner verde con conteos previos al commit |
| sha duplicado | Banner amarillo + opción "Forzar re-ingesta" (no recomendada; solo admin) |
| Commit OK | `IngestReport` formateado + CTA "Ir a Nuevo análisis" |
| Error parser | Banner rojo "El PDF no tiene formato Federación oficial" + log técnico colapsado |
| Error red | Toast + retry button |

---

## Validación inputs

### Reglas duras (del schema `EventMeta` y modelo)

- `season ∈ [2020, 2100]` (`schemas/race.py:47`).
- `valida_num ∈ [1..7] ∪ {99}` con validator explícito (`schemas/race.py:61-69`).
- `name max 200`, `location max 150`, `climate max 60`, `weather_notes` libre, `pdf_results_filename max 255`, `pdf_general_filename max 255`.
- `temperature_c ∈ [-10, 50]` con validator (`schemas/race.py:71-80`).
- `altitude_msnm ∈ [0, 6000]`.
- `surface_condition` enum: `seca | humeda | barro | lluvia | mixta`.
- `RaceSeries` UNIQUE `(name, season_year)` (`race_series.py:34-36`).
- `RaceEvent` UNIQUE `(series_id, sequence_number)` (`race_event.py:80`).
- `RaceImport.sha256 CHAR(64)` — siempre presente.

### Comportamiento idempotencia

- Re-upload del **mismo PDF (mismo sha256)** con status `committed` → ingestor **no escribe** filas nuevas y retorna report con `results_inserted=0` + warning. Operación es **segura by default**.
- Re-upload con **valida_num distinto** → crea/actualiza otro `RaceEvent` (upsert por `series_id, sequence_number`). El coach puede actualizar clima/superficie sin tocar SQL (`ingestor.py:467-487`).
- Re-upload **PDF corregido** (mismo valida, distinto contenido → distinto sha) → escribe filas adicionales. `RaceResult` tiene UNIQUE `(event_id, category_id, competitor_id)` → si ya hay resultado para esa tripla, **se salta** con `results_skipped++`. **Limitación**: si la corrección cambia el tiempo de un resultado existente, no se actualiza — queda el valor viejo. Esto es por diseño F1.7 (revisar es responsabilidad del coach via SQL o UI futura `race_result_revisions`). Documentar al coach.

### Reglas blandas (warnings, no bloquean)

- Categoría en RESULTADOS pero no en seed → `ValueError` que **sí bloquea** la transacción (`ingestor.py:276-280`). Decisión: en UI capturar y mostrar "categoría desconocida, contactar admin para extender seed".
- Tiempo anómalo (<25 min en INF/PJUV/JUN o <2 min en TET o <5 min en PRE) → warning con `bib + cat`, no bloquea (`ingestor.py:328-339`).
- Bib en GENERAL ausente en RESULTADOS → no warning automático (sería ruidoso). Edge case documentado `edge-cases.md §4.12`.

### Edge cases no obvios

- **`GENERAL` no es CSV-importable**: Federación solo publica GENERAL en PDF (`scripts/ingest_race.py:280-283`). RESULTADOS sí acepta `.csv/.tsv/.txt` (Sevilla 2026 fixture). El upload UI debe permitir RESULTADOS `.pdf` o `.csv`, GENERAL solo `.pdf`. Decisión `/sc:design`: ¿soportar CSV en MVP o solo PDF?
- **Header no detectado** → en CLI se pregunta interactivamente (`ingest_race.py:521-527`). En UI: form manual del paso 2 cubre este caso.
- **Series 2026 ya existe**: el upsert por `(name="Copa Valle de Ciclomontañismo", season_year=2026)` es transparente (`ingestor.py:408-427`). El coach no necesita crear series previo.

---

## Open questions para /sc:design

1. **¿Guardar el PDF en storage o solo procesar?**
   - A favor de guardar: re-procesar sin pedir al coach, audit, troubleshoot del parser con casos reales.
   - En contra: storage cost (mínimo), URL pública (mitigable con UUID), modelo gana 2 columnas.
   - Recomendación research: **guardar** — el costo es marginal y desbloquea features futuros (re-parse, evidence en chat agéntico).

2. **¿Dry-run real o solo preview client-side?**
   - El ingestor **no** soporta dry-run hoy (status enum lo permite pero código nunca lo usa). Implementar requiere: corre todo el flujo sin commit, retorna `IngestReport` ficticio, hace `db.rollback()` al final. Esfuerzo ~30 LOC en service.
   - Alternativa MVP: skip dry-run, mostrar paso 2 con datos parseados y matchear inmediatamente al confirmar.
   - Recomendación: **implementar dry-run server-side** — el wizard se vuelve mucho más seguro y el patrón se reusa para troubleshoot.

3. **¿Wizard 1 endpoint o 3 endpoints?**
   - 3 endpoints (paso 1 = `POST /imports/parse` retorna parsed JSON + event header detectado, paso 2 = `POST /imports/dry-run` con meta+decisions retorna IngestReport, paso 3 = `POST /imports/commit` con mismo body ejecuta) → mejor UX, requiere persistir parsed entre pasos (en client state o en `RaceImport.status=pending` temporal).
   - 1 mega-endpoint (`POST /imports` con todo) → más simple, peor UX (re-parsea en cada paso si el coach edita).
   - Recomendación: **3 endpoints** — la latencia de parse pdfplumber (2-5s) hace impráctico repetirla.

4. **¿"Forzar re-ingesta" para sha duplicado?**
   - El comportamiento actual es seguro (abort). UI necesita decisión: ¿escondemos la opción o la mostramos solo a admins?
   - Recomendación: mostrar como advertencia, no como botón principal; requerir checkbox "Sé que esto duplicará registros si fue un error".

5. **¿Crear `RaceCompetitor` no-TyR sin athlete_id es OK?**
   - Hoy el ingestor lo hace siempre (`ingestor.py:284-296`). La UI no necesita preguntar nada para no-TyR. Solo confirmar que está OK con el coach.

6. **¿Soportar CSV en MVP de la UI?**
   - El service ya soporta autodispatch por extensión (`scripts/ingest_race.py:247-251`). Agregarlo al endpoint cuesta nada. Pero la mayoría de PDFs serán PDF Federación.
   - Recomendación: **sí incluir** — esfuerzo marginal, cubre el caso Sevilla V-I 2026.

7. **¿Permitir editar PDF metadata después del commit?**
   - El upsert de `RaceEvent` ya lo permite — re-subir el mismo PDF con meta actualizada lo refleja. ¿Necesitamos un endpoint dedicado "editar clima" sin re-subir?
   - Diferir a F2; no MVP.

8. **¿Posición del wizard: tab dedicada o modal global?**
   - Recomendación research: **tab dedicada** "Cargar resultados". Mantiene estado al navegar.

9. **¿Polling o sincrónico para el commit?**
   - El ingestor es síncrono (<2s para 227 corredores en local). En Render free tier con cold start podría tardar más.
   - Recomendación: **sincrónico con timeout de 60s**. Si tardara más sería bug del parser, no carga normal.

10. **¿Crear nuevo athlete desde el wizard inline o redirigir?**
    - En CLI, "n(ew)" deja `athlete_id=None` y el coach crea el athlete después (`riders link` para vincular). Mismo patrón en UI: opción "Pendiente — crear atleta después" + link al CRUD de athletes.
    - Recomendación: **diferir creación** (no inline).

---

## Recomendación final research

**Enfoque sugerido**: implementar el upload como **wizard de 3 pasos en una tab nueva "Cargar resultados"** dentro de `RaceAnalysisPage.tsx`, respaldado por **3 endpoints REST** bajo `/api/race-analysis/imports/*` que envuelven la pipeline F1.7 existente sin tocarla. La capa de servicio determinista (`RaceIngestor`, `pdf_parser`, `matcher`, `normalizer`) es **autosuficiente y bien testeada (305 tests, 98% cobertura)** — solo necesita un wrapper HTTP, manejo de upload multipart con magic bytes / size cap (patrones ya validados en `route-file` y `media`), persistencia transitoria de PDFs en `storage_sftp` con UUID en path, y dos pequeños gaps a llenar: (a) **implementar dry-run real** en `RaceIngestor` (~30 LOC) para que el paso 2 del wizard pueda mostrar preview sin escribir, (b) **extender `RaceImport`** con `event_id`, `kind`, `storage_path`, `storage_url` para trazabilidad completa.

**Riesgos a vigilar**: (1) `pdf_parser.parse_results_pdf` solo acepta `Path` y no `BinaryIO` — obliga a `tempfile` o un refactor (decidir en design); (2) las envs `HOSTINGER_SFTP_*` siguen pendientes en Render según F1.6 paso 9 — sin esas envs el storage cae a fallback local que se borra al redeploy, **bloqueador operativo silencioso**; (3) el patrón "el coach interactivo confirma top-3 matches" se traduce mal a UI sin diseño visual cuidado de la tabla de matches — invertir aquí evita que el coach abandone el wizard. La gran ventaja de este camino es que **no toca la lógica de negocio probada** — todo lo nuevo es HTTP + UI + 2 migraciones triviales.
