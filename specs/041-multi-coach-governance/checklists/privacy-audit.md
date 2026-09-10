# Auditoría de privacidad — feature 041 (multi-coach governance)

**Tarea**: T091 (`specs/041-multi-coach-governance/tasks.md:240`) · **Rama**: `feat/041-multi-coach-governance`
**Fecha**: 2026-09-10 · **Alcance**: la feature completa (backend, plantillas, CLI, workflow, fixtures)
**Marco**: Ley 1581 de 2012 y Ley 1098 de 2006; regla dura del proyecto en `CLAUDE.md` (raíz).

Esta auditoría es de **solo lectura**: no se modificó ni una línea de código ni de pruebas. Los defectos
se reportan con archivo y línea, sin corregirse. **Ningún valor real de un menor aparece en este
documento** — cuando un hallazgo depende de un dato concreto, se cita la ubicación, nunca el valor.

---

## 1. Condiciones de la revisión

- Rama limpia al iniciar (último commit `ef904a8`).
- Durante la revisión, dos archivos ajenos a esta tarea estuvieron en edición por otro agente
  (`backend/app/services/race/group_launch.py`, `backend/app/routers/race_analysis.py`); en un
  momento `group_launch.py:461` tuvo un `SyntaxError` que impidió importar `app.main` y por tanto
  correr la suite. Se resolvió solo y las pruebas se ejecutaron después. **No es un hallazgo de
  privacidad**, se deja anotado porque afecta la reproducibilidad de la corrida.
- No hay MySQL ni Docker en el entorno: la lane `-m mysql`, los Playwright y cualquier verificación
  contra la base real quedan fuera de alcance (ver §5, "no verificable acá").

### Lo que se verificó **ejecutando**

| # | Comando / prueba | Resultado |
|---|---|---|
| E1 | `pytest -q tests/test_audit_privacy.py tests/test_audit_append_only.py tests/test_audit_coverage.py tests/test_audit_actors.py tests/test_audit_automated_actors.py tests/test_audit_athletes.py tests/test_audit_parent_links.py tests/test_audit_profile_auth.py tests/test_audit_race_analysis.py tests/test_audit_race_results.py tests/test_audit_reports_newsletters.py tests/test_retention.py tests/test_coach_activity.py tests/test_logging_config.py tests/test_newsletter_privacy.py tests/test_password_reset_privacy.py tests/test_profile_privacy.py tests/test_training_session_privacy.py tests/test_monthly_report_privacy.py tests/test_ai_explanation_audit.py` | **317 pasan, 3 saltadas** |
| E2 | Barrido AST propio sobre `backend/app/**` y `backend/scripts/**`: extrae de cada llamada a `record_audit` las claves y expresiones de `meta`, `diff` y `changed_fields` | 131 sitios de llamada; inventario completo en §3, punto 2 |
| E3 | Sonda propia (en scratchpad, fuera del repo) que ejerce una ruta mutante real (`DELETE /api/athletes/{id}` con `reason_code`) sobre el motor de `test_audit_privacy.py` y pasa la fila resultante por el escáner del proyecto | 1 fila producida, **0 violaciones**; contenido: solo nombres de columna + `reason_code` |
| E4 | Sonda propia sobre `record_audit` con texto libre bajo una clave permitida de `meta_json` y con una cadena arbitraria en `changed_fields` | **Ambas se persisten sin filtro** (hallazgo M-2 y L-1) |
| E5 | Reproducción aislada de los dos detectores del escáner (`_ISO_DATE_RE`, `_MEASUREMENT_LIKE_RE`) sobre un `diff_json` con una fecha de nacimiento sembrada | El detector de fechas **nunca dispara** (hallazgo A-2) |

### Lo que se verificó **leyendo**

Código de `backend/app/services/audit.py` (1791 líneas, completo), `request_context.py`, `retention.py`,
`coach_activity.py`, `race/ai/budget_guard.py`, `routers/audit.py`, los sitios de `record_audit` en los
routers de mayor riesgo (`ai.py`, `parent_athletes.py`, `auth.py`, `profile.py`, `reports.py`,
`parent_newsletters.py`, `intervals.py`, `athlete_monthly_newsletters.py`, `race_analysis.py`), los
esquemas de padre (`parent_newsletter.py`, `calendar.py`, `training_session.py`), la proyección
`to_parent_dto`, las plantillas de `backend/templates/email/**` y `backend/templates/documents/**`,
`backend/main.py` (logging y middleware), `backend/scripts/retention_audit_log.py`,
`.github/workflows/audit-retention.yml`, `backend/scripts/seed.py`, `backend/tests/fixtures/**` y los
propios módulos de prueba de privacidad.

---

## 2. Veredicto por punto

| # | Punto | Veredicto |
|---|---|---|
| 1 | La allow-list es de verdad la frontera | **Cumple con reserva** — la frontera de `diff_json` es sólida; la de `meta_json` cubre las claves pero **no los valores** (M-2) |
| 2 | Las filas realmente escritas | **Cumple** |
| 3 | Los esquemas de familia no llevan atribución | **No cumple** — boletín y calendario sí; **sesiones no** (M-1) |
| 4 | El PDF y el correo de familia no muestran nombre de entrenador | **Cumple** (con la precisión del §4) |
| 5 | Logs con `request_id`, sin cuerpos ni PII | **Cumple** |
| 6 | Exportaciones auditadas por tipo + `athlete_id` | **Cumple** (cobertura de pruebas parcial) |
| 7 | Fixtures y semillas versionadas sintéticas | **No cumple parcialmente** (M-3) |
| 8 | Purga de retención: solo conteos, secreto por nombre | **Cumple** |
| 9 | Gasto por entrenador e informe de actividad | **Cumple con reserva** (L-2) |

**Estado global: REQUIERE CORRECCIÓN** — 2 hallazgos altos (ambos de *cobertura de pruebas*, no de
comportamiento en producción) y 3 medios. Ninguna fuga confirmada de dato de un menor en el código
que hoy corre.

---

## 3. Detalle por punto

### Punto 1 — La allow-list como frontera

**`VALUE_ALLOWLIST`** (`backend/app/services/audit.py:266-314`) sólo admite estados de enum, banderas,
fechas de evento (nunca de nacimiento), llaves foráneas y contadores. Se revisó campo por campo: no hay
ninguna clave por la que pueda colarse un valor de un menor. El único valor JSON admitido es
`athlete_monthly_newsletter.hidden_blocks`, y son claves de bloque estáticas (`app/services/audit.py:298-304`),
lo cual la prueba `tests/test_audit_privacy.py:253` amarra contra el conjunto real de bloques ocultables.

El filtrado ocurre dentro de `record_audit` (`app/services/audit.py:656-665`): lo que no está en la
allow-list del `entity_type` **no llega a `diff_json`**, sin importar lo que pase el llamador. Verificado
por E3: la fila real de archivo de deportista trae `changed_fields = ['deleted_at', 'deleted_by_user_id',
'deleted_reason_code']` y `diff_json` con únicamente `deleted_reason_code`.

Hay además una **segunda frontera en lectura** (`app/routers/audit.py:180-219`), que vuelve a pasar
`diff_json` y `meta_json` por las mismas listas y registra en WARNING los campos descartados citando
sólo el **nombre** del campo, jamás el valor. Buena práctica; conviene conservarla.

**`record_audit` es el único constructor de filas.** Confirmado: el único `AuditLog(` de toda la
aplicación está en `app/services/audit.py:685`; no hay ningún `INSERT INTO audit_log` en SQL crudo.
`app/services/retention.py:204-219` también escribe su fila de purga a través de `record_audit`.

**Reserva (→ M-2)**: `META_ALLOWLIST` (`app/services/audit.py:356-388`) valida la **clave** y, para `job`,
también el valor contra `AUDIT_JOB_SLUGS`. Para las otras 27 claves, el valor entra sin ninguna
validación (`app/services/audit.py:667-680`). El comentario de `app/services/audit.py:350-355` afirma que
"no hay clave de meta de texto libre"; hay exactamente una, `step_id`.

### Punto 2 — Las filas realmente escritas

Barrido AST completo (E2) de los **131** sitios de `record_audit`. Inventario de lo que viaja:

- **`changed_fields`**: 58 nombres de columna literales distintos (`club_id`, `status`, `hashed_password`,
  `bmi`, `weight_percentile`, `coach_note`, `ai_narrative`…). Son **nombres**, nunca valores; los que
  corresponden a datos sensibles quedan fuera de `VALUE_ALLOWLIST`, así que el valor no acompaña al
  nombre. Las 20 expresiones no literales son todas `sorted(update_data.keys())`,
  `compute_changed_fields(...)` o variables construidas con esas dos: claves de columna en todos los casos.
- **`diff`**: 16 expresiones no triviales, todas tuplas de enums de estado o de `reason_code`.
- **`meta`**: 24 claves usadas, todas con valores de tipo entero, booleano, enum cerrado, id o fecha de
  evento. Las tres expresiones dinámicas (`audit_meta` en `routers/athlete_monthly_newsletters.py:718,746`,
  `_hitl_audit_meta` en `routers/race_analysis.py:1111`, `meta` en `services/retention.py:217`) se
  inspeccionaron una por una y resuelven a `{"athlete_count": int}`, `{step_id, previous_status, has_edits}`
  y `{job, removed_count, cutoff}` respectivamente.

Zonas de mayor riesgo revisadas una por una, como pedía el encargo:

- **Explicaciones de IA sobre un menor** (`app/routers/ai.py:211-259`): la fila lleva `athlete_id`,
  `club_id`, `changed_fields` con nombres de columna y `meta={"related_entity_id": <id de la medición>}`.
  **El texto de la explicación no viaja a ninguna parte de la fila.** Los logs del módulo sólo emiten
  `type(exc).__name__` (`app/routers/ai.py:521,527,533,696,702,708`).
- **Vínculos familiares** (`app/routers/parent_athletes.py:172,349,394,411,555` y
  `app/routers/auth.py:284,307,319`): `meta={"parent_user_id": <id>}` y `changed_fields` con nombres.
  Ni el correo del acudiente ni el nombre del menor entran a la fila. El correo sí se usa en el
  `NotificationRequest` (`parent_athletes.py:426-433`), que es el canal de envío, no la bitácora.
- **Perfil y restablecimiento de contraseña** (`app/routers/profile.py:91,120,210`;
  `app/routers/auth.py:426`): `changed_fields=["hashed_password"]` / `["email"]` — **el nombre de la
  columna, nunca su contenido, ni hash ni token**. En `PATCH /profile/basic` el `diff` se calcula contra
  `VALUE_ALLOWLIST[user]` (`app/routers/profile.py:86-90`), que no incluye `first_name`, `last_name` ni
  `phone`, así que `diff_json` queda vacío — el docstring de `profile.py:67-80` lo dice y el código lo
  cumple. La ruta `POST /auth/password-reset/request` está exenta a propósito, con la razón correcta
  (evitar un oráculo de enumeración de cuentas, `app/services/audit.py:822-825`).
- **Nota del entrenador en la bitácora familiar**: se auditan `coach_note`, `coach_note_author_id` y
  `coach_note_updated_at` como **nombres** en `changed_fields`; `athlete_monthly_newsletter` no los tiene
  en `VALUE_ALLOWLIST`, así que el texto de la nota nunca llega a `diff_json`.
- **Exportaciones de documentos**: ver punto 6.

### Punto 3 — Esquemas de familia sin atribución

- **Boletín — cumple.** `ParentNewsletterListItem` / `ParentNewsletterOut`
  (`backend/app/schemas/parent_newsletter.py`) no declaran ningún campo de autoría. El `stage_log` se
  construye siempre con `to_parent_dto` (`app/services/training/stage_log.py:413-437`), un allow-list
  explícito de 17 claves (`:382-400`) más un allow-list anidado para `analyst_reading` (`:403-407`);
  `coach_note_author` no está en ninguno de los dos. La superficie coach/admin
  (`app/schemas/athlete_newsletter.py:325-346`) sí lo expone, con el comentario de FR-012 en `:229-235`.
- **Calendario — cumple.** `EventReadParent` (`app/schemas/calendar.py:328-346`) omite
  `created_by_user_id` y las audiencias internas; `_serialize_event`
  (`app/routers/calendar.py:200-204`) selecciona el esquema por rol y `_to_list_item`
  (`app/routers/calendar.py:183-186`) además le quita la `description` al padre. Existe prueba dedicada:
  `tests/test_calendar_models.py:530`.
- **Sesiones — NO CUMPLE.** Ver hallazgo **M-1**.

Complemento correcto que sí está: `GET /api/training-sessions` rechaza con **403** el filtro
`coach_user_id` cuando quien pregunta es un padre, en vez de ignorarlo en silencio
(`app/routers/training_sessions.py:426-435`, FR-032).

### Punto 4 — PDF y correo de familia sin nombre de entrenador

**Cumple, y con una precisión importante** que conviene dejar escrita para que nadie la "corrija" mal
más adelante: la regla de "sin nombre de entrenador" es la de **FR-012** y aplica a la **bitácora de
etapa** (boletín familiar), no a todo correo a la familia.

- Boletín por correo: `backend/templates/email/athlete_stage_log.html:211-221` cierra con la voz
  institucional del club y documenta explícitamente que `coach_note_author` es exclusivo de coach/admin.
  El contexto que arma el despachador son sólo `stage_log` (ya proyectado) y `club_name`
  (`app/services/notification/newsletter_dispatcher.py:313,325`).
- Boletín en PDF: `backend/templates/documents/pdf/athlete_stage_log.html:256-259` incluye la
  instrucción de no agregar `coach_note_author` a la plantilla. El contexto que se le pasa
  (`app/services/notification/athlete_newsletter_pdf.py:141-153`) no contiene ningún campo de personal.
- Correos de **sesión** (`training_session_invite/updated/cancelled`, `.html` y `.txt`): sí llevan
  `acting_coach_name` y `coaches_text`. Es **intencional** y está contratado en
  `contracts/session-coaches.md:270-352`, y el propio serializador de padre lo dice al excluir `coaches`
  de la pantalla: *"la familia nunca ve qué entrenador dirige la sesión en pantalla; los nombres van
  únicamente en el email"* (`app/routers/training_sessions.py:190-192`). Son nombres de **personal
  adulto**, no datos de un menor: no hay conflicto con la Ley 1581.

Cobertura de pruebas de este punto: buena — `tests/routers/test_newsletter_coach_note_author.py:350,379,
393,401,407,424,455,483` cubre la ausencia del autor en la superficie de padre, en el DTO, en el modelo,
en el PDF, en el cuerpo del correo y en las plantillas.

### Punto 5 — Logs

**Cumple.**

- `dictConfig` con filtro `RequestIdLogFilter` para todos los loggers `app.*`
  (`backend/app/main.py:23-77`); el formato incluye `[%(request_id)s]`. `propagate: True` está
  justificado en `:60-70` (sin él, `caplog` quedaba vacío y varias pruebas de privacidad no verificaban
  nada). Prueba: `tests/test_logging_config.py:15,33,41` (pasa, E1).
- `RequestIdMiddleware` (`app/services/request_context.py:63-95`) es ASGI puro (no
  `BaseHTTPMiddleware`, para no re-envolver las respuestas binarias de WeasyPrint) y se monta como el
  más externo (`app/main.py:135`). Acepta un `X-Request-Id` entrante **sólo** en los dos endpoints de
  máquina y sólo si calza el hex de 32 (`request_context.py:98-120`): un navegador no puede elegir su
  propio id de correlación.
- El manejador global de excepciones registra `method`, `path` y `type(exc).__name__` — **nunca el
  cuerpo de la petición** (`app/main.py:140-146`).
- `record_audit` registra sólo conteos y valores de enum (`app/services/audit.py:704-727`); el WARNING
  `audit_reserve_request_id_minted` no lleva `entity_id` ni identidad del actor.
- `app/routers/audit.py:189,212` registra el **nombre** del campo descartado, no su valor.
- Barrido de todos los `logger.{info,warning,error,debug,exception}` de `backend/app/**` buscando
  interpolación de `first_name`/`last_name`/`.email`/`birth`/`body`/`payload`: 4 coincidencias, las 4
  inocuas — `app/services/race/agents/analyst.py:926` registra un **conteo** de nombres escrubeados y
  `app/routers/race_analysis.py:1506,1512,1525` un `session_id`.
- No hay ningún `print(` ejecutable en `backend/app/**` (el único match, `services/race/ingestor.py:154`,
  está dentro de un docstring).

### Punto 6 — Exportaciones

**Cumple.** Las ocho exportaciones/envíos se auditan contra el registro del que sale el documento, con
`meta={"document_kind": <AuditDocumentKind>}` y `athlete_id`, y **nada del contenido**:

| Ruta | Sitio | `meta` |
|---|---|---|
| `GET …/report/pdf` | `app/routers/reports.py:134-143` | `growth_pdf` |
| `GET …/clearance/docx` | `app/routers/reports.py:204-213` | `clearance_docx` |
| `POST …/report/email` | `app/routers/reports.py:315-324` | `growth_pdf` |
| `GET …/monthly-reports/…/pdf` · `/docx` | `app/routers/monthly_reports.py:622,779` | `monthly_report_pdf` / `_docx` |
| `GET …/newsletters/{id}/pdf` (coach) | `app/routers/athlete_monthly_newsletters.py:1057` | `newsletter_pdf` |
| `GET /api/parents/me/…/newsletters/{id}/pdf` | `app/routers/parent_newsletters.py:248-257` | `newsletter_pdf` |
| `GET …/instructivo` | `app/routers/intervals.py:1220-1228` | `session_instructivo_pdf` |
| `GET …/runs/{id}/pdf` | `app/routers/race_analysis.py:1362` | `race_analysis_pdf` |
| envío del boletín | `app/services/notification/newsletter_dispatcher.py:437-452` | `newsletter_email` + `recipients_count` |

`AuditDocumentKind` es un enum cerrado (`app/services/audit.py:103-111`) y no existe clave de meta
`filename` ni `storage_url` (`META_ALLOWLIST`, `:356-388`). El nombre de archivo generado nunca sale del
`Content-Disposition`.

Reserva de **cobertura**: sólo `newsletter_email` tiene una aserción sobre el contenido de la fila
(`tests/test_audit_reports_newsletters.py:604,629`). `clearance_docx` y `session_instructivo_pdf` no
aparecen mencionados en ninguna prueba.

### Punto 7 — Fixtures y semillas versionadas

- `backend/tests/fixtures/two_coaches.py` — **impecable**: declaración explícita en `:15` ("Ningún
  nombre corresponde a una persona real") y todos los nombres marcados (`:62`, `:126-155`, `:177-179`).
- `backend/tests/fixtures/race_groups.py:150-178` — nombres marcados como ficticios.
- `backend/tests/fixtures/race_history_fixtures.py:115-118` — **NO CUMPLE**, ver hallazgo **M-3**.
- `backend/scripts/seed.py` — las mediciones antropométricas llevan la declaración correcta
  (`:37-39`: "Valores inventados y plausibles… no corresponden a ninguna persona"); el bloque de
  identidad del deportista demo (`:204-212`) no la lleva. Ver hallazgo informativo I-1.
- `frontend/e2e/helpers/session.ts:17,23` y `frontend/e2e/helpers/demo-athlete.ts:20-21` — la identidad
  `coach2` que agregó T004 es sintética y está anotada como tal. Correcto.

### Punto 8 — Purga de retención

**Cumple, y con margen.**

- `app/services/retention.py:24-27` declara la regla y el código la respeta: `preview_purge` y
  `apply_purge` (`:157-175`, `:227-302`) sólo emiten `COUNT(*)` agrupados y un único `DELETE`. **El
  contenido de las filas borradas no se devuelve ni se registra en ningún punto.** La fila de purga lleva
  `{"job", "removed_count", "cutoff"}` (`:198-202`), las tres claves en `META_ALLOWLIST`.
- CLI (`backend/scripts/retention_audit_log.py`): stdout es una sola línea JSON con
  `{candidates, deleted, cutoff}` (`:279-283`, `:307-311`); stderr sólo lleva conteos y desglose por
  `entity_type` y `club_id` (`:264-306`) — **ningún contenido de fila**.
- **Secreto por nombre**: `--database-url` se declara con `envvar="AUDIT_RETENTION_DATABASE_URL"`
  (`:349-357`) y el propio help dice "Nunca se imprime". `_describe_database` (`:216-221`) emite
  únicamente `host/base`, y `_scrub` (`:106-110`, aplicado en `:387`) tapa la contraseña si una
  excepción de terceros llegara a citarla. En el workflow
  (`.github/workflows/audit-retention.yml:63-65,104`) el secreto viaja como
  `${{ secrets.AUDIT_RETENTION_DATABASE_URL }}` en `env:`, nunca interpolado en un `echo`. El job
  `apply` exige `workflow_dispatch` + `confirm=true` + `environment: production`, con una segunda
  barrera en el shell (`:107-118`).

### Punto 9 — Gasto por entrenador e informe de actividad

- **`coach_activity.py` — cumple.** El payload son nombres de personal adulto y enteros
  (`app/schemas/coach_activity.py:44-123`: ningún `athlete_id`, ningún campo de texto libre). El
  conjunto de filas se restringe a `ClubRole.coach` (`app/services/coach_activity.py:253`) sobre miembros
  del club (`:188-201`), así que una cuenta de deportista —que también vive en `users` y en
  `club_members` con `ClubRole.athlete`, ver `scripts/seed.py:243-250`— **no puede aparecer** como fila
  del informe. Los deportistas sólo participan como criterio de alcance por club
  (`app/services/coach_activity.py:356-370`). El único log del router emite `club_id` y las fechas del
  período (`app/routers/audit.py:378-383`).
- **`budget_guard.py` — cumple con reserva.** `UserSpend` expone `user_id`, `display_name`,
  `cost_usd_total` y `run_count` (`app/services/race/ai/budget_guard.py:173-190`), y el cubo sin
  atribuir se etiqueta `"Sin atribuir"`. El log de sobrecosto (`:326`, `:383`) no lleva identidades.
  La reserva es la resolución de nombres: ver hallazgo **L-2**.

---

## 4. Hallazgos, por severidad

### [ALTO] A-1 · `backend/tests/test_audit_privacy.py:498-530` — la parte que debía revisar las filas reales no revisa ninguna

`test_audit_log_rows_produced_by_the_real_app_are_clean` es hoy una prueba vacía. Emite **un GET**
(`/api/athletes`, una lectura que por diseño no escribe bitácora, `:511-513`), afirma
`assert len(rows) == 0` (`:522`) y a continuación corre el escáner sobre una lista vacía (`:529`). El
docstring lo explicaba honestamente en su momento —"as of this writing no router calls record_audit
yet"— pero eso dejó de ser cierto: hoy hay ~100 rutas instrumentadas y **ninguna fila producida por un
router se pasa jamás por `scan_rows_for_privacy_violations`**.

Se agrava con un segundo detalle: el `_override_current_user` de la fábrica de clientes devuelve
`club_memberships=[]` (`:142`), así que aunque la prueba intentara una escritura como `coach`
recibiría 403. Verificado ejecutando (E3): con actor `admin` y `DELETE /api/athletes/{id}` la aplicación
sí produce 1 fila —limpia— y la afirmación `len(rows) == 0` **fallaría**.

> **Recomendación**: reemplazar el GET por un pequeño lote de escrituras reales (una por familia de
> entidad: atleta, sesión, boletín, vínculo familiar, exportación), quitar el ancla `== 0` y pasar esas
> filas por el escáner con `forbidden_substrings` poblado desde el escenario. La infraestructura ya
> existe; falta usarla. Corregir también el `club_memberships=[]` de la fábrica, o la prueba no podrá
> ejercer una escritura de entrenador.

### [ALTO] A-2 · `backend/tests/test_audit_privacy.py:205` y `:344` — el detector de fechas de nacimiento no puede dispararse nunca

`_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")` se usa con `.search()` (`:344`) sobre un blob que
siempre empieza por `{` o por `None` (`:341`). Con el ancla `^` y sin `re.MULTILINE`, `search` sólo
puede coincidir en la posición 0: el detector es **código muerto**.

Verificado ejecutando (E5): con una fecha de nacimiento sembrada dentro de `diff_json`, el detector
devuelve `False`; el de medidas (`_MEASUREMENT_LIKE_RE`, `:206`, sin ancla) tampoco coincide con un
valor entero o con una fecha. En consecuencia, la única red que hoy atrapa un **valor** prohibido es la
tupla `forbidden_substrings` que pasa el llamador — y A-1 muestra que la parte que revisa filas reales
no pasa ninguna.

Combinados, A-1 y A-2 significan que la auditoría automática de `audit_log` verifica hoy la **forma**
de las filas (claves permitidas, `club_id` no nulo) pero **no su contenido**.

> **Recomendación**: quitar el ancla `^` (o recorrer valor por valor en vez de sobre un blob
> serializado) y exceptuar explícitamente las claves con fecha que la allow-list sí admite a propósito
> (`club_join_date`, `scheduled_date`, `start_at`, `end_at`, `evaluation_date`, `event_date`, `cutoff`,
> `archived_at`, `deleted_at`), para que el detector distinga una fecha de evento de una de nacimiento
> en vez de quedar desactivado por no saber distinguirlas.

### [MEDIO] M-1 · `backend/app/schemas/training_session.py:217` — el esquema de sesión para padres conserva `created_by_user_id`

`TrainingSessionReadParent` (`:212-238`) declara `created_by_user_id: int`: un campo de atribución de
personal que llega a la familia en cada lectura de sesión. Es inconsistente con dos decisiones del
propio proyecto:

- el gemelo de calendario lo elimina a propósito y lo documenta (`app/schemas/calendar.py:328-329`),
  con prueba dedicada (`tests/test_calendar_models.py:530`);
- el serializador de padre excluye explícitamente `coaches` y `has_active_coach` citando FR-032
  (`app/routers/training_sessions.py:183-195`), pero **no** excluye `created_by_user_id`, que se copia
  desde `TrainingSessionRead` en el `model_dump` de `:183`.

Afecta a `GET /api/training-sessions` (`:294`) y a `GET /api/training-sessions/{id}` (`:484`). No es
dato de un menor —es el id numérico de un adulto— pero es exactamente el tipo de campo que el criterio
3 de T091 prohíbe en una superficie de familia, y contradice FR-032 ("qué entrenador dirige una sesión
es información interna de gestión") por una vía distinta a la que ya se cerró.

> **Recomendación**: sacar `created_by_user_id` de `TrainingSessionReadParent` y agregarlo al `exclude`
> de `_session_to_read_parent`; replicar `tests/test_calendar_models.py:530` para el esquema de sesión.
> No corregido aquí por instrucción explícita.

### [MEDIO] M-2 · `backend/app/routers/race_analysis.py:1008` y `:1096-1097` — `meta_json.step_id` es texto libre sin validar

`step_id` entra como segmento de ruta tipado sólo `str` (`:1008`), sin `Literal`, sin patrón y sin
verificarse contra los pasos reales del grafo, y se copia verbatim a `meta_json`
(`:1096-1097` → `record_audit` en `:1102-1112`). `META_ALLOWLIST` valida la **clave** pero no el
**valor** (`app/services/audit.py:667-680`); el único valor de meta que sí se valida es `job`
(`:672-679`). El lector tampoco lo filtra: `_filter_meta` descarta claves desconocidas y devuelve el
valor intacto (`app/routers/audit.py:201-219`).

Verificado ejecutando (E4): `record_audit` persistió sin objeción una cadena arbitraria de ~200
caracteres bajo `meta_json.step_id`.

Es la única excepción real a la afirmación de `app/services/audit.py:350-355` ("An unbounded dict is a
PII channel — there is no free-text meta key"). Hoy quien puede escribirla es un coach o admin del
club, así que el riesgo práctico es bajo; el problema es que la frontera declarada no es la frontera
efectiva, y la bitácora es precisamente el sitio donde eso importa.

> **Recomendación**: tipar `step_id` contra el catálogo cerrado de pasos del grafo (o al menos un
> `^[a-z_]{3,40}$` como el que ya existe para `job` en `app/services/audit.py:546`), y extender la
> validación de valor de `record_audit` a las claves de meta que hoy admiten cadenas.

### [MEDIO] M-3 · `backend/tests/fixtures/race_history_fixtures.py:115-118` — fixture de menor con nombre propio completo y sin marca de ficción

`create_athlete` tiene por defecto un nombre y un apellido de persona **sin ninguna marca de ficción**,
junto con una fecha de nacimiento que corresponde a un menor de la franja del club. Está versionado en
git. Contrasta con todos sus pares, que sí marcan: `tests/fixtures/two_coaches.py:15,62`,
`tests/fixtures/race_groups.py:154,176` y el propio `race_history_fixtures.py:267`, que unas líneas más
abajo sí usa la convención "Ficticio". El docstring del módulo (`:1-16`) no declara que los datos sean
sintéticos.

No es un archivo que haya nacido con la feature 041, pero **041 lo usa**: `tests/test_coach_activity.py:71`
(T082) y `tests/test_session_coaches.py:521` importan precisamente ese `create_athlete`, con sus valores
por defecto. Por eso entra en el alcance de T091 punto 7.

No se puede determinar desde el código si corresponde o no a una persona real; la política del proyecto
no exige determinarlo, exige que la semilla sea **evidentemente** ficticia.

> **Recomendación**: cambiar los defaults a la convención "Ficticio/a" ya usada en el resto de
> `tests/fixtures/`, agregar la declaración al docstring del módulo, y correr la suite para confirmar
> que ninguna aserción dependía de esas cadenas. No corregido aquí por instrucción explícita.

### [BAJO] L-1 · `backend/app/services/audit.py:654` — `changed_fields` no tiene catálogo cerrado

`resolved_changed_fields = sorted(set(changed_fields or (diff or {}).keys()))` acepta cualquier cadena.
No hay allow-list de nombres de columna (a diferencia de `meta_json`, cuyas claves sí están cerradas), y
el lector devuelve los nombres desconocidos verbatim porque `AUDIT_FIELD_LABELS.get(field, field)` cae a
la propia cadena (`app/routers/audit.py:244-245`).

Verificado ejecutando (E4): una frase arbitraria se persistió como si fuera un nombre de columna.

Riesgo hoy **residual, no activo**: el barrido AST (E2) confirma que los 131 sitios de llamada pasan
nombres de columna reales. Es un canal abierto para un llamador futuro que confunda nombre con valor.

> **Recomendación**: validar `changed_fields` contra las columnas reales del modelo del `entity_type`
> (que ya son conocibles vía SQLAlchemy) o, como mínimo, contra `AUDIT_FIELD_LABELS` más las columnas
> de `VALUE_ALLOWLIST`, elevando a `AuditContractError` lo que no calce.

### [BAJO] L-2 · `backend/app/services/race/ai/budget_guard.py:208-210` — la resolución de nombres del gasto no filtra por rol

`_QUERY_RESOLVE_NAMES` es `SELECT id, first_name, last_name FROM users WHERE id IN :ids`, sin filtro de
rol ni de club (`:276-292`). El docstring de `UserSpend` afirma que `display_name` es **siempre** staff
adulto (`:179-181`), pero eso depende enteramente de que `agent_runs.requested_by_user_id` /
`athlete_ai_insights.generated_by_user_id` nunca apunten a otra cosa. La tabla `users` contiene también
filas de deportistas (`role=athlete`, `can_login=false`; ver `scripts/seed.py:216-224`), así que una
atribución histórica o corrupta que apunte a una de ellas renderizaría el nombre de un menor en la
superficie de salud de IA (`app/routers/race_analysis.py:1713-1719`).

El módulo hermano sí tiene la guarda equivalente (`app/services/coach_activity.py:253`), lo que hace la
omisión más visible.

> **Recomendación**: agregar `AND role IN ('admin','coach')` a la consulta y devolver el rótulo
> `"Usuario no disponible"` —el que ya existe en `:265-267`— para cualquier id que no resuelva a staff.

### [BAJO] L-3 · `backend/tests/test_audit_append_only.py:51,149` — el escaneo append-only tiene un punto ciego

El escaneo AST recorre sólo `backend/app/**` (`APP_ROOT`, `:51`; `rglob` en `:149`) y detecta
construcciones de SQLAlchemy (`update(AuditLog)`, `delete(AuditLog)`, `session.delete(...)`, mutación de
atributo). Quedan fuera: (a) SQL crudo vía `text("DELETE FROM audit_log …")`, que la heurística no ve, y
(b) todo `backend/scripts/**` y `backend/alembic/**`.

Hoy **no existe ninguna violación**: se verificó por grep que fuera de `app/services/audit.py`,
`app/models/audit_log.py`, `app/routers/audit.py`, `app/services/retention.py` y
`scripts/retention_audit_log.py` no hay ningún módulo que nombre la tabla en una escritura.

> **Recomendación**: agregar un grep de `audit_log` dentro de literales pasados a `text(...)` y extender
> la raíz del escaneo a `backend/scripts/`.

### [INFO] I-1 · `backend/scripts/seed.py:204-212` — el deportista demo no lleva la declaración de ficción

Las constantes antropométricas del mismo archivo sí la llevan (`:37-39`). El bloque de identidad del
deportista (nombre, apellido, fecha de nacimiento) no. La semilla sólo corre con
`APP_ENV=development` (`backend/entrypoint.sh`), así que no llega a producción, pero está versionada y
es lo primero que ve quien monta el stack.

### [INFO] I-2 · `backend/app/services/audit.py:1092` — una ruta sigue marcada como pendiente

`POST /api/race-analysis/imports/{parse_id}/dry-run` es la única entrada de `AUDITED_ROUTES` con el
marcador `_PENDING`. La razón está documentada en detalle (`:1077-1091`): el contrato describe un cambio
de estado que el código no emite, y registrar un `update` sería anotar una escritura que no ocurrió.
**No es un defecto de privacidad** —una lectura no auditada nunca filtra nada—, pero T095 pide cero
exenciones pendientes, así que sigue abierta como decisión de producto.

### [INFO] I-3 · `backend/tests/test_audit_coverage.py:262-289` — el humo dinámico de FR-009 recoge cero casos

`test_audited_route_writes_at_least_one_audit_log_row` está parametrizado sobre entradas `Audited` que
declaren un `request_factory`, y ninguna lo declara. La propia prueba lo dice sin adornos (`:280-289`) y
explica que antes recogía 81 rutas y las saltaba una a una, "lo que hacía parecer que la compuerta
existía". La mitad estática (`:231-256`, recorrido del grafo de llamadas hasta `record_audit`) sí
funciona y sí pasa. Se anota aquí porque es la otra mitad del mismo hueco que A-1: hoy nadie comprueba
en ejecución **el contenido** de la fila de cada ruta.

---

## 5. Brechas que quedan abiertas

**Por corregir (bloquean el cierre de T091 con "aprobado")**

1. A-1 y A-2 — la revisión automática de privacidad de `audit_log` no inspecciona ninguna fila real ni
   ningún valor. Es la brecha más importante de todo el informe: el código está bien, la red que debía
   probarlo no está tendida.
2. M-1 — `created_by_user_id` en el esquema de sesión de padres.
3. M-2 — `step_id` como texto libre en `meta_json`.
4. M-3 — fixture de menor sin marca de ficción, usada por pruebas de esta misma feature.

**No verificable en este entorno, y por qué**

- **Lane de MySQL** (`pytest -m mysql`, `backend/tests/test_audit_mysql.py`): no hay MySQL ni Docker.
  Quedan sin ejercer los índices, el `COLLATE` real de `entity_type`/`request_id` y el comportamiento
  del `DELETE` de la purga sobre el motor de producción.
- **Playwright** (T092, pendiente): las cinco especificaciones de e2e no existen todavía, así que
  ninguna de las superficies de familia se verificó en un navegador.
- **Logs de producción**: que `X-Request-Id` aparezca en los logs de Render es T097, posterior al
  despliegue. Acá sólo se verificó la configuración y una prueba unitaria de propagación.
- **Contenido real de `audit_log` en producción**: la tabla no es alcanzable desde este entorno. Esta
  auditoría verifica el **camino de escritura**, no lo ya escrito. La primera corrida en simulación de
  `scripts/retention_audit_log.py` contra producción (T097) es la primera oportunidad de contar filas
  reales; conviene aprovecharla para exportar sólo el desglose por `entity_type` que ya emite la CLI.
- **Superficies de frontend** (`localStorage`, parámetros de URL compartibles): fuera del enunciado de
  T091, que acota a esquemas y respuestas del backend. No se revisaron.

**Deuda de cobertura reconocida, no bloqueante**

- Sin aserción sobre el contenido de las filas de exportación de `clearance_docx` y
  `session_instructivo_pdf` (punto 6).
- Sin prueba que amarre la ausencia de campos de atribución en el esquema de sesión de padres — el
  hueco que dejó pasar M-1 (existe el equivalente para calendario, `tests/test_calendar_models.py:530`).
- Sin prueba de que la CLI de retención no vuelque contenido de filas a stdout/stderr; hoy se sostiene
  por lectura del código y por `tests/test_retention.py`, que verifica conteos y códigos de salida.

---

## Resumen

```
AUDITORÍA DE PRIVACIDAD — feature 041

Archivos revisados: 47 (backend/app, backend/templates, backend/scripts,
                        backend/tests/fixtures, .github/workflows, frontend/e2e/helpers)
Sitios de record_audit inventariados por AST: 131
Pruebas ejecutadas: 317 pasan, 3 saltadas

Hallazgos: 2 altos, 3 medios, 3 bajos, 3 informativos

[ALTO]  tests/test_audit_privacy.py:498-530 — la revisión de filas reales no revisa ninguna
[ALTO]  tests/test_audit_privacy.py:205,344 — el detector de fechas de nacimiento no dispara nunca
[MEDIO] app/schemas/training_session.py:217 — atribución de personal en el esquema de padres
[MEDIO] app/routers/race_analysis.py:1008,1096 — meta_json.step_id es texto libre sin validar
[MEDIO] tests/fixtures/race_history_fixtures.py:115-118 — fixture de menor sin marca de ficción
[BAJO]  app/services/audit.py:654 — changed_fields sin catálogo cerrado
[BAJO]  app/services/race/ai/budget_guard.py:208-210 — resolución de nombres sin filtro de rol
[BAJO]  tests/test_audit_append_only.py:51,149 — punto ciego del escaneo append-only

Fugas confirmadas de datos de un menor: NINGUNA

Estado: REQUIERE CORRECCIÓN
```
