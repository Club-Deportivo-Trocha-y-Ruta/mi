# Auditoría de privacidad — Feature 044 (histórico Copa Valle 2024-2025)

## §1 — Candado de progresión de terceros (T036, US3, FR-012…FR-015)

**Alcance de esta sección**: revisión de T034 (`third_party_guard.py`) y T035 (aplicación del candado) contra FR-012…FR-015. Auditor: `data-privacy-guard`. Fecha: 2026-09-18. Rama: `feat/044-race-history-backfill`.

**Archivos revisados**: `backend/app/services/race/third_party_guard.py`, `backend/app/services/race/analytics.py`, `backend/app/services/race/ai/nodes/compute_metrics.py`, `backend/app/services/race/ai/retry.py`, `backend/app/services/race/ai/events.py`, `backend/app/main.py`, `backend/app/services/race/competitor_linking.py`, `backend/app/services/race/field_metrics.py`, `backend/app/services/training/newsletter_builder.py`, `backend/app/routers/race_analysis.py`, `backend/app/routers/race_competitors.py`, `backend/app/routers/race_events.py`, `backend/app/models/race_competitor.py`, `backend/alembic/versions/8efe1618cb83_race_history_backfill.py`, `backend/tests/privacy/test_third_party_lock.py`.

**Tests corridos yo mismo** (no me fío del reporte de T034/T035):

```
tests/privacy/test_third_party_lock.py                          39 passed
tests/services/race/ai/nodes/test_compute_metrics.py            (incluidos en los 39)
tests/routers/test_race_analysis_privacy.py
tests/services/race/ai/test_graph.py
tests/services/race/ai/test_graph_championship.py
tests/services/race/test_analytics.py
tests/services/race/ai/test_race_ai_privacy_invariants.py       62 passed
tests/services/race + tests/routers + tests/privacy + tests/models (suite completa)
                                                                  2536 passed, 16 failed
```

Los 16 fallos son preexistentes y ajenos al candado: 10 son `tests/routers/test_race_imports_integrity.py` (US1, T014) que fallan porque T018/T019 todavía no están implementadas — el propio test lo declara (`"T019 pendiente"`); 3 son de `test_schemas.py` / `test_invariants_v2.py` / `test_prompt_v3_blocks.py`, sobre validación de edad y prompts del atleta adulto, sin relación con `competitor_id` ni con el candado. No hay ninguna falla en los archivos que T034/T035 tocaron. **Regresión (punto 6): confirmada sin hallazgos — nada que antes estuviera cerrado se abrió.**

---

### 1. Cobertura real — ¿cubre TODA vía que devuelva datos de más de una válida?

El barrido estructural de `test_third_party_lock.py` (`_discover_competitor_id_callables`) sólo indexa **callables públicos de primer nivel definidos en `app.services.race.*` cuya firma trae un parámetro literal `competitor_id`** (`pkgutil.walk_packages` + `inspect.signature`, filtrando `name.startswith("_")` y `obj.__module__ == modname`). Eso es exactamente lo que el contrato pide, pero tiene un perímetro, y hay que decirlo explícito porque es lo que el barrido **no** puede ver:

- **Funciones internas (`_prefijo`)**: quedan fuera por diseño. Revisé manualmente las que alimentan a las guardadas — `_load_results`/`_load_events`/etc. de `queries.py` no filtran por competidor (cargan la temporada completa), así que no hay una vía intermedia sin candado; el filtrado por competidor ocurre siempre dentro de la función ya guardada (`athlete_progression`, `projection`).
- **Un `athlete_id` que se resuelve a competidor por dentro**: revisé `newsletter_builder.py:592-608` y `compute_metrics.py` — ambos resuelven su `competitor_id` con `select(RaceCompetitor).where(RaceCompetitor.athlete_id == athlete_id)` (siempre desde un atleta ya autorizado), nunca aceptan un `competitor_id` crudo. No encontré ninguna función que reciba `athlete_id` y lo traduzca a un competidor arbitrario sin ese filtro.
- **Una función que reciba una LISTA de ids** (`competitor_ids: list[int]`): no existe hoy en `app/services/race/`. Si apareciera, el barrido tampoco la detectaría (parámetro no se llama `competitor_id`) — dejo esto anotado como el hueco más probable a vigilar en Phase 4/US4 (identity review, que sí trabajará con conjuntos de competidores).
- **SQL crudo en routers**: `grep -rn "competitor_id" app/routers/` no encontró ningún `text("SELECT ... competitor_id ...")` fuera de `race_competitors.py` (linking, ver §2) y `race_events.py:1298` (`ResultRow` de una sola válida — ver nota abajo). Ningún router arma progresión multi-válida por SQL directo.
- **El pipeline de boletines**: `newsletter_builder.py` — el `competitor_id` sale siempre del `athlete_id` ya resuelto (arriba); `compute_field_metrics` corre con ese mismo id, cubierto por la nota de `ALLOWED_SINGLE_EVENT` (ver §2).
- **Los nodos de IA**: sólo `compute_metrics.py` toca `competitor_id`/progresión. Lo guarda **dos veces** — vía `@club_competitor_only` en `athlete_progression`/`projection`, y de forma **explícita y primero** con `await require_club_competitor(db, competitor_id)` (compute_metrics.py:367) antes de tocar cualquier otra cosa, con el argumento correcto en el docstring: el nodo recibe `state`, no un parámetro `competitor_id` en su firma, así que el barrido estructural **no lo vigila** — sin ese candado explícito, reordenar el nodo o envolver la primera llamada en un condicional habría hecho desaparecer la protección en silencio. Verificado corriendo `test_club_competitor_only_marks_and_enforces_before_body_runs` y los tests de `test_compute_metrics.py` mencionados por el equipo.
- **`field_metrics.compute_field_metrics`**: síncrona, sin `db`, no puede llevar el candado — cubierta en `ALLOWED_SINGLE_EVENT`, ver §2.
- **`analytics.podium_gap`**: no tiene parámetro `competitor_id` (firma `podium_gap(db, category_id, season)`), filtra internamente a `athlete_id IS NOT NULL` antes de construir la grilla — no hay forma de pedirle la fila de un tercero sin importar el `competitor_id` que exista en la tabla. El barrido correctamente no la reporta; documentado en el docstring del propio guard (líneas 38-49) para que no se lea como descuido.

**Conclusión del punto 1**: cobertura real confirmada para todo lo que existe hoy en el árbol. El límite explícito del barrido es (a) funciones internas `_prefijo`, (b) una futura función con `competitor_ids: list[int]` en vez de `competitor_id`, y (c) SQL crudo fuera de `app/services/race/`. Ninguno de los tres tiene hoy una instancia real explotable — quedan como puntos a vigilar cuando US4 (identity review, que trabaja sobre conjuntos) y US5/US6 (history endpoint) se implementen.

---

### 2. Las 5 entradas de `ALLOWED_SINGLE_EVENT`

| Entrada | Sostiene la justificación |
|---|---|
| `field_metrics.compute_field_metrics` | **Sí.** Verifiqué sus dos llamadores de producción uno por uno: `compute_metrics.py:378` corre **después** de que la línea 367 ya validó el mismo `competitor_id` en la misma función (si el candado rechaza, la función completa aborta con `raise` antes de llegar a esta línea — no hay ventana). `newsletter_builder.py:780` recibe un `competitor_id` que en la línea 608 ya salió de `select(RaceCompetitor).where(athlete_id == athlete_id)`, con `athlete_id` fijo de un atleta del club — por construcción nunca un tercero. No hay un tercer llamador de producción (`grep -rn "compute_field_metrics(" app/` sólo devuelve estos dos más los tests). |
| `competitor_linking.suggest_athletes_for_competitor` | Sostiene: no devuelve datos de progresión ni resultados, sólo scores de similitud fuzzy — es la superficie que permite decidir un vínculo, no consultarlo. |
| `competitor_linking.link_competitor_to_athlete` | Sostiene: es la acción misma de vincular; exigir vínculo previo sería contradictorio. |
| `competitor_linking.unlink_competitor` | Sostiene: es la acción de desvincular; ponerla detrás del candado impediría revertir un match equivocado. |
| `third_party_guard.require_club_competitor` | Sostiene: es el primitivo mismo, no puede depender de sí mismo, y sólo devuelve el `athlete_id` vinculado o excepción — nunca datos de progresión. |

Las cinco entradas llevan justificación ≥10 caracteres (`test_allowed_single_event_entries_are_short_and_justified` lo exige y pasa) y la lista no excede el tamaño corto acordado. `test_guarded_functions_are_not_also_allowlisted` confirma que ninguna función lleva doble mecanismo ambiguo.

**Nota aparte, no una entrada nueva de la allow-list**: `race_events.py:1298` (`_result_row_from_orm`) expone `competitor_id`, `display_name` y `club_text` en `ResultRow` — pero es el listado de resultados de **una sola válida** (comportamiento preexistente a esta feature, ya usado por el wizard de importación y la tabla de resultados), no progresión cruzada. No aplica el candado porque no encaja en su ámbito ("datos que abarcan más de una válida"); lo confirmo explícitamente para que quede fuera de duda.

---

### 3. Fuga por canal lateral (id inexistente vs. no vinculado)

Verificado en `require_club_competitor` (`third_party_guard.py:201-215`): un `competitor_id=None` → `reason="missing_competitor_id"`; inexistente → `reason="unknown_competitor"`; existente sin vínculo → `reason="not_linked"`. Los tres casos lanzan la **misma clase de excepción** con el **mismo `code`** público (`ERROR_CODE = "third_party_progression_forbidden"`).

En el borde HTTP (`app/main.py:137-174`, handler a nivel de app, no por router — deliberado para cubrir cualquier router futuro), la respuesta es literalmente idéntica para los tres casos: `403` con `{"detail": {"code": "third_party_progression_forbidden", "message": "Solo se puede consultar el historial de deportistas vinculados al club."}}`. `reason` **nunca** sale en el cuerpo — sólo viaja al log del servidor (`logger.warning` en la línea 156-162 de `main.py`, y otra vez dentro del propio guard vía `_refuse`). Confirmado con test dedicado (`test_unknown_and_unlinked_are_indistinguishable_from_outside`, verde) que compara tipo, `code` y sólo distingue por `reason` interno.

**Conclusión del punto 3**: indistinguible desde afuera, tal como exige el diseño. Sin hallazgos.

---

### 4. Logs y trazas

El evento `third_party_progression_refused` (`third_party_guard.py:165-173` y de nuevo en `main.py:156`) lleva únicamente `competitor_id` (int) y `reason` (código cerrado) — nunca nombre, club ni ciudad. Confirmado además por el test de barrido de PII (`test_no_third_party_name_leaks_into_logs_or_ai_prompt`), que corre el escenario del tercero contra los 4 roles, un `caplog` completo, el dump JSON de `compute_field_metrics` y un `FakeLLMProvider.last_request` real, y no encuentra el nombre sintético en ninguno.

**Hallazgo — el mensaje de la excepción SÍ llega a una traza persistida y expuesta por API, aunque sin PII de identidad.** `ThirdPartyProgressionForbidden.__str__()` produce `"third_party_progression_forbidden (competitor_id=X, reason=Y)"`. El nodo `compute_metrics` está decorado con `@with_events(NODE_NAME)` (`compute_metrics.py:337`); `with_events` (`ai/events.py:117-132`) captura **cualquier** excepción no manejada del nodo, la trunca a 200 caracteres y la emite como evento `node_error` con `payload={"exc": ..., "msg": str(exc)[:200]}`, que queda en `state["errors"]`/`state["events"]`. Ese stream se persiste en `agent_run_events` (`race_analysis.py`, tabla vía `_persist_events`) y se sirve tal cual — sin scrub de `payload` — por `GET /runs/{run_id}/status` (`race_analysis.py:1111-1114`, `_load_events_since` → `RunEvent(**e)`).

Es decir: si `require_club_competitor` rechaza dentro de `compute_metrics` (línea 367, ANTES del try/except propio del nodo — la excepción sube sin capturar hasta el decorador `@with_events`), el mensaje `"...(competitor_id=X, reason=not_linked)"` queda persistido en `agent_run_events` y es legible por quien pueda hacer polling de ese run.

Matizado por tres cosas que bajan la severidad a condición, no bloqueo:
1. El endpoint que sirve ese payload (`GET /race-analysis/runs/{run_id}/status`) exige `_coach_or_admin` + `ensure_run_club_access` — nunca lo ve un padre, y sólo lo ve el coach/admin del club dueño del run.
2. El `competitor_id` que puede llegar a `compute_metrics` es siempre el que `load_athlete_context` resolvió del `athlete_id` ya autorizado por `verify_athlete_access`/`_ensure_athlete_club_access` — nunca un tercero genuino. El único disparador realista es una carrera de datos: el coach desvincula al propio atleta mientras un run en curso todavía tiene el `competitor_id` viejo en `state`. En ese caso el "tercero" es, de hecho, el propio atleta del coach que lanzó el run — no hay fuga de identidad de un menor ajeno.
3. Nunca contiene nombre, club ni ciudad — sólo un id numérico interno y un código de motivo cerrado.

No es lo que el contrato pedía impedir (identidad de un tercero ajeno), pero sí contradice la intención declarada de "sólo IDs, y sólo al log del servidor" del propio módulo, porque este canal en particular es una traza servida por API, no un log de servidor. Lo dejo como **condición**, no bloqueador: recomiendo que T035 (o un follow-up) excluya `ThirdPartyProgressionForbidden` del payload persistido en `agent_run_events` — por ejemplo, en `with_events`, sustituir `msg` por un texto genérico cuando `type(exc) is ThirdPartyProgressionForbidden`, igual que ya se hace con el 403 del router. No bloquea el gate G3 porque no hay ninguna vía real hoy para que el `competitor_id` de un tercero genuino llegue a `compute_metrics` (R-15: el pipeline de IA sólo corre para atletas vinculados).

**Fuera del hallazgo anterior**: revisé también `_analyst_agent_with_fallback` (`graph.py:65-90`, el único otro sitio que serializa `str(exc)[:200]` a `state["errors"]`) — no aplica al candado porque envuelve sólo a `analyst_agent`, no a `compute_metrics`, y `ThirdPartyProgressionForbidden` nunca llega hasta ahí (aborta antes, en el nodo previo).

---

### 5. `city_text`

Confirmado: la columna existe (`race_competitor.py:95`, migración `8efe1618cb83` línea 321, `nullable=True`) pero **no se escribe desde ningún dato real todavía** — `grep -n "city_text" app/services/race/ingestor.py` no arroja nada, y la migración sólo la crea vacía (el backfill de `race_competitor_signatures` usa `"city_norm": ""` fijo, no la ciudad real impresa — eso es esperado, es trabajo de US4, todavía no implementado). Tampoco aparece en ningún schema de lectura (`app/schemas/race_results.py`, `results_read.py`) ni en el router de competidores (`race_competitors.py`). El campo `city` que sí existe hoy (`pdf_parser.py`, `csv_parser.py`, `completeness.py`) es un valor transitorio de parseo — nunca se persiste en el modelo `RaceCompetitor` (documentado explícitamente en el propio parser: *"city no se persiste"*).

**Conclusión del punto 5**: hoy `city_text` no se serializa en ninguna respuesta. Sin hallazgos. Cuando US4 empiece a poblarlo y a mostrarlo en la revisión de identidad, ese trabajo deberá reverificar FR-014 (visible sólo a coach/admin dentro de la revisión, nunca exportado).

---

### 6. Regresión

Confirmada sin hallazgos (ver "Tests corridos yo mismo" arriba): 2536 passed en la suite completa de `race`/`routers`/`privacy`/`models`; los 16 fallos son ajenos a T034/T035 (US1 pendiente de T018/T019, y un fallo preexistente del path de atleta adulto sin relación con `competitor_id`). Revisé en particular que padres sigan sin poder ver terceros (`test_race_analysis_privacy.py` verde) y que ningún nombre entre a un prompt de IA (`test_race_ai_privacy_invariants.py` verde, más el barrido dedicado del propio `test_third_party_lock.py`).

---

## Dictamen §1

**APROBADO CON CONDICIONES**

El candado (T034/T035) cubre correctamente todo lo que existe hoy en el árbol para FR-012…FR-015; las 5 entradas de `ALLOWED_SINGLE_EVENT` están justificadas y verificadas contra sus llamadores reales; el rechazo por id inexistente es indistinguible del rechazo por no-vinculado en el cuerpo HTTP; `city_text` no se serializa en ninguna parte todavía; no hay regresión. No encontré ninguna vía de escape que permita obtener la progresión longitudinal de un tercero genuino.

**Condición para el gate G3** (no bloqueante, pero debe registrarse y resolverse antes de cerrar la feature, no antes de cargar): el mensaje de `ThirdPartyProgressionForbidden` queda persistido tal cual en `agent_run_events` vía `with_events`/`GET /runs/{run_id}/status` cuando el rechazo ocurre dentro de `compute_metrics` — visible a coach/admin del club dueño del run (nunca a un tercero ni a una familia), y sólo contiene `competitor_id` + `reason` (nunca nombre/club/ciudad), pero contradice la intención declarada de "sólo al log del servidor". Recomiendo que `with_events` sustituya el `msg` por un texto genérico cuando la excepción sea `ThirdPartyProgressionForbidden`, antes de que la feature se dé por cerrada. No bloquea T037 porque hoy no existe ninguna vía real para que el `competitor_id` de un tercero genuino llegue a ese nodo (R-15).

**Puntos a vigilar en fases siguientes** (no hallazgos de hoy, registrados para no repetir el análisis): una futura función con `competitor_ids: list[int]` (US4, identity review) no sería detectada por el barrido estructural tal como está escrito — revisar explícitamente cuando esa fase se implemente; y la serialización de `city_text` deberá reverificarse contra FR-014 cuando US4 empiece a poblarlo.

---

## §2 — Auditoría obligatoria de cierre (T090)

**Alcance de esta sección**: `git diff main...HEAD` más el árbol de trabajo completo de la rama al día de hoy — parser (`pdf_parser.py`, `completeness.py`), staging (`import_staging.py`, `routers/race_imports.py`, sus cachés de filas parseadas), identidad (`identity_review.py`, `identity_resolver.py`, `routers/race_identity.py`, `schemas/race_identity.py`, snapshots de candidatos), el candado de terceros y su extensión a listas (`third_party_guard.py` + `tests/privacy/test_third_party_lock.py`), el endpoint de historial y la compuerta familiar (`history.py`, `routers/athlete_race_analysis.py`, `services/privacy.py::is_policy_version_in_force`), ambas audiencias de UI (pestaña Carreras del coach y de la familia, `IdentityReviewPage`, `HistoricalLoadPage`), el script `backend/scripts/stage_race_history.py`, migraciones, fixtures nuevas y el borrador `docs/10-race-results/history-family-notice.md`. Auditor: `data-privacy-guard`. Fecha: 2026-09-22. Rama: `feat/044-race-history-backfill`.

**Metodología**: el alcance no cabía en una sola pasada, así que se dividió en cinco sub-revisiones independientes (cada una otro `data-privacy-guard` con su propio recorrido de archivos y sus propias corridas de tests), y esta sección sintetiza sus cinco reportes. Cada sub-revisión corrió los tests relevantes a su porción por su cuenta (la de historial/candado corrió 90 tests en vivo, todos verdes); no repetí aquí la suite completa porque §1 ya documentó que la suite general está verde salvo los 16 fallos preexistentes y ajenos ya explicados allí, y nada en esta ronda tocó esos archivos.

**Sub-revisiones y sus veredictos**:

| Slice | Alcance | CRÍTICO | ALTO | MEDIO | Veredicto |
|---|---|---|---|---|---|
| A — Parser y staging | `pdf_parser.py`, `completeness.py`, `import_staging.py`, `routers/race_imports.py`, `stage_race_history.py` | 0 | 0 | 1 | Requiere corrección (no bloqueante) |
| B — Identidad | `identity_resolver.py`, `identity_review.py`, `routers/race_identity.py`, `schemas/race_identity.py`, modelos de firma/candidato | 0 | 0 | 1 | Aprobado |
| C — Historial y extensión del candado | `history.py`, `routers/athlete_race_analysis.py`, `services/privacy.py`, `third_party_guard.py` (delta desde §1), `test_third_party_lock.py` | 0 | 0 | 1 | Aprobado |
| D — Frontend | `HistoricalLoadPage.tsx`, `IdentityReviewPage.tsx`, pestaña Carreras (coach y familia), componentes de historial, hooks y API clients | 0 | 0 | 0 | Aprobado |
| E — Migraciones, fixtures y documentos | Las dos migraciones, 14 archivos de fixtures/tests nuevos, `history-family-notice.md`, `history-backfill-design.md`, grep de cédulas/direcciones/teléfonos en todo el diff | 0 | 0 | 0 | Aprobado |

### Hallazgo A — cachés de proceso con filas sin filtrar (MEDIO)

`backend/app/routers/race_imports.py:701-838` mantiene dos `OrderedDict` a nivel de módulo (`_RAW_PARSE_CACHE` por sha256, `_CORRECTED_CATEGORIES_CACHE` por `(sha256, len(corrections))`), de vida igual a la del proceso, acotadas por LRU a 32 entradas cada una, sin TTL. Guardan el `ParsedResults`/`ParsedCategory` completo — nombre, ciudad y club de cada fila de la parrilla, club propio y varios cientos de menores ajenos por igual — sin ningún control de acceso dentro de la propia caché o de sus funciones de carga. Hoy es seguro sólo porque los 6 puntos de entrada que la alcanzan (`dry_run_import`, `commit_import`, `commit_pending_import`, `add_correction`, `acknowledge_category`, `rebuild_identity_candidates`) están detrás de `require_role([admin, coach])` en el router — verificado en cada uno.

**Recomendación** (no bloqueante para G5 ni para la carga real, porque el único perímetro de acceso hoy — RBAC de router — sí se cumple en los seis casos): dejar explícito en un comentario junto a `_RAW_PARSE_CACHE`/`_CORRECTED_CATEGORIES_CACHE` que contienen PII de menores sin filtrar y que cualquier función nueva que las lea debe heredar `require_role([admin, coach])`, para que el control de acceso no dependa silenciosamente de que nadie olvide ese guard en el router al añadir un séptimo llamador.

### Hallazgo B — docstring inexacto sobre el alcance de `city` (MEDIO) — **RESUELTO 2026-09-22**

`backend/app/schemas/race_identity.py:8-9` y `backend/app/routers/race_identity.py:27-28` afirmaban que `IdentityRecordRead` es el *único* schema de toda la plataforma que serializa `city`. Era falso tal como estaba escrito: `backend/app/schemas/race_imports.py:160` (`ParsedResultsRowRead`) y `:219` (`ResultsRowIn`) también llevan `city` — del mismo modo protegido (mismo nivel RBAC, `require_role([admin, coach])` verificado en los 9 endpoints del wizard de importación), así que nunca hubo exposición real, pero el comentario inducía a error a quien lo tomara como base para un chequeo futuro basado en grep.

**Resuelto por `team-lead`** el mismo día: ambos docstrings ahora dicen "fuera de la familia del asistente de importación... es el único schema que serializa `city`", referenciando explícitamente esa familia en vez de afirmar unicidad absoluta. Verificado en el archivo.

### Hallazgo C — la extensión "a listas de competidores" del candado no existe en runtime (MEDIO, informativo)

El mensaje del commit `8ffa380` dice que el candado se extendió "a parámetros con listas de competidores", y en efecto `tests/privacy/test_third_party_lock.py:171` amplió su regex de barrido para reconocer también `competitor_ids: list[int]`. Pero no hay ningún `require_club_competitors` (plural) en `third_party_guard.py`, y un grep de `competitor_ids` en `app/services/race/` (incluyendo `identity_review.py`) no encuentra ese parámetro en ningún lado hoy — nada dispara el regex ampliado, `EXPECTED_CANDIDATES` sigue en 7. No es explotable porque no hay primitivo que bypasear: `identity_review.py` no necesita el candado de un solo competidor porque su trabajo es precisamente comparar competidores no vinculados entre sí (su propio control de acceso correcto es `require_role([admin, coach])` en `race_identity.py`, no el candado de terceros, que protege otra cosa: la progresión longitudinal de alguien no vinculado).

**Recomendación** (no bloqueante): una línea en el docstring de `third_party_guard.py` dejando constancia de que el primitivo por lote aún no existe, para que un cambio futuro de identity-review no asuma que sí.

### Verificaciones limpias, sin hallazgo, por slice

- **A**: ningún `logger.*` en `pdf_parser.py`/`completeness.py`/`import_staging.py`/`race_imports.py` incluye nombre/ciudad/club (sólo ids, conteos, sha256, texto de encabezado de categoría). Ningún mensaje de error al llamador API embebe datos de fila. El flujo de "reconocer un hueco" usa un enum cerrado (`AcknowledgeReasonCode`) con `extra="forbid"` — no existe campo de texto libre. `record_audit` sólo lleva nombres de campo, nunca contenido. Fixtures nuevas de este slice son ficticias ("Ciclista Fantasma", "Club Ficticio Uno/Dos").
- **B**: `city`/`city_text` sólo aparece en `race_identity.py` y `race_imports.py`, ambos coach/admin. Los 5 endpoints de `race_identity.py` exigen `[admin, coach]`. Logs y `record_audit` sólo llevan ids/conteos/códigos de razón. El candado de terceros vive en `require_club_competitor` sin caché, evaluado en vivo. La reversión de una decisión no re-loguea el par de nombres. Fixtures ficticias ("Mateo Ficticio Igual", "Ana Prueba Uno").
- **C**: `get_history` reutiliza `verify_athlete_access` sin modificar — un padre nunca ve el historial de otro atleta (403/404 confirmados por test). `AthleteRaceHistoryRead` (`extra="forbid"`) no lleva `competitor_id` ni lista de la parrilla. El umbral de 5 corredores sigue ocultando percentil/brecha a la mediana; `field_size` queda visible por diseño (conteo puro, no dato comparativo — coherente con el resto del código). `is_policy_version_in_force` falla cerrado (vacío/desconocido/no vigente/deprecado → `False`); `withhold_before` no filtra ninguna pista de cuántas filas se ocultaron. Cero logs en `history.py`.
- **D**: sin `console.*` con datos de fila, sin `localStorage`/`sessionStorage`, rutas y enlaces por id numérico opaco (nunca nombre). `IdentityReviewPage` (que sí renderiza `city`) está detrás de `ProtectedRoute allowedRoles=[coach, admin]` en `App.tsx`, igual que `HistoricalLoadPage`. La vista de familia (`MyAthleteDetailPage`) usa el mismo hook que el coach pero con `audience="family"`, nunca importa `useIdentityReview`/`raceIdentity.ts`, y ninguno de sus componentes (`HistoryTable`/`HistoryChart`/`SeasonCompletionChips`/`CaveatsNote`) tiene siquiera un campo `city`/`club` en sus props — no hay forma estructural de que la vista familiar renderice el dato de un tercero. Fixtures ficticias ("Ana Prueba").
- **E**: las dos migraciones son DDL/backfill genérico, sin nombres reales hardcodeados (`club_norm`/`city_norm`/`normalized_name` son nombres de columna, no valores). Las 14 fixtures nuevas revisadas siguen la convención explícita de marcador ficticio ("Ficticio", "Prueba", "Ejemplar", "Simulado", "Demostrativo", "Sintetico") documentada y forzada por construcción en `identity_support.py`/`results_pdf_builder.py`. `history-family-notice.md` es un borrador genérico sin nombre real, describe el alcance con precisión (no promete anonimato que no entrega, no minimiza que ahora existen datos de otros niños en el sistema), en español neutro (Colombia), detrás de `RACE_HISTORY_FAMILY_POLICY_VERSION` — listo para enviar en cuanto haya visto bueno legal/del dueño del club. `history-backfill-design.md` no usa ningún nombre real como ejemplo. Grep de todo el diff por patrones de cédula/dirección/teléfono: sin coincidencias. `copa_valle_participantes.py` lee credenciales sólo por nombre de variable, nunca las imprime, y sus queries son de solo lectura y agregadas (conteos, nunca nombres).

## Dictamen §2

**APROBADO CON CONDICIONES**

Ninguna de las cinco sub-revisiones encontró un hallazgo CRÍTICO ni ALTO. Los tres MEDIO (A: cachés de proceso sin filtro propio, dependientes del RBAC del router; B: un comentario inexacto sobre el alcance de `city`; C: una extensión "de lista" documentada en el mensaje de commit y en el test de barrido que aún no tiene primitivo real que proteger) son todos no bloqueantes: ninguno tiene hoy una vía de explotación real, y los tres se reducen a dejar una intención por escrito antes de que un cambio futuro la dé por sentada.

**Condiciones para cerrar la feature** (no bloquean la carga real de datos ni el gate G5; deben resolverse antes de dar la 044 por terminada):
1. Documentar en `race_imports.py`, junto a `_RAW_PARSE_CACHE`/`_CORRECTED_CATEGORIES_CACHE`, que contienen PII de menores sin filtro propio y que todo llamador nuevo debe heredar `require_role([admin, coach])`.
2. ~~Corregir el docstring de `IdentityRecordRead`/`race_identity.py`...~~ — **resuelta el mismo día** por `team-lead` (ver Hallazgo B).
3. Anotar en `third_party_guard.py` que el primitivo por lote (`competitor_ids: list[int]`) que el test de barrido ya sabe reconocer no existe todavía en runtime, para que un futuro cambio de identity-review no lo asuma.

Quedan dos condiciones abiertas (1 y 3); la 2 ya está cerrada.

Ningún hallazgo de esta sección exige tocar el candado de terceros de §1 ni reabrir su condición pendiente (el mensaje de `ThirdPartyProgressionForbidden` en `agent_run_events`, aún sin resolver y registrada allí). Ninguna sub-revisión encontró que un nombre, club o ciudad de un menor llegara a un log de servidor, a una traza servida por API a un rol equivocado, a un mensaje de commit, a un prompt de IA, o a una respuesta que una familia o un tercero pudieran leer.

## §3 — Revisión del dictamen §2 (T091, lead de datos y privacidad, 2026-09-22)

**Dictamen §2 confirmado: APROBADO CON CONDICIONES. Las tres condiciones quedan cerradas en la rama.**

- **Hallazgo A (cachés)**: comentario de privacidad en la declaración de `_RAW_PARSE_CACHE` / `_CORRECTED_CATEGORIES_CACHE` (`backend/app/routers/race_imports.py`) que nombra a todos los llamadores autorizados y exige el mismo `require_role([admin, coach])` a cualquier llamador nuevo. Se revisó además que las cachés viven solo en memoria del proceso (32 entradas cada una), se vacían en cada despliegue o reinicio de Render y nunca se serializan a disco ni a logs. Retenerlas más allá de eso no es posible con el despliegue actual.
- **Hallazgo B (docstrings de `city`)**: corregidos en `schemas/race_identity.py` y `routers/race_identity.py` ("fuera del asistente de importación…").
- **Hallazgo C (primitivo por lotes)**: nota en el docstring de `third_party_guard.py`. El primitivo `require_club_competitors` no existe y no debe asumirse.

**Pendientes de FR-043, escritos con responsable** (siguiente feature, no bloquean la carga real):

| Pendiente | Responsable | Cuándo |
|---|---|---|
| Borrado a solicitud de los datos de un tercero (nombre, club, ciudad, resultados) y de sus firmas y candidatos de identidad | Dueño del club (responsable del tratamiento) + la feature siguiente a la 044 | Antes de publicar la versión de aviso de privacidad que abre la compuerta familiar |
| Plazo de retención de los PDF oficiales en el almacenamiento SFTP y de `parse_meta_json` de los imports históricos | Dueño del club | Misma feature |
| Base legal (interés legítimo) y texto del aviso con visto bueno legal | Dueño del club | Antes de fijar `RACE_HISTORY_FAMILY_POLICY_VERSION` |

Revisado también el runbook de carga real (T096): se agregó el respaldo obligatorio de MySQL antes de cada carga y se reescribió el rollback de una temporada (§12.6). Solo `race_results` guarda `imported_from_id`, así que borrar por ese campo dejaba competidores, firmas y candidatos huérfanos que el siguiente recálculo habría tratado como personas reales.
