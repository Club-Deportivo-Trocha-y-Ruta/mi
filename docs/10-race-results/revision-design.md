# Manejo integral de revisiones de resultados — Diseño técnico

**Proyecto:** Club Deportivo Trocha y Ruta — XCO juvenil
**Módulo:** `services/race/` + `routers/race_imports.py` + `frontend/src/routes/results/` (wizard upload)
**Fecha:** 2026-05-21
**Autor:** System Architect agent
**Estado:** Diseño técnico — listo para `/sc:workflow` + `/sc:implement`
**Audiencia:** entrenador (validación UX banner/tabla diff), arquitecto/dev (implementación)
**Entrada autoritativa:** `docs/10-race-results/upload-design.md` (F-UP1-6 cerrado) + `upload-workflow.md` + `backend/app/services/race/ingestor.py` + `backend/app/routers/race_imports.py:280-330`
**Fase:** **F-UP-REV** (extiende wizard upload F-UP)

---

## 0. Resumen ejecutivo

### Problema

Hoy el sistema de ingesta de PDFs Copa Valle deduplica **por SHA256 binario**:

- Si el coach sube el **mismo PDF byte-exacto** → endpoint `POST /imports/parse` devuelve `409 Conflict` (correcto).
- Si el coach sube un **PDF revisado** (la federación publica corrección tras reclamos) con misma válida lógica pero SHA256 distinto → el sistema lo **acepta como evento nuevo y crea duplicado lógico**. Quedan dos `RaceEvent` con mismo `(series_id, sequence_number)` o, peor, dos `RaceImport.status=committed` apuntando a resultados conflictivos en la misma fila `(event_id, category_id, competitor_id)` (la UNIQUE existente los bloquea pero deja inserts parciales mezclados con skips).

### Solución integral

Cambiar el modelo mental de dedup: la unidad lógica no es **el PDF** sino **la válida** (`series_id + sequence_number`). Cuando el coach sube un PDF para una válida ya commiteada con SHA distinto:

1. El backend lo **detecta automáticamente** como revisión (no error 409).
2. El dry-run del wizard devuelve un **diff completo** vs lo persistido: `creates / updates / deletes / unchanged`.
3. La UI muestra ese diff en una **tabla revisable**, con conteos y la decisión por fila preservada (override coach posible en F2 — MVP usa toda la diff propuesta).
4. Al confirmar, el sistema aplica los cambios **transaccionalmente** y registra **una entrada `RaceResultRevision` por cada cambio** (modelo ya existente, ya pensado para esto).
5. Soft-delete de removidos (nunca `DELETE` físico). El audit trail es reversible vía SQL manual.

### Scope

| Incluye | Excluye |
|---|---|
| Detección automática de revisión por `(series_id, sequence_number)` | Override del diff fila por fila en UI MVP (toda o nada) |
| Endpoint `parse` permite mismo (series, valida) si SHA distinto | Endpoint para revertir una revisión (rollback semántico) — diferido F2 |
| Endpoint `dry-run` retorna `diff_rows` estructurado | UI para visualizar histórico de revisiones de un competitor — diferido F2 |
| Endpoint `commit` acepta `revision_reason` opcional | Notificación a padres cuando se aplica revisión — fuera de scope MVP |
| Soft-delete de resultados removidos | Diff de competidores entre PDFs (solo diff de `RaceResult`) |
| Audit completo en `RaceResultRevision` (action: create/update/delete) | Edición libre de campos sin re-subir PDF |
| Migración: `parent_import_id` + `revision_reason` en `RaceImport` | Soporte multi-coach colaborativo (lock pesimista MVP) |
| UI step 2 con modo `diff` (en vez de `matches`) | Diff de GENERAL — solo aplica a RESULTADOS (GENERAL solo pre-llena catálogo) |

**No cambia:** `RaceIngestor.ingest_event` (intacto). `pdf_parser`, `normalizer`, `matcher` (intactos). Modelo `RaceResultRevision` (intacto).

**Reusa al máximo:**
- `RaceResultRevision` con su enum `create/update/delete`, `diff_json`, `reason`.
- `RaceResult.deleted_at` (soft-delete patrón ya existente en F1.7).
- `RaceImport.status=pending/committed/dry_run/failed` y `RaceImport.series_id`.
- Wizard 3 pasos F-UP (sin paso adicional — solo cambia el render del step 2).

---

## 1. Detección lógica de revisión

### 1.1 Regla canónica

> Una ingesta es **revisión** si existe `RaceEvent` con `(series_id, sequence_number) = (event_meta.series_id, event_meta.valida_num)` que ya tenga **al menos un `RaceImport.status=committed`** asociado (vía `RaceImport.event_id`).

Equivalentemente: revisión = "ya hay imports committed para esa válida lógica".

### 1.2 Algoritmo paso a paso (server-side, en `parse` y `dry-run`)

```
def detect_revision(db, series_id, valida_num) -> RevisionDetection | None:
    # 1. Buscar RaceEvent por (series_id, sequence_number)
    event = db.execute(
        select(RaceEvent).where(
            RaceEvent.series_id == series_id,
            RaceEvent.sequence_number == valida_num,
        )
    ).scalar_one_or_none()

    if event is None:
        return None  # Primer import de esta válida — flujo F-UP normal

    # 2. ¿Hay imports committed previos?
    prior_import = db.execute(
        select(RaceImport)
        .where(
            RaceImport.event_id == event.id,
            RaceImport.status == RaceImportStatus.committed,
        )
        .order_by(RaceImport.committed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if prior_import is None:
        return None  # Hay event pero sin imports committed — caso raro F1.7 legacy

    return RevisionDetection(
        is_revision=True,
        parent_event_id=event.id,
        parent_import_id=prior_import.id,
        prior_committed_at=prior_import.committed_at,
        prior_imported_by=prior_import.imported_by_user_id,
    )
```

### 1.3 Trigger en respuestas API

**`POST /imports/parse` response** extendido con campo opcional:

```python
class ImportParseResponse(BaseModel):
    parse_id: int
    results_sha256: str
    ...
    # NUEVO:
    will_be_revision: bool = False
    parent_event_id: int | None = None
    parent_import_id: int | None = None
    prior_committed_at: datetime | None = None
    prior_imported_by_name: str | None = None  # join a User
```

El campo `will_be_revision` permite que la UI cambie de modo **antes** del dry-run (banner inmediato post-paso 1 sin esperar al paso 2).

**`POST /imports/{parse_id}/dry-run` response** extendido con `diff_rows` y `diff_summary` (ver §4 y §6).

### 1.4 Edge cases de detección

| # | Escenario | Decisión |
|---|---|---|
| D-1 | Existe `RaceEvent` pero **0 imports committed** (F1.7 legacy con `event_id=NULL`) | NO es revisión → flujo F-UP normal, primer import “real” con `event_id` set. Se loggea warning informativo. |
| D-2 | Coach sube PDF de **válida 99 (campeonato)** ya commiteada | Es revisión normal. Misma lógica aplica. |
| D-3 | Coach sube PDF con `valida_num` correcto pero `season` distinto (futuro 2027) | NO es revisión — `(series_id, sequence_number)` no matchea porque `series_id` distinto. Crea nueva serie + nuevo evento. |
| D-4 | Coach sube **dos veces el mismo PDF revisado** (mismo SHA distinto al committed) | Primera vez es revisión normal; segunda vez **el SHA del revisado ya está committed** → bloquea con 409 (genuino duplicado byte-exacto). |
| D-5 | Coach sube revisión de revisión (3era versión del PDF) | Es revisión normal — `parent_import_id` apunta al **último committed** (encadenamiento lineal vía `committed_at DESC LIMIT 1`). |
| D-6 | Revisión idéntica lógica (mismo conteo, mismas posiciones, solo metadata distinta del PDF) | `diff_rows` retorna vacío → UI muestra “Esta revisión no cambia ningún resultado” + botón “Aplicar de todos modos (registrar import revisión sin cambios)”. Útil para trazabilidad. |
| D-7 | El coach borró localmente el `RaceImport.status=pending` previo del wizard abandonado (cleanup nocturno F-UP) | Sin impacto — la detección se basa en `committed`, no `pending`. |

---

## 2. Schema delta

### 2.1 Migración Alembic — sí, necesaria

**Migración nueva** `f9a0b1c2d3e4_race_imports_revision_delta.py`
**`down_revision = e8f9a0b1c2d3`** (head F-UP).

Razón: necesitamos persistir **el linaje** (`parent_import_id`) y **el motivo** (`revision_reason`) para auditoría. Sin migración no hay dónde almacenarlos.

### 2.2 Columnas nuevas en `race_imports`

| Columna | Tipo | Nullable | Default | Propósito |
|---|---|---|---|---|
| `parent_import_id` | INT FK→`race_imports.id ON DELETE SET NULL` | YES | NULL | Self-ref al import committed previo. NULL para primer import o legacy. **Encadenamiento lineal** (cada revisión apunta al committed inmediato anterior). |
| `revision_reason` | VARCHAR(300) | YES | NULL | Texto libre del coach explicando la revisión (ej. "Federación corrigió posiciones tras reclamo Andrés Mejía 2026-05-19"). Opcional cuando no hay deletes; **obligatorio cuando `diff` incluye deletes** (validación application-level, no SQL). |

**`is_revision` boolean:** NO se persiste. Se **deriva** vía `parent_import_id IS NOT NULL`. Razón: evitar denormalización + drift entre dos campos que siempre deben coincidir.

**`committed_at` timestamp:** ya existe en `RaceImport` (`status` + `imported_at`/`committed_at` — verificar nombre exacto en modelo). Si no existiera, agregar como parte de esta migración. (TBD durante F-UP-REV1: leer modelo y confirmar.)

### 2.3 Índices nuevos

| Índice | Columnas | Propósito |
|---|---|---|
| `ix_race_imports_parent_id` | `parent_import_id` | Listar revisiones descendientes de un import dado (audit query). |
| (reuso) `ix_race_imports_event_id` | `event_id` | Ya existe en F-UP1. Es el índice clave para detectar revisión. |

### 2.4 Compatibilidad legacy

- Imports F1.7 con `event_id=NULL`: la detección de revisión es **safe** porque consulta `WHERE event_id = <X>` — los legacy con NULL nunca matchean.
- Imports F-UP con `event_id` poblado pero `parent_import_id=NULL` (primer import “real”): son el **primer eslabón** del linaje. Cualquier revisión posterior apunta a ellos.

### 2.5 Migración Alembic — outline

```
revision: f9a0b1c2d3e4
down_revision: e8f9a0b1c2d3
description: Race imports revision support — parent_import_id + revision_reason
```

**Up:**
1. `ADD COLUMN parent_import_id INT NULL`
2. `ADD CONSTRAINT fk_race_imports_parent FOREIGN KEY (parent_import_id) REFERENCES race_imports(id) ON DELETE SET NULL`
3. `ADD COLUMN revision_reason VARCHAR(300) NULL`
4. `CREATE INDEX ix_race_imports_parent_id ON race_imports(parent_import_id)`

**Down:** drop index → drop FK → drop columnas.

**Reversible:** sí. No requiere data migration porque ambas columnas son NULL para imports existentes.

---

## 3. Algoritmo diff

### 3.1 Match key entre PDF nuevo y persistido

Para cada par `(category, competitor)`:

- **Persistido:** `RaceResult` filtrado por `event_id = parent_event_id` Y `deleted_at IS NULL`, joineado a `RaceCompetitor.normalized_name`.
- **PDF nuevo:** filas parseadas por `parse_results_pdf` / `parse_results_csv`, normalizadas con `normalize_name`.

**Match primario:** `(category.code, competitor.normalized_name)`.

**Match secundario (fuzzy fallback):** si normalized_name no matchea exacto, usar `rapidfuzz.partial_ratio >= 92` sobre `normalized_name` dentro de **la misma categoría** (mismo `code`). Razón: typo en revisión (`MEJIA` → `MEJÍA` con acento agregado por la fed).

**No matchea por bib_number.** Razón: bib puede cambiar entre versiones del PDF si la fed corrige uno mal digitado. `normalized_name` es la fuente de verdad.

### 3.2 Clasificación por fila

```
Sea:
  persistidos = {(cat_code, normalized_name): RaceResult}  # filtrado deleted_at IS NULL
  nuevos      = {(cat_code, normalized_name): ParsedRow}   # del PDF nuevo

Para cada key en (nuevos.keys() ∪ persistidos.keys()):
  case (en nuevos) y (en persistidos):
    p = persistidos[key]; n = nuevos[key]
    fields_changed = {}
    para campo en ['position', 'status', 'race_time_ms', 'laps_behind', 'points_awarded']:
      if normalize(p.field) != normalize(n.field):
        fields_changed[campo] = {'before': p.field, 'after': n.field}
    if fields_changed:
      yield DiffRow(action='update', result_id=p.id, diff=fields_changed, ...)
    else:
      yield DiffRow(action='unchanged', result_id=p.id)

  case (en nuevos) y NO (en persistidos):
    # Nuevo competitor en revisión (raro pero válido: la fed agregó un atleta omitido)
    yield DiffRow(action='create', new_row=n, ...)

  case NO (en nuevos) y (en persistidos):
    # Competitor en lo persistido pero NO en el PDF revisado
    # Default: soft-delete (la fed lo removió oficialmente — DSQ / DNF post-protesta)
    yield DiffRow(action='delete', result_id=p.id, ...)
```

### 3.3 Edge cases del diff

| # | Escenario | Tratamiento |
|---|---|---|
| E-1 | Competitor en persistido con `deleted_at IS NOT NULL` y reaparece en revisión | Tratado como `create` (nuevo `RaceResult` row; el viejo queda soft-deleted; la revisión “revive” el resultado con nueva entrada). |
| E-2 | Mismo competitor en dos categorías (raro pero posible si fed corrigió cat) | Trata cada `(cat, name)` como key independiente: aparecerá como `delete` en cat vieja + `create` en cat nueva. |
| E-3 | Typo corregido en `normalized_name` (ej. "JUAN PEREZ" → "JUAN PÉREZ" tras `normalize_name`) | Si `normalize_name` colapsa acentos → match exacto. Si no → fuzzy fallback (§3.1). Si fuzzy también falla → aparece como `delete` viejo + `create` nuevo (subóptimo pero seguro; coach revisa el diff antes de confirmar). |
| E-4 | Competitor sin posición (`position=NULL`, status=`DNF`) en persistido, ahora con `position=42, status=FINISHED` en revisión | `update` con `position` y `status` en `fields_changed`. |
| E-5 | Cambio de `athlete_id` (vinculación TyR cambió) | NO se incluye en diff de revisión. La vinculación atleta se preserva del registro existente (no se sobrescribe). Razón: la decisión de matching TyR es del coach, no de la fed. Si el coach quiere cambiar `athlete_id`, lo hace vía endpoint dedicado o re-confirma matches en step 2 (UI conserva las decisiones previas como pre-fill). |
| E-6 | `points_awarded` cambió porque la fed re-calculó (rangos, bonus) | `update` normal — campo está en la lista. |
| E-7 | PDF revisado tiene **categoría completamente nueva** (la fed habilitó "JUN_F" donde antes solo existía "JUN_M") | Resultados de esa categoría aparecen todos como `create`. Cero `update`/`delete` en esa cat. |
| E-8 | PDF revisado **omite una categoría entera** (la fed removió "PROMO" por baja inscripción) | Todos los resultados de esa cat aparecen como `delete`. |

### 3.4 Campos del `DiffRow` (response API)

```python
class DiffRow(BaseModel):
    action: Literal["create", "update", "delete", "unchanged"]
    category_code: str
    competitor_display_name: str  # del PDF nuevo o del persistido (privado: no expone PII menores aquí porque ya están en BD)
    competitor_normalized_name: str
    # Para action=update y unchanged:
    result_id: int | None = None
    # Para action=create:
    new_row: ParsedRowPreview | None = None
    # Para action=update:
    fields_changed: dict[str, dict[str, Any]] | None = None
        # Ej. {"position": {"before": 5, "after": 3}, "race_time_ms": {...}}
    # Para action=delete:
    deleted_row: ResultPreview | None = None
```

### 3.5 `DiffSummary` (header para UI)

```python
class DiffSummary(BaseModel):
    total_persisted: int
    total_in_new_pdf: int
    creates: int
    updates: int
    deletes: int
    unchanged: int
    fuzzy_matches: int     # cuántos pares matchearon vía fuzzy (sospechosos)
    cross_category_moves: int  # cuántos competitors aparecen como delete+create entre cats
```

`fuzzy_matches > 0` ⇒ banner amarillo en UI: "Algunos competidores fueron matcheados aproximadamente. Revisa antes de confirmar."

---

## 4. Algoritmo commit revisión

### 4.1 Pre-condiciones

- `parse_id` válido, status=`pending`, ownership confirmada.
- `is_revision=True` derivado de detección.
- Diff calculado y pasado al endpoint commit (re-computado server-side para evitar TOCTOU).
- `revision_reason` ≠ None si `summary.deletes > 0` (validación application-level → 400 si falla).
- `confirm=True` en body (igual que F-UP commit).

### 4.2 Pseudocódigo transaccional

```python
async def commit_revision(parse_id, event_meta, revision_reason, current_user):
    async with db.begin():  # BEGIN
        # 1. Re-load context
        parse_import = await db.get(RaceImport, parse_id)
        assert parse_import.status == RaceImportStatus.pending
        detection = await detect_revision(db, series_id, event_meta.valida_num)
        assert detection is not None, "race condition: ya no es revisión"

        # 2. Lock optimista sobre RaceEvent
        event = await db.execute(
            select(RaceEvent).where(RaceEvent.id == detection.parent_event_id)
            .with_for_update()  # advisory lock MySQL
        )

        # 3. Re-parse PDF desde storage_path (ya subido en /parse)
        results_by_cat = await reparse_from_storage(parse_import.storage_path)

        # 4. Re-compute diff (server-side, autoridad final)
        diff_rows = compute_diff(db, event.id, results_by_cat)

        # 5. Validate revision_reason si hay deletes
        if any(r.action == "delete" for r in diff_rows) and not revision_reason:
            raise HTTPException(400, "revision_reason requerido si hay deletes")

        # 6. Aplicar cada diff_row transaccionalmente
        for row in diff_rows:
            if row.action == "create":
                new_result = build_race_result(row.new_row, event.id, parse_import.id, current_user.id)
                db.add(new_result)
                await db.flush()  # necesario para tener new_result.id
                db.add(RaceResultRevision(
                    result_id=new_result.id,
                    action=RaceResultRevisionAction.create,
                    changed_by_user_id=current_user.id,
                    diff_json={"after": serialize_result(new_result)},
                    reason=revision_reason,
                ))

            elif row.action == "update":
                result = await db.get(RaceResult, row.result_id)
                before = serialize_result(result)
                apply_changes(result, row.fields_changed)
                after = serialize_result(result)
                db.add(RaceResultRevision(
                    result_id=result.id,
                    action=RaceResultRevisionAction.update,
                    changed_by_user_id=current_user.id,
                    diff_json={"before": before, "after": after, "fields": list(row.fields_changed.keys())},
                    reason=revision_reason,
                ))

            elif row.action == "delete":
                result = await db.get(RaceResult, row.result_id)
                before = serialize_result(result)
                result.deleted_at = datetime.now(timezone.utc)
                # Política: NO cambiamos result.status — lo dejamos como estaba.
                # El deleted_at es el discriminador. Status=DSQ semántico se hace
                # vía revision_reason en humano-leíble.
                db.add(RaceResultRevision(
                    result_id=result.id,
                    action=RaceResultRevisionAction.delete,
                    changed_by_user_id=current_user.id,
                    diff_json={"removed": before},
                    reason=revision_reason,
                ))

            # action=unchanged → skip

        # 7. Promover RaceImport a committed con linaje
        parse_import.status = RaceImportStatus.committed
        parse_import.parent_import_id = detection.parent_import_id
        parse_import.revision_reason = revision_reason
        parse_import.event_id = event.id
        parse_import.stats_json = {
            "is_revision": True,
            "creates": sum(1 for r in diff_rows if r.action == "create"),
            "updates": sum(1 for r in diff_rows if r.action == "update"),
            "deletes": sum(1 for r in diff_rows if r.action == "delete"),
            "unchanged": sum(1 for r in diff_rows if r.action == "unchanged"),
        }

    # COMMIT (implícito al salir de db.begin())

    return CommitRevisionResponse(...)
```

### 4.3 Política importante: status de resultados soft-deleted

**Decisión:** soft-delete via `deleted_at` **NO cambia** `status`. El status semántico (DSQ, DNF, DNS, FINISHED) refleja **lo que la fed publicó originalmente**. El soft-delete es metadata operacional ("este resultado fue removido por revisión").

**Razón:** preserva integridad histórica. Si un coach quiere reportar "fue descalificado", lo hace en `revision_reason`. El `RaceResult.status` siempre refleja lo último publicado por la fed.

### 4.4 ¿Y si dos coaches commitean revisiones simultáneas?

Lock pesimista vía `SELECT ... FOR UPDATE` sobre `RaceEvent` (§4.2 paso 2). La segunda transacción espera; al adquirir el lock recomputa el diff (que ahora incluye los cambios de la primera) y aplica solo el delta restante.

**Edge:** si el segundo coach subió el **mismo PDF** que el primero, su diff post-lock será todo `unchanged` → no se aplica nada, pero igual se persiste `RaceImport` committed con `stats.creates=0,updates=0,deletes=0` y `parent_import_id=<id del primer commit>`. Audit trail completo.

---

## 5. Cambios API

### 5.1 `POST /imports/parse` — cambio de comportamiento

**Antes (F-UP):**
- SHA committed encontrado → `409 Conflict`.

**Después (F-UP-REV):**
- **SHA idéntico** (binario exacto) committed encontrado → sigue siendo `409 Conflict`. (Genuino duplicado byte-exacto; no aporta info nueva.)
- **`(series_id, sequence_number)` ya tiene committed pero SHA distinto** → `200 OK` con `will_be_revision=true, parent_event_id, parent_import_id, prior_committed_at, prior_imported_by_name`.

**Sin breaking change:** los campos nuevos son optional con default falsy. Cliente F-UP sigue funcionando.

⚠️ **Nota:** la determinación de `(series_id, sequence_number)` en `parse` requiere que el cliente envíe `series_name + season + valida_num` en el form (ya lo hace, ver `race_imports.py:281-283`). Si no se enviaran, el detector cae a `None` y se trata como primer upload. Confirmar que el wizard pre-llena estos campos en step 1 incluso antes de step 2.

### 5.2 `POST /imports/{parse_id}/dry-run` — response extendido

```python
class ImportDryRunResponse(BaseModel):
    parse_id: int
    report: IngestReport  # como antes
    matches_preview: list[MatchPreview]  # como antes — solo si NO es revisión
    will_create_event: bool
    will_update_event_id: int | None

    # NUEVO (solo presente si is_revision=true):
    is_revision: bool = False
    parent_event_id: int | None = None
    parent_import_id: int | None = None
    prior_committed_at: datetime | None = None
    prior_imported_by_name: str | None = None
    diff_summary: DiffSummary | None = None
    diff_rows: list[DiffRow] | None = None  # ordenadas: deletes → updates → creates → unchanged
```

**Comportamiento del backend:**
- Si `is_revision=False` → comportamiento F-UP intacto, response sin `diff_*` (campos opcionales NULL).
- Si `is_revision=True` → el `IngestReport.results_inserted` representa el conteo **de creates**, no de “todos los resultados del PDF nuevo”. Esto mantiene semántica de “qué se va a escribir”. `IngestReport.warnings` incluye `"REVISION: vs import_id=<parent>"`.

### 5.3 `POST /imports/{parse_id}/commit` — body extendido

```python
class ImportCommitRequest(BaseModel):
    event_meta: EventMeta
    match_decisions: dict[str, int | None]
    force_reingest: bool = False
    confirm: bool

    # NUEVO:
    revision_reason: str | None = Field(None, max_length=300)
```

**Validación application-level (no SQL):**
- Si `is_revision=True` y `diff_summary.deletes > 0` y `revision_reason` vacío → `400`.
- Si `is_revision=False` y `revision_reason` provisto → `400` ("revision_reason solo aplica a revisiones").

**Response extendido:**

```python
class ImportCommitResponse(BaseModel):
    parse_id: int
    event_id: int
    series_id: int
    report: IngestReport
    storage_url_results: str | None
    storage_url_general: str | None

    # NUEVO:
    is_revision: bool = False
    parent_import_id: int | None = None
    revisions_created: int = 0  # cuántas filas en race_result_revisions
    creates: int = 0
    updates: int = 0
    deletes: int = 0
    unchanged: int = 0
```

### 5.4 Errores nuevos / cambios

| Código | Trigger nuevo |
|---|---|
| 400 | `revision_reason` requerido (deletes presentes) o `revision_reason` provisto pero no es revisión |
| 409 (sin cambio) | SHA byte-exacto idéntico ya committed |
| 422 (sin cambio) | Categoría desconocida (igual que F-UP) |
| 423 Locked (NUEVO opcional) | Race condition: otro coach está commiteando revisión al mismo event (lock timeout) — UI muestra "Otro entrenador está aplicando una revisión a esta válida. Espera 30s y reintenta." |

### 5.5 Endpoint nuevo opcional (NO MVP)

`GET /imports/{import_id}/revisions` — listar revisiones derivadas de un import. Útil para auditoría. **Diferido F2** salvo que coach lo pida explícito.

---

## 6. UI step 2 — modo `diff` (cambia el render según `is_revision`)

### 6.1 Lógica de modo

```typescript
const step2Mode: 'matches' | 'diff' =
  parseResponse.will_be_revision ? 'diff' : 'matches';
```

### 6.2 Modo `diff` — layout

```
╔══════════════════════════════════════════════════════════════════╗
║ Paso 2 de 3 — REVISIÓN DETECTADA                                 ║
╠══════════════════════════════════════════════════════════════════╣
║ ⚠ Esta válida ya fue importada previamente.                      ║
║                                                                  ║
║ Válida IV — Cali (event #4)                                      ║
║ Importada por:  entrenador   ·   2026-05-17 18:42                ║
║ Import previo:  #12          ·   PDF: valida_iv_v1.pdf           ║
║                                                                  ║
║ Cambios detectados vs el PDF previo:                             ║
║                                                                  ║
║  ┌─────────────────────────────────────────────────────────┐     ║
║  │  3 nuevos    ·  12 actualizados  ·  2 removidos         │     ║
║  │                                  ·  210 sin cambios     │     ║
║  └─────────────────────────────────────────────────────────┘     ║
║                                                                  ║
║  [✓] Mostrar solo cambios                                        ║
║                                                                  ║
║  ┌──────┬──────────┬──────────────────┬──────────────────────┐   ║
║  │ Acc. │ Cat      │ Competidor       │ Cambios              │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟡 U │ JUN_M    │ ANDRÉS MEJÍA     │ position: 5 → 3      │   ║
║  │      │          │                  │ time: 50:12 → 49:08  │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟡 U │ INF_A_M  │ JUAN PÉREZ MORA  │ position: NULL → 4   │   ║
║  │      │          │                  │ status: DNF → FIN.   │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟢 C │ INF_A_F  │ MARÍA GÓMEZ      │ NUEVO en revisión    │   ║
║  │      │          │                  │ pos: 7  time: 33:42  │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🔴 D │ JUN_M    │ DIEGO ROJAS      │ REMOVIDO             │   ║
║  │      │          │                  │ (era pos 8, FIN.)    │   ║
║  └──────┴──────────┴──────────────────┴──────────────────────┘   ║
║                                                                  ║
║  ⚠ Hay eliminaciones — explica el motivo de la revisión:         ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │ Resultados corregidos por la federación tras reclamo de    │  ║
║  │ Andrés Mejía sobre tiempo cronometrado en V-IV (2026-05-19)│  ║
║  └────────────────────────────────────────────────────────────┘  ║
║  120/300 caracteres                                              ║
║                                                                  ║
║                          [← Atrás]   [Vista previa final →]      ║
╚══════════════════════════════════════════════════════════════════╝
```

### 6.3 Componentes UI nuevos

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| `RevisionBanner` | `frontend/src/components/race/RevisionBanner.tsx` | Banner amarillo con metadata import previo, lookup user via API. |
| `DiffSummaryCounts` | `frontend/src/components/race/DiffSummaryCounts.tsx` | 4 badges con counts coloreados. |
| `DiffTable` | `frontend/src/components/race/DiffTable.tsx` | Tabla virtualizada (TanStack Table + react-window si >100 filas). Columnas: Acción (badge), Categoría, Competidor, Cambios. Filtro "Solo cambios". |
| `RevisionReasonInput` | `frontend/src/components/race/RevisionReasonInput.tsx` | Textarea controlled con counter y validación (obligatorio si deletes > 0). |

### 6.4 Comportamiento step 2 según modo

| Modo | Mostrar | Inputs requeridos |
|---|---|---|
| `matches` (no revisión) | EventMetaForm + MatchDecisionTable (F-UP) | match decisions |
| `diff` (revisión) | EventMetaForm (preserva los valores del event existente como pre-fill) + RevisionBanner + DiffSummaryCounts + DiffTable + RevisionReasonInput | revision_reason (si deletes>0) |

**EventMetaForm en modo `diff`:** se pre-rellena con los valores actuales del `RaceEvent` persistido (clima, temperatura, ciudad). El coach puede editarlos. Los cambios se aplican vía upsert del ingestor (igual que F-UP — el método `_upsert_event` ya hace update in-place).

### 6.5 Step 3 success — confirmación

```
╔══════════════════════════════════════════════════════════════╗
║ ✓ Revisión aplicada exitosamente                             ║
║                                                              ║
║  Evento:  Válida IV — Cali (event #4)                        ║
║  Import:  #15 (revisión de #12)                              ║
║                                                              ║
║  Cambios aplicados:                                          ║
║    🟢 3 resultados nuevos                                    ║
║    🟡 12 resultados actualizados                             ║
║    🔴 2 resultados removidos (soft-delete)                   ║
║    ⚪ 210 sin cambios                                        ║
║                                                              ║
║  Audit:                                                      ║
║    17 filas registradas en race_result_revisions             ║
║    Motivo: "Resultados corregidos por la federación..."      ║
║                                                              ║
║  [Cargar otro archivo]    [Ir a Nuevo análisis →]            ║
╚══════════════════════════════════════════════════════════════╝
```

### 6.6 UX paginación si diff grande

- **N ≤ 50 cambios:** tabla completa renderizada (sin virtualization).
- **50 < N ≤ 500:** TanStack Table con virtualization (react-window/react-virtual).
- **N > 500:** además, paginación cliente (20/pág) + warning banner "Diff inusualmente grande (>500 cambios). ¿Estás seguro que es la misma válida?".

---

## 7. Risk register

| # | Riesgo | Prob | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Pérdida de datos por soft-delete erróneo (revisión que en realidad era PDF de otra válida confundida por el coach) | Baja | **Alto** | (a) confirmación explícita step 3 con checkbox; (b) `revision_reason` obligatoria si hay deletes; (c) audit trail completo en `RaceResultRevision` (reversible vía SQL: `UPDATE race_results SET deleted_at=NULL WHERE id IN (SELECT result_id FROM race_result_revisions WHERE ...)`); (d) banner amarillo "Diff inusualmente grande" si >500 cambios o deletes >20% del total. |
| R2 | Diff muy grande (>500 cambios) degrada performance UI (lag en render) | Baja | Medio | TanStack Table con virtualization. Paginación cliente. Backend retorna `diff_rows` siempre completo (no streaming MVP) pero limitado por `IngestReport.results_inserted < 5000` (cap defensivo: si excede, retornar 422 "diff demasiado grande, contactar dev"). |
| R3 | Coach cambia normalized_name accidentalmente (re-parseo extrae diferente porque actualizamos `normalize_name`) → match exact falla, fuzzy también falla → todo aparece como delete+create | Baja | Alto | (a) `normalize_name` es función pura y estable (no se cambia entre versiones del backend sin migración previa); (b) fuzzy match con `partial_ratio >= 92` cubre typos menores; (c) `DiffSummary.fuzzy_matches` count visible en UI → banner si > 0; (d) `cross_category_moves` también visible. |
| R4 | Race condition: 2 coaches suben mismo PDF revisado simultáneamente | Muy baja | Bajo | Lock pesimista `SELECT ... FOR UPDATE` sobre `RaceEvent` en commit (§4.2). El segundo coach espera y recomputa diff post-lock (que será todo `unchanged`). Si SHA del segundo === SHA del primero → 409 normal. |
| R5 | `parent_import_id` chain corrupto si admin hace hard-delete de un import (operación SQL manual) | Muy baja | Bajo | FK `ON DELETE SET NULL` preserva descendientes con `parent_import_id=NULL` (audit roto pero no rompe queries). Documentar en runbook que **nunca** se debe hard-deletear imports — siempre marcar `status=failed`. |
| R6 | Re-parseo en commit (§4.2 paso 3) usa storage_path pero el archivo fue movido/borrado | Baja | Medio | Storage path es **inmutable** post-`/parse` (F-UP DT-4: parse sube a `pending/`, commit mueve a `committed/` solo al final). Si rename falla → rollback. Si archivo no existe → 500 con mensaje claro. |
| R7 | Coach espera el diff pero `dry-run` se cuelga (PDF grande, fuzzy matching costoso) | Baja | Medio | Timeout 30s ya existe en parse (F-UP). Diff es trivial en SQL (1 query persistidos + 1 fuzzy en memoria); coste O(N×M) acotado por N<300 competitors y M=top-3 candidates. Estimado <500ms para diff típico. Si excede 5s → log warning. |
| R8 | El `RaceResultRevision.action=delete` queda “colgado” si después soft-delete se revierte manualmente | Baja | Bajo | Por diseño: las revisiones son **append-only**. Revertir un soft-delete vía SQL deja `deleted_at=NULL` pero conserva la revisión `action=delete` como evidencia histórica. Si el coach quiere registrar "se reactivó", futura revisión del mismo PDF re-creará entrada `action=create`. |
| R9 | Filtro UI "Solo cambios" oculta filas `unchanged` pero al confirmar el backend recomputa diff y aplica todo — discrepancia visual vs ejecución | Muy baja | Medio | Backend es autoridad final (§4.2 paso 4). El filtro UI solo afecta render. Step 3 muestra summary completo (con `unchanged` count) → coach ve el total real. |
| R10 | Coach abandona wizard en step 2 con revision pending → al volver, el persistido cambió (otro coach revisó entre tanto) | Baja | Medio | TTL pending 24h (F-UP). Si el coach vuelve y el `parse_id` aún es válido, el dry-run **se re-ejecuta** (no cacheado) y muestra el diff actualizado. Banner "Aviso: estos cambios reflejan el estado actual, no el de cuando subiste el archivo." (futuro F2). |
| R11 | `revision_reason` filtrado en logs aplicación contiene nombres de menores | Baja | Alto | Sanitización en logger: `logger.info("revision_committed import_id=%d reason_length=%d", id, len(reason))` — nunca loggear el texto del reason. El reason solo se persiste en BD, no en logs. |
| R12 | Coach sube PDF revisado que **excluye GENERAL** intencionalmente — esto no es revisión de GENERAL (que solo pre-llena catálogo) pero coach espera ver cambios | Baja | Bajo | Documentar en UI: "Las revisiones solo aplican a resultados de la válida. El acumulado de temporada (GENERAL) se recalcula automáticamente." |

---

## 8. Decisiones cerradas para el workflow

`/sc:workflow` y `/sc:implement` deben respetar las siguientes sin re-consultar:

1. **`RaceResultRevision` se reutiliza** intacto. Tres acciones: `create`, `update`, `delete`. No se crea modelo nuevo.
2. **`RaceResult.deleted_at`** es el discriminador soft-delete. `status` NO cambia en deletes — solo `deleted_at`.
3. **Migración Alembic** agrega `parent_import_id` (FK self-ref, ON DELETE SET NULL) + `revision_reason VARCHAR(300)` + índice. Reversible.
4. **`is_revision` se deriva** de `parent_import_id IS NOT NULL`. NO se persiste como columna.
5. **Detección de revisión:** `(series_id, sequence_number)` con `RaceImport.status=committed` previo. Encadenamiento lineal vía `committed_at DESC LIMIT 1`.
6. **Match diff:** primario `(category.code, normalized_name)`. Fuzzy `partial_ratio >= 92` dentro de misma cat como fallback. NO match por bib.
7. **Diff incluye:** create / update / delete / unchanged. Campos comparados: `position, status, race_time_ms, laps_behind, points_awarded`. NO compara `athlete_id` (vinculación TyR la preserva el upsert).
8. **`revision_reason` obligatorio** si hay deletes. Opcional si no.
9. **`POST /parse`:**
   - SHA byte-exacto committed → 409 (sin cambio).
   - `(series, valida)` committed pero SHA distinto → 200 con `will_be_revision=true`.
10. **`POST /dry-run` response** incluye `is_revision`, `diff_summary`, `diff_rows` (solo si revisión).
11. **`POST /commit` request** acepta `revision_reason: str | None`. Validation app-level.
12. **Commit transaccional:** una `RaceResultRevision` por cada change (create/update/delete). Soft-delete via `deleted_at=NOW()`. Lock pesimista `FOR UPDATE` sobre `RaceEvent`.
13. **UI step 2 modo dual:** `matches` (no revisión) | `diff` (revisión). Mismo wizard, distinto render.
14. **UI step 2 modo `diff`:** RevisionBanner + DiffSummaryCounts + DiffTable + RevisionReasonInput. EventMetaForm pre-rellenado con datos del event existente.
15. **DiffTable virtualizada** si >50 filas (TanStack Table + react-window).
16. **DiffTable readonly en MVP:** coach NO puede overridear el diff fila por fila. Toda o nada. Override es F2 si el coach lo pide.
17. **`athlete_id` linkage** NO se sobrescribe en revisión. El upsert preserva el binding TyR existente.
18. **Audit append-only:** `RaceResultRevision` jamás se hard-deletea. Reversión via SQL manual (documentado en runbook).
19. **Lock pesimista** vía `SELECT ... FOR UPDATE` sobre `RaceEvent` en commit. Timeout default MySQL (50s).
20. **Tests obligatorios antes de mergear:** backend nuevo ≥90% en `diff.py` + `commit_revision`; frontend componentes nuevos ≥85% incluyendo DiffTable virtualization; E2E happy revisión (re-upload Válida IV modificado) + 1 error path (deletes sin reason).
21. **Sin endpoint nuevo** `GET /imports/{id}/revisions` en MVP. Diferido F2.
22. **Sin override fila por fila** en DiffTable MVP. Diferido F2.
23. **Compatibilidad CLI:** `scripts/ingest_race.py` sigue funcionando sin cambios. La revisión es feature exclusiva del wizard. Si CLI detecta `(series, valida)` committed con SHA distinto → comportamiento legacy (loggea warning informativo, aborta sin error). Documentar.

---

## 9. Open questions coach (⚠️ requieren validación)

| # | Pregunta | Recomendación default si no responde |
|---|---|---|
| Q1 | ⚠️ ¿Coach quiere ver `unchanged` rows por default en DiffTable, o ocultar (filtro "Solo cambios" activo por default)? | **Filtro activo por default** (oculta unchanged). Menos ruido visual; toggle disponible. |
| Q2 | ⚠️ ¿El campo `revision_reason` debe ser obligatorio SIEMPRE (no solo si hay deletes)? | **Solo si hay deletes** (decisión 8 cerrada). Razón: typos en posiciones no requieren justificación; eliminar atleta sí. |
| Q3 | ⚠️ ¿Aplicar revisión debe notificar a padres de atletas TyR afectados? | **NO en MVP** (consistente con upload v1 sin emails). Eventual F2 con opt-in. |
| Q4 | ⚠️ ¿Permitir al coach **override** del diff fila por fila ("este create no lo apliques") en MVP? | **NO** (decisión 16). Si lo pide explícito → F2. |
| Q5 | ⚠️ Tras aplicar revisión, ¿el coach quiere ver el histórico completo de revisiones del evento? | **NO en MVP** (decisión 21). Mostrar solo el last commit. Endpoint `GET /imports/{id}/revisions` diferido. |
| Q6 | ⚠️ Si la diff tiene **0 cambios** (PDF revisado idéntico lógicamente), ¿permitir commit "fake" para registrar trazabilidad? | **SÍ** (D-6 §1.4). Genera `RaceImport` committed con stats todo en 0 + `parent_import_id` set. Útil para auditoría ("verifiqué que la v2 del PDF no cambió nada"). |
| Q7 | ⚠️ Ante una revisión, ¿se actualiza también `RaceEvent.climate`, `temperature_c`, etc., si el coach editó EventMetaForm? | **SÍ** (decisión 14 + upsert F1.7 ya lo hace). Esto es feature, no bug — el coach puede corregir el clima reportado vía revisión. |

---

## 10. Apéndice — ejemplos de `diff_json` en `RaceResultRevision`

### 10.1 action=create

```json
{
  "after": {
    "result_id": 1234,
    "event_id": 4,
    "category_id": 7,
    "competitor_id": 88,
    "athlete_id": null,
    "bib_number": 152,
    "position": 7,
    "status": "finished",
    "race_time_ms": 2022000,
    "laps_behind": null,
    "points_awarded": 18
  }
}
```

### 10.2 action=update

```json
{
  "before": {
    "position": 5,
    "status": "finished",
    "race_time_ms": 3012000,
    "laps_behind": null,
    "points_awarded": 22
  },
  "after": {
    "position": 3,
    "status": "finished",
    "race_time_ms": 2948000,
    "laps_behind": null,
    "points_awarded": 26
  },
  "fields": ["position", "race_time_ms", "points_awarded"]
}
```

### 10.3 action=delete

```json
{
  "removed": {
    "result_id": 891,
    "event_id": 4,
    "category_id": 7,
    "competitor_id": 42,
    "bib_number": 412,
    "position": 8,
    "status": "finished",
    "race_time_ms": 3142000,
    "points_awarded": 12
  }
}
```

---

## 11. Próximos pasos

1. **Validar Q1-Q7 con coach** (sesión 10 min — la mayoría tiene default razonable).
2. **`/sc:workflow revision-design.md`** → genera `revision-workflow.md` con fases F-UP-REV0..7 (ya redactado en archivo paralelo).
3. **`/sc:implement F-UP-REV1`** para la migración Alembic.
4. **Coordinar con F-UP en curso:** F-UP-REV depende de que F-UP esté mergeado (necesita `event_id`, `kind`, `storage_*` en `RaceImport`).
5. **Code review previo a merge:** especial atención al lock pesimista §4.2 y al diff §3.2 (la fuente de bugs más probable).

---

**Fin del documento.**
