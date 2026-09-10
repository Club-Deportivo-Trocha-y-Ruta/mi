# Auditoría de privacidad — T091 (feature 041, gobernanza multi-entrenador)

**Norma**: Ley 1581 de 2012 (datos personales) y Ley 1098 de 2006 (infancia y
adolescencia) — todos los deportistas del club tienen entre 10 y 15 años,
así que sus datos son sensibles por definición.

**Alcance**: el diff completo de la rama `feat/041-multi-coach-governance`
contra `main` (`git diff main...HEAD`, 418 archivos), leído contra el
checklist de 7 puntos del encargo. Corrida nocturna sin supervisión — no hay
MySQL disponible en este entorno, así que ningún hallazgo aquí se validó
contra datos reales; donde eso importa se marca explícitamente como "no
verificable aquí".

**Fecha**: 2026-09-10. **Auditor**: agente `data-privacy-guard` (Claude Sonnet
5), corrida automática nocturna.

---

## 1. Veredictos por punto del checklist

| # | Punto | Veredicto | Nota |
|---|---|---|---|
| 1 | `audit_log.diff_json`/`meta_json` respetan `VALUE_ALLOWLIST`/`META_ALLOWLIST` | **Cumple** | Ver §2.1 |
| 2 | Esquemas de cara a la familia (boletín, sesiones, calendario) sin campos de atribución | **Cumple, con 1 corrección aplicada** | Ver §2.2 |
| 3 | PDF/correo familiar sin nombre de entrenador donde el contrato lo prohíbe | **Cumple** | Ver §2.3 |
| 4 | Logs con `request_id`, nunca el cuerpo de la petición | **Cumple** | Ver §2.4 |
| 5 | Exportaciones auditadas solo por tipo de documento + athlete_id | **Cumple** | Ver §2.5 |
| 6 | Fixtures/seeds versionados son sintéticos | **Cumple** | Ver §2.6 |
| 7 | Informe de actividad por entrenador y gasto de IA por entrenador exponen solo personal adulto | **Cumple** | Ver §2.7 |

**No verificable aquí (aplica a los 7 puntos)**: nada de lo anterior corrió
contra MySQL real ni contra la app viva — no hay servidor MySQL en este
entorno (`nc 127.0.0.1 3306` rehúsa conexión, no hay Docker). La verificación
fue lectura de código + un test unitario offline puntual (validación Pydantic
sin DB) para el hallazgo A. La suite `pytest -m mysql` / los tests de router
que dependen de `TEST_DATABASE_URL` (p. ej. `test_training_session_router.py`,
que declara explícitamente "Requiere DB de test disponible") no se pudieron
ejecutar. Esto coincide con la nota ya dejada en `plan.md` sobre T027/T028
diferidas por infraestructura.

---

## 2. Detalle por punto

### 2.1 — `VALUE_ALLOWLIST` / `META_ALLOWLIST` (`backend/app/services/audit.py`)

Revisé el catálogo cerrado (líneas 266–388) y el punto único de escritura
`record_audit` (líneas ~656–714):

- `diff_json` se filtra por `VALUE_ALLOWLIST.get(entity_type)` antes de
  persistir — cualquier clave no listada se descarta en silencio, nunca se
  guarda. Ninguna entrada del allowlist admite nombre, fecha de nacimiento,
  medida antropométrica o texto libre; la única excepción documentada
  (`athlete_monthly_newsletter.hidden_blocks`) es una lista de *claves* de
  bloque estáticas, no contenido.
- `meta_json` usa allowlist positiva y **lanza `AuditContractError`** ante
  cualquier clave desconocida — no hay degradación silenciosa como en
  `diff_json`.
- `changed_fields` (los únicos nombres de columna que viajan sin filtrar,
  por diseño — línea 260: "Default... names only in changed_fields, no value
  anywhere") se confirmó que en los 42 sitios de llamada nunca lleva un
  valor, solo nombres de columna (`"email"`, `"first_name"`, etc.), lo cual
  es exactamente lo que el punto 1 del checklist permite ("column names...
  only, never a name... of a minor").
- Verifiqué que no existe ningún `AuditLog(...)` construido fuera de
  `record_audit` (`grep -rn "AuditLog(" app/` solo encuentra el modelo y el
  propio `audit.py`) — no hay vía de escape del allowlist.
- Revisé manualmente ~15 sitios de llamada representativos
  (`app/routers/users.py:227`, `app/services/training/sessions.py:1120`,
  `app/services/calendar/events.py:483`, `app/routers/monthly_reports.py:910`,
  etc.) — todos construyen `diff`/`meta` con las claves del allowlist, sin
  intentos de colar texto libre por una clave permitida (p. ej.
  `narrative_blocks` del boletín solo entra en `changed_fields`, nunca en
  `diff`).
- El log de línea 704–727 (`logging.getLogger(__name__).debug/warning`) solo
  emite conteos y enums (`entity_type`, `action`, `*_count`,
  `used_reserve_request_id`) — nunca `entity_id`, actor ni valores.

No verificable aquí: no pude correr `tests/test_audit_privacy.py`,
`tests/test_audit_mysql.py` ni el resto de la familia `test_audit_*` (19
archivos nuevos) contra una base real — se leyeron pero no se ejecutaron.

### 2.2 — Esquemas de cara a la familia — sesiones, boletín, calendario

- **Boletín** (`AthleteNewsletterRead` vs `ParentNewsletterOut`): la
  superficie coach (`app/schemas/athlete_newsletter.py:227`) expone
  `coach_note_author`, `last_edited_by`, `generated_by`, `approved_by`
  (todos `ActorRef`), documentado explícitamente como exclusivo
  coach/admin (FR-012). `ParentNewsletterOut`
  (`app/schemas/parent_newsletter.py`) no tiene ningún campo de atribución
  — solo `id/athlete_id/year/month/period_label/sent_at/read_at/has_pdf/
  stage_log` (este último ya pasado por `to_parent_dto`, un allow-list
  explícito). **Cumple.**
- **Calendario** (`EventRead` vs `EventReadParent`,
  `app/schemas/calendar.py:303/328`): `EventReadParent` omite
  explícitamente `created_by_user_id` y `audiences` (comentario propio:
  "omite created_by_user_id y audiencia interna"). **Cumple.**
- **Sesiones de entrenamiento** — **hallazgo A (corregido)**:
  `TrainingSessionReadParent` (`app/schemas/training_session.py`) excluía
  ya `coaches` y `has_active_coach` con el comentario explícito "la familia
  nunca ve qué entrenador dirige la sesión en pantalla" (FR-032/§3.1), pero
  **sí** dejaba pasar `created_by_user_id` (un id interno de personal, sin
  resolver a nombre) — el mismo dato que esa regla dice ocultar, solo que
  en su forma cruda. Corregido en esta corrida (ver §3).

Hallazgo incidental fuera de alcance (no corregido, pre-existente en
`main`, no tocado por el diff de 041): `GET
/api/calendar/events/{id}/attendances`
(`backend/app/routers/calendar.py:610-613`, rama no-`training_session`) sí
deja pasar `rsvp_by_user_id` sin filtrar hacia un padre — si un coach hizo
el RSVP por un atleta (`can_rsvp_event` permite a cualquier coach/admin del
club RSVP por cualquier atleta, `app/services/permissions.py:477-479`), el
padre ve el id crudo del entrenador en la respuesta. Confirmé con
`git show main:...` que esta línea es idéntica en `main` — no forma parte
del diff de esta feature, así que queda fuera del veredicto de este punto,
pero lo dejo anotado porque es la misma clase de defecto que el hallazgo A.

### 2.3 — Plantillas PDF/correo familiares sin nombre de entrenador donde el contrato lo prohíbe

- `templates/email/athlete_stage_log.html` y
  `templates/documents/pdf/athlete_stage_log.html` (boletín): sin
  interpolación de `coach_note_author`/`last_edited_by`/`generated_by`/
  `approved_by` — solo hay comentarios explícitos advirtiendo a futuros
  editores que NO agreguen esos campos a esa plantilla.
- `templates/email/training_session_{invite,updated,cancelled}.{html,txt}`
  SÍ muestran `acting_coach_name`/`coach_names`/`coaches_text` — esto es
  intencional y está en el contrato mismo
  (`contracts/session-coaches.md:270-343`, tabla B-08/B-09/B-17): el correo
  de sesión es una superficie distinta del boletín, con su propia regla ("el
  correo con el entrenador que actúa"), no la regla de voz institucional del
  boletín. No es una violación.

**Cumple**, sin correcciones necesarias.

### 2.4 — Logs con `request_id`, sin cuerpo de la petición

- `RequestIdLogFilter` (`app/main.py:23-41`) inyecta `request_id` en todo
  registro de los loggers `app.*` leyendo el `ContextVar` de
  `app/services/request_context.py`; `test_logging_config.py` (offline, sin
  DB) corrió limpio y confirma el comportamiento (5 tests, 0 fallos).
- El único `except Exception` global de `app/main.py:134-146` loguea
  `method`/`path`/`error_type` — nunca el cuerpo. `path` son rutas con ids
  numéricos, sin nombre.
- `record_audit` (§2.1) solo loguea conteos.
- No encontré ningún `logger.*` que reciba `await request.json()`, `body`
  ni `payload` en el código tocado por el diff.

**Cumple.**

### 2.5 — Exportaciones auditadas solo por tipo de documento + athlete_id

Revisé los 9 sitios que escriben `meta={"document_kind": ...}`
(`race_analysis.py:1452`, `monthly_reports.py:622/779`, `intervals.py:1227`,
`parent_newsletters.py:256`, `reports.py:142/212/323`,
`athlete_monthly_newsletters.py:1057`) — todos siguen el mismo patrón:
`entity_id` de la fila fuente, `athlete_id` cuando aplica, `club_id`,
`meta={"document_kind": ...}`, y el comentario propio del código dice
literalmente "SOLO el tipo de documento y el athlete_id, nunca su
contenido". Ninguno agrega nombre de archivo, texto renderizado ni ningún
otro dato del contenido del documento.

**Cumple.**

### 2.6 — Fixtures/seeds versionados sintéticos

- `backend/tests/fixtures/two_coaches.py` (nueva, 374 líneas): declara
  explícitamente "Ningún nombre corresponde a una persona real" y usa
  `ATHLETE_FIRST_NAME = "Mariana Ficticia"` — la palabra "Ficticia" queda
  literalmente en el dato, marcándolo sin ambigüedad.
- Búsqueda dirigida de patrones de cédula (`\d{6,12}` en clave `cedula`),
  dirección (`direccion`/`address_line`/`home_address`) y teléfono
  colombiano (`+57...`) en todo `tests/` y `app/`: **cero coincidencias** —
  el modelo `Athlete` (`app/models/athlete.py`) ni siquiera tiene columnas
  de documento de identidad o dirección, así que esa clase de dato no
  existe en la app.
- Migración `45cd705c6b54_multi_coach_governance.py`: solo DDL y un backfill
  `INSERT ... SELECT` desde columnas existentes — sin literales de datos.

**Cumple.**

### 2.7 — Informe de actividad por entrenador y gasto de IA por entrenador

- `app/schemas/coach_activity.py`: el propio docstring fija el contrato
  ("nombres de personal adulto y enteros, nada más... Ningún athlete_id,
  ningún nombre de menor..."), respaldado por un test dedicado
  (`tests/test_coach_activity.py`, no ejecutable aquí sin DB). Revisé los
  modelos (`CoachRef`, `ClubTotals`, `CoachActivityRow`) — son contadores
  cerrados, sin ningún campo de texto libre ni id de atleta.
- `app/services/coach_activity.py`: el único uso de `Athlete` es un
  `outerjoin` para acotar por club (línea 361-382); el comentario propio lo
  deja explícito ("ni su id ni su nombre salen en el payload"). `first_name`/
  `last_name` que sí se seleccionan (líneas 193-206) son de `User`
  (entrenador/admin), no de `Athlete`.
- `spend_by_user_last_30d` (`app/services/race/ai/budget_guard.py:233-320`,
  archivo que otro agente tiene en edición ahora mismo — solo lectura):
  resuelve nombres exclusivamente contra `users` (`_QUERY_RESOLVE_NAMES`,
  línea 215-217); el hallazgo H3 documentado en el propio código (ya
  corregido en este mismo diff, commit `8ca2870`) repliega el gasto de
  personal de otros clubes en una fila "Otros clubes" sin resolver nombre
  cuando quien consulta es coach — el admin sigue viendo todo el staff. El
  llamador (`app/routers/race_analysis.py:1756-1779`, también en edición
  ajena) pasa `visible_user_ids=None` solo para admin.
- Frontend `AIHealthPage.tsx` y `CoachActivityPage.tsx`: sin ninguna
  referencia a `athlete`/`birth`/dato de menor.

**Cumple.**

---

## 3. Corrección aplicada en esta corrida

**Hallazgo A — severidad ALTA (id interno de personal filtrado a un padre,
contradice la intención explícita del propio código)**

- **Archivo · línea**: `backend/app/schemas/training_session.py`, clase
  `TrainingSessionReadParent` (antes declaraba `created_by_user_id: int`
  sin excluirlo); `backend/app/routers/training_sessions.py`, función
  `_session_to_read_parent` (el `exclude={...}` del `model_dump` no incluía
  `created_by_user_id`).
- **Qué exponía**: el id numérico interno (`users.id`) del entrenador que
  creó la sesión, en toda respuesta de sesión a un padre
  (`GET /api/training-sessions` y `GET /api/training-sessions/{id}` con rol
  `parent`) — el mismo dato que la propia función ya redactaba para
  `coaches`/`has_active_coach` con el comentario "la familia nunca ve qué
  entrenador dirige la sesión en pantalla" (FR-032/§3.1). Es un id sin
  resolver, no un nombre, así que el riesgo real es bajo — no encontré
  ningún endpoint accesible a un padre que resuelva `user_id → nombre` de
  personal — pero viola la letra de FR-032/§3.1 y el punto 2 del checklist.
- **Corrección**: se quitó `created_by_user_id` de
  `TrainingSessionReadParent` y se agregó a la lista `exclude` del
  `model_dump` en `_session_to_read_parent`, siguiendo el mismo patrón ya
  usado para `coaches`/`has_active_coach`.
- **Verificación**: cambio validado offline (sin MySQL) construyendo el
  schema Pydantic directamente con datos sintéticos y confirmando que
  `created_by_user_id` ya no es un atributo del modelo resultante. No
  encontré ningún test que fijara el valor anterior (`grep
  created_by_user_id` sobre los tests del router no arrojó ninguna
  aserción sobre ese campo en la rama padre), así que no se rompió
  ningún contrato de test existente por lo que pude verificar
  estáticamente — **no verificable aquí** contra la suite completa de
  integración (requiere MySQL).
- **Nota de deuda menor, no corregida**: `frontend/src/types/
  trainingSession.types.ts` sigue tipando `created_by_user_id: number`
  como obligatorio en la interfaz compartida de sesión (no hay un tipo
  `TrainingSessionParent` separado en el frontend). El backend ya no lo
  envía para el padre, así que el campo llegará `undefined` en tiempo de
  ejecución pese al tipo; no es una fuga de datos (el backend es quien
  manda), pero el tipo miente. No lo toqué por quedar fuera de "cambio
  pequeño y local" con confianza suficiente sin poder correr `tsc`/vitest
  aquí; queda para quien retome T091 con el frontend disponible.

---

## 4. Hallazgos no corregidos (fuera de los archivos permitidos o de mayor alcance)

Ninguno. No encontré defectos en `race_analysis.py`, `race_imports.py`,
`permissions.py`, `budget_guard.py` ni `AIHealthPage.tsx` (los archivos
excluidos de corrección directa en este encargo) — de hecho esos archivos
contienen, en este mismo diff, la corrección documentada del hallazgo H3
(commit `8ca2870`, "un entrenador ya no alcanza a menores de otro club al
lanzar o listar análisis"), que revisé y luce coherente con el punto 7 del
checklist.

El único hallazgo con alcance mayor al de "cambio pequeño y local" es el
incidental de `rsvp_by_user_id` en `app/routers/calendar.py` (§2.2) — no lo
corregí porque es pre-existente en `main` y por tanto fuera del alcance de
esta auditoría ("el diff de la feature 041"), no porque el archivo esté
vedado.

---

## 5. Veredicto de cierre

**APROBADO para publicación desde el punto de vista de privacidad**, con
una corrección aplicada en esta misma corrida (hallazgo A) y una salvedad
importante: **ningún punto de este checklist se verificó contra una base de
datos real** — la corrida ocurrió sin MySQL disponible, así que la
cobertura es 100% lectura de código + un test unitario offline puntual.
Los ~150 archivos de test nuevos de esta feature (`test_audit_*`,
`test_coach_activity.py`, `test_session_coaches.py`,
`test_training_session_router.py`, etc.) están escritos exactamente para
cubrir estos siete puntos con aserciones automáticas, pero no pude
ejecutarlos aquí. Antes de un release a producción, alguien con acceso a
`TEST_DATABASE_URL` (o al stack Docker) debe correr al menos:

```
pytest tests/test_audit_privacy.py tests/test_coach_activity.py \
       tests/test_session_coaches.py backend/tests/test_training_session_router.py \
       -m mysql
```

y confirmar que los tests de privacidad de esos archivos (varios llevan
"privacy"/"privacidad" en el nombre) siguen en verde con el cambio del
hallazgo A aplicado.
