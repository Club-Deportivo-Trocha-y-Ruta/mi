# Auditoría de Privacidad — Módulo Resultados Copa Valle

**Fecha:** 2026-05-19
**Agente:** `data-privacy-guard` (Opus override)
**Workflow:** [`workflow.md`](./workflow.md) — Paso 8.
**Estado:** APROBADO (con fixes preventivos aplicados).

---

## 1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Archivos auditados | 11 (services/race/*.py + ingestor + schemas + modelos race_* + CLI + 8 suites de tests) |
| Hallazgos críticos (P0) | **0** |
| Hallazgos altos (P1) | **0** |
| Hallazgos medios (P2) | **1** (cobertura sentinel insuficiente — *resuelto en este Paso*) |
| Hallazgos notas (P3) | **3** (preventivos para fases futuras) |
| Tests añadidos | **3** sentinels nuevos en `tests/test_privacy_audit_race.py` |
| Estado de la suite | 305 tests pasan (302 baseline + 3 sentinels) |

**Veredicto:** el módulo `services/race/` + `scripts/ingest_race.py` cumple con
los principios de privacidad de menores declarados en [`CLAUDE.md`](../../CLAUDE.md)
y con la Ley 1581/2012 de Colombia. Los nombres completos de menores **NO** se
filtran en logs, stdout no autenticado, persistencia o reportes agregados. El
flujo interactivo de confirmación de matches (donde el coach SÍ ve nombres) es
contexto autenticado por construcción (CLI ejecutado localmente por el coach).

---

## 2. Marco legal aplicable

| Norma | Implicación |
|---|---|
| **Ley 1581/2012 art. 5** | Datos de menores son **datos sensibles** con tratamiento prohibido salvo excepciones del art. 6. |
| **Ley 1581/2012 art. 6 inc. b** | Excepción para datos públicos por mandato de autoridad. Los PDFs oficiales de la Federación Colombiana de Ciclismo Liga del Valle caen bajo esta excepción. |
| **Decreto 1377/2013** | Política interna debe declarar finalidad, garantías de seguridad y derechos del titular. |
| **Ley 1098/2006 (Infancia y Adolescencia)** | Interés superior del niño — refuerza la protección por encima del estándar adulto. |

**Implicación operativa:** los PDFs ya publicados por la federación pueden
referenciarse en el repo y procesarse; pero **agregar datos no presentes en el
PDF** (DOB, antropometría, datos médicos) cruzaría la frontera de la excepción
y requeriría consentimiento explícito de padres/tutores.

---

## 3. Inventario de superficies auditadas

### 3.1 Código fuente

| Archivo | LoC | Riesgo principal evaluado |
|---|---:|---|
| `backend/app/services/race/ingestor.py` | 626 | Logs INFO en commit, warnings persistidos, athlete_id auto-linkeo. |
| `backend/app/services/race/pdf_parser.py` | 484 | `logger.warning` con líneas raw (cabeceras vs filas). |
| `backend/app/services/race/normalizer.py` | 277 | Sin logs; helpers puros. |
| `backend/app/services/race/matcher.py` | 228 | `logger.debug` con cardinalidad; sin nombres. |
| `backend/app/services/race/analytics.py` | 680 | DataFrames de salida; verificar que `_results_df` no incluya nombres. |
| `backend/scripts/ingest_race.py` | 1140 | CLI: `console.print` interactivos, flag `--show-names`, `_mask_name`. |
| `backend/app/schemas/race.py` | 144 | Schemas Pydantic — verificar que `IngestReport.warnings` no exponga nombres. |
| `backend/app/models/race_competitor.py` | 115 | Modelo SQLAlchemy — DOB, dirección, datos médicos: **NO presentes**. |
| `backend/app/models/race_import.py` | 96 | Trazabilidad: `stats_json` con conteos; `error_log` Text NULL. |
| `backend/app/models/race_*.py` (otros) | — | Categorías, eventos, resultados, series — sin PII directa. |

### 3.2 Fixtures binarios

| Path | Tamaño | Contenido sensible |
|---|---:|---|
| `backend/tests/fixtures/race/valida_iv_2026_resultados.pdf` | 246 KB | Nombre + dorsal + ciudad + club + tiempo + puntos (NO DOB, NO dirección, NO médico). |
| `backend/tests/fixtures/race/valida_iv_2026_general.pdf` | 160 KB | Idem + acumulado por temporada. |
| `docs/10-race-results/snapshots/valida_iv_2026_*.pdf` | (idem) | Snapshots originales para referencia. |

### 3.3 Documentación en repo

- `docs/10-race-results/edge-cases.md` §5 — oracle TyR Válida IV (10 nombres completos en tabla markdown).
- `docs/10-race-results/edge-cases.md` §4.1–4.16 — citas textuales del PDF con nombres.

Ambos casos están **conformes con la excepción de Ley 1581/2012 art. 6 inc. b**
(datos públicos por mandato federativo). Ver §6 más abajo para política.

---

## 4. Hallazgos

### 4.1 P0 críticos — **0 hallazgos**

Sin filtraciones de DOB, datos médicos, contacto de tutores, dirección o
documento de identidad. El modelo de dominio no almacena estos campos para
`RaceCompetitor` — sólo nombre normalizado, nombre de display, club textual,
sexo (nullable) y FK opcional a `athletes.id`.

### 4.2 P1 altos — **0 hallazgos**

- **`logger.info` en commit del ingestor**
  `ingestor.py:379-388` loggea `event_id`, `series_id`, `results_inserted`,
  `results_skipped`, `tyr_count`, `warnings` (longitud). Sin nombres.
- **`logger.warning` del parser** (`pdf_parser.py:243, 263, 298, 382, 401, 466, 472`):
  todos los warnings usan `bib` + `category_code` + `page_idx`. Las cabeceras
  desconocidas se cortan a 80 chars (`stripped[:80]`) y son texto de
  `CAT: <NOMBRE_CATEGORIA>`, no nombre de persona.
- **`logger.debug` del matcher** (`matcher.py:221-226`): sólo
  `candidates_total`, `top`, `threshold`. Cardinalidad y score, nunca nombres.
- **CLI `console.print` no-interactivos** (todos los path `--non-interactive`):
  banner Parseo (`results.name` = filename), tabla resumen (campos meta del
  evento), panel IngestReport (conteos), lista de warnings (sin nombres).
- **CLI `riders list` default**: usa `_mask_name(display_name)` →
  `"T. Cardona"` en lugar de `"Thiago Duque Cardona"`. Flag `--show-names`
  es opt-in explícito del coach.
- **CLI `analyze ranking|gap|evolution|projection`**: dataframes de salida
  contienen `competitor_id` (entero), `category_code`, métricas — sin nombres.
- **CLI `analyze projection`**: `confidence='low'` cuando `n<5` con warning
  explícito (workflow §5.2 y §8.1).
- **`IngestReport.warnings`** (`schemas/race.py:117-143`): documentado como
  contrato de "nunca nombres". Sentinel
  `test_warnings_do_not_leak_names` (`tests/services/race/test_ingestor.py:515`)
  verifica con los nombres más sensibles del oracle.

### 4.3 P2 medios — **1 hallazgo** (resuelto en este Paso)

#### P2-001 — Cobertura sentinel insuficiente sobre stdout

**Descripción.** El sentinel existente `test_warnings_do_not_leak_names`
valida sólo `report.warnings`. No existía test que cubriera:

- stdout completo de `ingest --non-interactive` (tabla resumen, banner Parseo,
  panel IngestReport, lista de warnings combinada).
- stdout de `analyze ranking` (tablas rich + markdown opcional con
  `--output`) — riesgo de regresión si alguien agrega columna `nombre` o
  detalle por competitor.
- stdout de `riders list` default (sin `--show-names`) — riesgo de regresión
  si alguien elimina el `_mask_name` o cambia el default.

**Recomendación.** Añadir 3 tests sentinel con datos reales de Válida IV.

**Fix aplicado.** Nuevo archivo
[`backend/tests/test_privacy_audit_race.py`](../../backend/tests/test_privacy_audit_race.py)
con 3 clases:

| Clase | Verifica |
|---|---|
| `TestIngestStdoutDoesNotLeakNames` | Ningún fragmento de los 10 nombres oracle TyR aparece en stdout de `ingest --non-interactive`. |
| `TestAnalyzeRankingDoesNotLeakNames` | Ningún fragmento de los 10 nombres oracle aparece en stdout ni en markdown de `analyze ranking`. |
| `TestRidersListDefaultMasksTyrNames` | Ningún nombre completo (primer nombre + apellido junto) aparece en stdout de `riders list` default. |

Resultado: **305 tests pasan** (302 baseline + 3 sentinels). Tiempo: 25.3 s.

### 4.4 P3 notas — **3 hallazgos** (preventivos)

#### P3-001 — Política explícita sobre persistencia de `IngestReport.warnings`

`stats_json` actualmente solo persiste la **longitud** de warnings
(`ingestor.py:369-376`). Si el código futuro lo cambia a lista completa, los
warnings (aunque hoy sin nombres) podrían arrastrar cualquier futuro string
sensible si la convención se relaja.

**Recomendación.** Documentar en `models/race_import.py` que `stats_json` no
debe persistir listas detalladas; sólo conteos/IDs. Actual: documentado en
docstring de la clase `IngestReport` (`schemas/race.py:117-134`).
**Acción para sprint posterior**: añadir test sentinel que verifique
`stats_json["warnings"]` es int, no list. **Postergable**.

#### P3-002 — Flag `--show-names` declarado pero no usado en `analyze evolution`

`scripts/ingest_race.py:713` declara `show_names: bool` en `analyze_evolution`,
pero el dataframe que se imprime (`athlete_progression`) no incluye nombre —
sólo `competitor_id`, `category_code`, `position`, etc. El flag se usa solo
en el mensaje de error "Competidor no encontrado" (`línea 740`).

**Por qué no es bug**: comportamiento conservador. Si en el futuro se agrega
columna `display_name`, el flag ya está cableado para opt-in.
**Acción**: mantener; documentar en comentario inline para evitar que un
refactor "limpieza" lo elimine.

#### P3-003 — Fixtures PDF en repo público

Los PDFs Válida IV están en `backend/tests/fixtures/race/` y
`docs/10-race-results/snapshots/`. Son datos públicos por publicación oficial
de la Federación Colombiana de Ciclismo Liga del Valle (Ley 1581/2012 art. 6
inc. b). El oracle TyR en `edge-cases.md §5` también está conforme.

**Política recomendada** (ver §6).

---

## 5. Fixes aplicados en este Paso

### 5.1 Tests sentinel nuevos

**Archivo:** `backend/tests/test_privacy_audit_race.py` (290 líneas).

3 tests sentinel que reaplican el contrato de privacidad en superficies
agregadas del CLI:

```
tests/test_privacy_audit_race.py::TestIngestStdoutDoesNotLeakNames::test_ingest_non_interactive_stdout_has_no_tyr_full_names PASSED
tests/test_privacy_audit_race.py::TestAnalyzeRankingDoesNotLeakNames::test_ranking_stdout_has_no_individual_names PASSED
tests/test_privacy_audit_race.py::TestRidersListDefaultMasksTyrNames::test_riders_list_default_masks_oracle_names PASSED
```

### 5.2 Sin modificaciones a código de producción

No se aplicaron cambios a `services/race/`, `scripts/ingest_race.py`,
`schemas/race.py` ni modelos. El módulo ya cumple los principios.

---

## 6. Política sobre fixtures PDF en repo público

### 6.1 Justificación legal

Los PDFs RESULTADOS y GENERAL de cada válida son **publicaciones oficiales
de la Federación Colombiana de Ciclismo Liga del Valle**. Se publican en su
sitio web sin autenticación, contienen solo: nombre completo, dorsal,
ciudad, club, tiempo, puntos. **NO** contienen DOB, dirección, contacto,
datos médicos. Conforme con Ley 1581/2012 art. 6 inc. b (excepción de
datos públicos por mandato).

### 6.2 Regla operativa

| Acción | Permitida sin autorización adicional |
|---|---|
| Almacenar PDFs originales de la federación en `tests/fixtures/race/` y `docs/10-race-results/snapshots/` | **SÍ** |
| Citar texto literal del PDF (incluyendo nombres) en `edge-cases.md` para documentar parsing | **SÍ** |
| Usar oracle TyR con nombres en tests automatizados | **SÍ** |
| Persistir nombres completos en logs INFO/WARNING de producción | **NO** |
| Persistir nombres completos en `stats_json` o `error_log` de `race_imports` | **NO** (solo conteos/IDs) |
| Exponer nombres en endpoints REST (cuando existan) sin auth | **NO** |
| Agregar DOB, dirección, datos médicos a fixtures o documentación | **NO** (requiere consentimiento) |
| Subir fotos identificables de menores al repo | **NO** (CLAUDE.md CRÍTICA) |

### 6.3 Procedimiento si un padre/tutor solicita retirar datos

1. Confirmar identidad del solicitante (Decreto 1377/2013 art. 22).
2. Eliminar de la BD `RaceCompetitor.athlete_id` para desvincular del athlete
   activo del club (los `race_results` históricos pueden quedar como
   competidor anónimo).
3. **No** modificar los PDFs originales del repo (son publicación de
   tercero — la federación es responsable de origen).
4. Si la solicitud cubre los PDFs, redirigir al solicitante a la federación.
5. Actualizar este documento con la decisión (sección "Changelog" abajo).

---

## 7. Recomendaciones para fases futuras

### 7.1 Cuando se expongan endpoints REST (Fase 2+)

| Endpoint hipotético | Control requerido |
|---|---|
| `GET /race/competitors` | Auth obligatoria. Default enmascarado (`_mask_name`). Flag query `?show_names=true` solo para rol `coach` o `admin`. |
| `GET /race/competitors/{id}` | Auth + RBAC: `parent` solo ve si su `athlete_id` está vinculado al `competitor_id`. |
| `GET /race/results/{event_id}` | Parent: filtrar resultados del padre/madre a solo sus hijos vía intersección con `parent_athlete`. Coach: visión completa del club. |
| `GET /race/analytics/projection/{competitor_id}` | Mostrar `confidence='low'` con disclaimer obligatorio cuando `n_samples<5`. |
| `GET /race/analytics/ranking?season=2026` | Público dentro de la app; ya es agregado por categoría sin nombres. Sin auth requerida pero rate-limit recomendado. |

### 7.2 Cuando se añada `audit_log` (Fase 2+)

- Registrar accesos a `analyze evolution` (lectura individual de menor) con
  `user_id`, `competitor_id`, `timestamp`, `ip`.
- No registrar `analyze ranking` (agregado, sin PII individual).
- Retención mínima 1 año (defensiva — Decreto 1377/2013 art. 11).

### 7.3 Si en algún momento se carga DOB explícita en `race_competitors`

Hoy NO se persiste — el `age_decimal` se calcula on-demand desde
`athletes.birth_date` cuando hay match confirmado. Si se decide persistirla:

- Migración con cifrado at-rest (MySQL `AES_ENCRYPT` o columna virtual).
- Excluir de cualquier API response default; flag opt-in coach/admin.
- Sentinel test que verifique que ningún schema Pydantic expone el campo.

### 7.4 Si se agrega CSV/Excel export

Default debe enmascarar nombres. Flag `--include-names` opt-in con
disclaimer impreso (mismo patrón que `riders list --show-names`).

---

## 8. Checklist de re-auditoría futura

Ejecutar antes de cualquier release con cambios al módulo `race/`:

- [ ] `grep -RE "logger\.(info|debug)" backend/app/services/race/ backend/scripts/ingest_race.py` y verificar que ningún match incluya `row.name`, `competitor.display_name`, `athlete.first_name`, `athlete.last_name`, `c.full_name`, `comp.display_name`.
- [ ] `grep -RE "console\.print|typer\.echo" backend/scripts/ingest_race.py` y verificar que los prints con nombres caen siempre dentro de `if show_names:` o de bloques interactivos prompt.
- [ ] `pytest backend/tests/test_privacy_audit_race.py -v` debe pasar (3/3).
- [ ] `pytest backend/tests/services/race/test_ingestor.py::TestPrivacyInWarnings -v` debe pasar (1/1).
- [ ] Si se agregó nueva columna a `RaceCompetitor` o `RaceResult`, revisar que no expone DOB, dirección, datos médicos.
- [ ] Si se agregó nuevo endpoint REST, agregar test de autorización por rol y enmascarado default.
- [ ] Si se cambió `_mask_name` o `_present_name`, validar que los 4 tests del CLI sobre masking siguen pasando.
- [ ] Verificar que `stats_json` de `RaceImport` no contiene listas detalladas — sólo conteos.

---

## 9. Comandos de verificación rápida

```bash
cd backend
source .venv/bin/activate

# Suite completa race + sentinels privacy
PYTHONPATH=. pytest tests/services/race/ \
                    tests/test_ingest_race_cli.py \
                    tests/test_ingest_race_cli_gaps.py \
                    tests/test_privacy_audit_race.py \
                    --tb=short -q

# Esperado: "305 passed in <30s"

# Solo sentinels privacy
PYTHONPATH=. pytest tests/test_privacy_audit_race.py \
                    tests/services/race/test_ingestor.py::TestPrivacyInWarnings -v
```

---

## 10. Criterios de aceptación workflow §8

- [x] **8.1** — Ningún `logger.info()` con nombre completo de menor. Verificado por grep + sentinel.
- [x] **8.1** — Reportes agregados (`club_ranking`, `podium_gap`) no incluyen feedback individual. Verificado por inspección de `_results_df` (analytics.py) y sentinel nuevo.
- [x] **8.1** — `analytics.athlete_progression()` accesible solo en contexto coach (CLI local — no hay endpoint REST aún). Cuando llegue endpoint, aplicar §7.1.
- [x] **8.1** — CLI no escribe a stdout nombres completos por defecto; usa `--show-names` flag. Verificado por `_mask_name` + sentinel nuevo.
- [x] **8.2** — Política de fixtures PDF documentada (§6).
- [x] **8.3** — Documento `docs/10-race-results/privacy-audit.md` generado (este archivo).
- [x] **Criterio global** — Sin filtraciones detectadas. Estado: **APROBADO**.

---

## 11. Changelog

| Fecha | Cambio |
|---|---|
| 2026-05-19 | Auditoría Paso 8 inicial. 0 hallazgos P0/P1. Fix P2-001 aplicado: 3 sentinels nuevos en `tests/test_privacy_audit_race.py`. 305/305 tests OK. |
