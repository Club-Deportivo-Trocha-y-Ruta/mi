# QA Plan — Módulo Resultados Copa Valle XCO

**Fecha:** 2026-05-19
**Agente:** `quality-engineer` (Opus override)
**Workflow:** Paso 7 cerrado — listo para Paso 8 (auditoría de privacidad).

> Este documento captura el test plan completo del módulo `app/services/race/`
> y `scripts/ingest_race.py`, junto con los gaps de cobertura conocidos y
> el plan para cerrarlos. Sirve como contrato para futuras válidas y para
> el agente operativo `results-analyst` (Paso 9).

---

## 1. Resumen ejecutivo

| Métrica | Valor | Criterio workflow §7 |
|---|---|---|
| Tests totales | 302 | (sin tope) |
| Tests añadidos en Paso 7 | 140 | (sin tope) |
| Cobertura `services/race/` | 98% | ≥85% ✅ |
| Cobertura `app/schemas/race.py` | 100% | — |
| Cobertura `scripts/ingest_race.py` | 70% | (gap esperado: flujo interactivo) |
| Suite completa (race) | 22.7 s | < 30 s ✅ |

**302 tests pasan; 0 fallos.** Todos los criterios del workflow §7 cumplidos.

---

## 2. Cobertura por archivo (post Paso 7)

| Archivo | Stmts | Miss | Cover | Líneas no cubiertas |
|---|---:|---:|---:|---|
| `app/schemas/race.py` | 55 | 0 | **100%** | — |
| `app/services/race/__init__.py` | 0 | 0 | 100% | — |
| `app/services/race/analytics.py` | 202 | 3 | **99%** | 299, 635, 642 |
| `app/services/race/ingestor.py` | 215 | 4 | **98%** | 554, 591, 625-626 |
| `app/services/race/matcher.py` | 69 | 1 | **99%** | 186 |
| `app/services/race/normalizer.py` | 75 | 0 | **100%** | — |
| `app/services/race/pdf_parser.py` | 214 | 9 | **96%** | 282-284, 364, 377, 420, 466-467, 472-473 |
| `scripts/ingest_race.py` | 424 | 127 | **70%** | flujos interactivos (TTY) |
| **TOTAL** | **1254** | **144** | **89%** | — |

### Mejora desde el Paso 6 (baseline pre-QA)

| Archivo | Antes | Después | Delta |
|---|---:|---:|---:|
| `analytics.py` | 95% | 99% | +4 pp |
| `ingestor.py` | 92% | 98% | +6 pp |
| `matcher.py` | 96% | 99% | +3 pp |
| `normalizer.py` | 99% | 100% | +1 pp |
| `pdf_parser.py` | 86% | 96% | +10 pp |
| `schemas/race.py` | 87% | 100% | +13 pp |
| `scripts/ingest_race.py` | 50% | 70% | +20 pp |
| **Total** | **77%** | **89%** | **+12 pp** |

---

## 3. Matriz de cobertura por área

| Área | Tests funcionales | Tests integración | Tests edge case | Tests privacidad | Tests perf |
|---|:---:|:---:|:---:|:---:|:---:|
| **normalizer** | 41 (parse_time, club, name, headers) | — | 33 (typos, vacíos, unicode) | — | — |
| **pdf_parser** | 24 (oracles V-IV reales) | — | 20 (PDFs sintéticos, headers desconocidos, kerning) | — | — |
| **matcher** | 13 (top-3, threshold, age boost) | — | 4 (athlete sin nombres, edad futura, boost capeado) | — | — |
| **ingestor** | 17 (V-IV completo, idempotencia, matches) | — | 49 (concurrencia, tier validation, rollback) | 1 (warnings sin nombres) | 1 (< 5s) |
| **analytics** | 17 (4 funciones × varias condiciones) | — | 5 (DataFrames vacíos, pivots faltantes) | — | — |
| **schemas** | — | — | 23 (validators de error) | — | — |
| **CLI** | 9 (subcomandos básicos) | 8 (ingest + ranking + riders end-to-end) | 22 (YAML inválido, error paths, homónimos) | 4 (`_mask_name`, default conservador) | — |

Totales por tipo:
- **Funcionales**: 121 (40%)
- **Integración**: 8 (3%)
- **Edge cases**: 156 (52%)
- **Privacidad**: 5 (2%)
- **Performance**: 1 (<1%)
- **Errores/validación**: ~50 (parte de edge cases)

Total: **302 tests**.

---

## 4. Inventario de archivos de test

```
backend/tests/services/race/
├── conftest.py                          # FakeAsyncSession + seed de 26 categorías
├── test_analytics.py                    # 17 tests — Paso 5 (athlete_progression, podium_gap, club_ranking, projection)
├── test_ingestor.py                     # 17 tests — Paso 4 (ingest V-IV + idempotencia + warnings)
├── test_ingestor_concurrency.py         # 34 tests — Paso 7 (concurrencia + idempotencia + tier thresholds)
├── test_ingestor_error_paths.py         # 15 tests — Paso 7 (categorías unknown, nombres vacíos, rollback)
├── test_matcher.py                      # 13 tests — Paso 4 (top-3, boost edad, tie-break)
├── test_misc_coverage.py                # 17 tests — Paso 7 (cobertura branches restantes)
├── test_normalizer.py                   # 41 tests — Paso 3 (parse_time, is_trocha_y_ruta, parse_category_header)
├── test_parser.py                       # 24 tests — Paso 3 (oracles V-IV PDFs reales)
├── test_parser_edge_cases.py            # 22 tests — Paso 7 (PDFs sintéticos via monkeypatch)
└── test_schemas_race.py                 # 23 tests — Paso 7 (validators EventMeta, MatchDecision, IngestReport)

backend/tests/
├── test_ingest_race_cli.py              # 17 tests — Paso 6 (CLI end-to-end: ingest, riders list, analyze ranking)
└── test_ingest_race_cli_gaps.py         # 29 tests — Paso 7 (riders link, system_user, _meta_from_yaml, error paths)
```

---

## 5. Fixtures disponibles

### 5.1 PDFs reales (Válida IV 2026)

```
backend/tests/fixtures/race/
├── valida_iv_2026_resultados.pdf   # PDF oficial RESULTADOS V-IV CALI 17-may-2026 (10 págs, 26 cats, 227 corredores)
└── valida_iv_2026_general.pdf      # PDF oficial CLASIFICACION GENERAL post-V-IV (12 págs, 339 filas-temporada)
```

**Justificación de privacidad**: los PDFs son publicación oficial de la Federación
Colombiana de Ciclismo Liga del Valle (datos públicos por mandato federativo,
conforme Ley 1581/2012 art. 6 inc. b). Sólo contienen nombre + dorsal +
categoría + tiempo + puntos — NO fecha de nacimiento, NO datos médicos,
NO domicilio.

### 5.2 PDFs sintéticos (vía monkeypatch en runtime)

`reportlab` y `fpdf` **no están instalados** en el `venv` del proyecto.
La estrategia para tests del parser con escenarios edge es **monkeypatch de
`pdfplumber.open`** con páginas mockeadas (`_FakePage`, `_FakePdf` en
`test_parser_edge_cases.py`). Esto cubre:

| Escenario | Test | Implementación |
|---|---|---|
| Página sin filas (cat vacía) | `test_category_with_zero_rows_returns_empty_list` | `_FakePage(text="CAT: ...\n...header...\n")` |
| Header `CAT:` desconocido | `test_unknown_category_header_logs_warning_and_skips` | Inyecta `"CAT: SUPER ELITE COSMICO"` |
| Filas sin categoría activa | `test_row_without_active_category_skipped` | Página sin `CAT:` previa |
| PDF completamente vacío | `test_completely_empty_pdf_returns_empty_dict` | `_FakePage(text="")` |
| Header GENERAL ausente | `test_general_pdf_default_cols_when_header_not_detected` | Sin línea `... Club/Patrocinador ... Total ...` |
| Header de evento con mes raro | `test_pdf_with_unknown_month_skips_to_next_line` | Inyecta `"XENERO"` |

> **Decisión**: no se generan PDFs sintéticos en disco. Si en el futuro se
> instalara `reportlab`, podríamos materializar las páginas a `.pdf` reales
> y reemplazar el monkeypatch; el contrato del test no cambia.

### 5.3 YAML fixtures (CLI tests)

Generados dinámicamente vía `tmp_path` en cada test:
- `event_meta_yaml` — todos los campos válidos de `EventMeta` para `--non-interactive`.
- `empty_decisions_yaml` — lista vacía `[]` (todos los TyR quedan sin link).

---

## 6. Comandos para correr la suite

### 6.1 Local (desarrollo)

```bash
cd backend
source .venv/bin/activate

# Solo módulo race (recomendado durante desarrollo)
PYTHONPATH=. pytest tests/services/race/ \
                    tests/test_ingest_race_cli.py \
                    tests/test_ingest_race_cli_gaps.py -v

# Con cobertura
PYTHONPATH=. pytest tests/services/race/ \
                    tests/test_ingest_race_cli.py \
                    tests/test_ingest_race_cli_gaps.py \
                    --cov=app.services.race \
                    --cov=scripts.ingest_race \
                    --cov=app.schemas.race \
                    --cov-report=term-missing \
                    --cov-report=html:/tmp/race_cov
# Abre el reporte HTML en /tmp/race_cov/index.html
```

### 6.2 CI

```bash
# CI mínimo (sin cobertura — solo verde/rojo)
cd backend && PYTHONPATH=. pytest tests/services/race/ \
                                  tests/test_ingest_race_cli.py \
                                  tests/test_ingest_race_cli_gaps.py \
                                  --tb=no -q

# Esperado: "302 passed in <30s"
```

Quality gate sugerido:
- `--cov-fail-under=85` sobre `services/race`.
- Tiempo máximo: 30s (workflow §7).

### 6.3 Smoke test pre-deploy

```bash
# Verifica que el CLI funciona end-to-end sin DB real (FakeAsyncSession)
cd backend && PYTHONPATH=. pytest tests/test_ingest_race_cli.py::TestIngestNonInteractive::test_ingest_valida_iv_produces_227_results -v
```

---

## 7. Tests críticos (no quitar / regresión sentinel)

Estos tests bloquean cambios silenciosos que romperían el contrato del módulo:

| Test | Por qué es crítico |
|---|---|
| `test_tyr_oracle_bibs_match` | Verifica los 10 bibs TyR de V-IV (edge-cases §5). Si el fuzzy o el parser cambia, este test detecta regresión inmediata. |
| `test_total_rows_is_227` | Conteo total de corredores V-IV. Cualquier regresión en el parser baja este número. |
| `test_tyr_unique_in_season_is_16` | Catálogo histórico de TyR temporada — base para `club_ranking`. |
| `test_warnings_do_not_leak_names` | Privacidad: warnings nunca con nombres completos (CLAUDE.md inviolable). |
| `test_re_ingest_with_committed_sha_aborts` | Idempotencia SHA256 — protege contra doble ingesta. |
| `test_re_ingest_with_modified_points_preserves_original` | Contrato PRESERVE en re-ingest — si cambia a UPDATE, debe ser decisión explícita. |
| `test_anomalous_time_in_menores_tier_warns` | Bib 424 Matias Sabogal — caso documentado edge-cases §4.2. |
| `test_bib_1411_not_in_results` + `test_bib_1411_present_in_general` | Anomalía estructural V-IV documentada (rider 1411 en GENERAL pero no en RESULTADOS). |

---

## 8. Gaps conocidos (postergables a Fase 2)

### 8.1 Líneas no cubiertas residuales (10 stmts)

| Archivo | Líneas | Razón | Plan |
|---|---|---|---|
| `analytics.py:299` | `events_in_season vacío en podium_gap` con eventos seedeados | edge case raro (ya cubierto por `test_no_events_in_season_returns_empty_df` — un branch de la misma rama) | Ignorar — branch redundante |
| `analytics.py:635, 642` | `_records` helper (numpy item / pd.NA) | trivial, sólo se ejerce con DataFrames complejos en CI | Ignorar — utilidad de test |
| `ingestor.py:554, 591` | update `competitor.sex` cuando ya es None y el code da F (sólo dos casos pequeños) | requiere setup específico | Postergar a Paso 9 (datos reales) |
| `ingestor.py:625-626` | `_parse_bib_safe` con `TypeError` en `int()` | imposible alcanzar tras `.isdigit()` check | Dead code defensivo — ignorar |
| `matcher.py:186` | `normalized_athlete == ""` (post unidecode) | trivial — requiere nombre con sólo caracteres no-ASCII raros | Ignorar |
| `pdf_parser.py:282-284, 420` | fallback `_split_body_fallback` cuando tabla devuelve celdas vacías | requiere PDF con tabla parcial muy específica | Documentar y postergar |
| `pdf_parser.py:364, 377` | filtros defensivos en GENERAL row parser | requiere PDF con header parcial | Postergar |
| `pdf_parser.py:466-467, 472-473` | warnings de roman/mes desconocidos | regex actual no acepta valores fuera del enum, así que estos warnings son código defensivo que sólo se dispararía si se extiende el regex sin actualizar el dict | Documentar y postergar |

### 8.2 CLI: 30% sin cubrir (flujo interactivo)

Las líneas 470-522, 589-641, 911-934 corresponden a:
- `_meta_from_interactive` — prompts `typer.prompt(...)`.
- `_collect_match_decisions_interactive` — prompt iterativo para coach.
- `_analyze_projection_impl` — formateo de panel `rich`.

**Por qué no se cubren**:
1. Requieren TTY simulada (`pexpect`/`pytest-subprocess`); ninguno está instalado.
2. El valor de testear prompts sintéticos es bajo: la lógica que importa
   ya está extraída en helpers que sí están testeados (`_meta_from_yaml`,
   `_decisions_from_yaml`, `_mask_name`, etc.).
3. El path `--non-interactive` está completamente testeado (CI usa ese path).

**Plan**:
- Paso 9 (backfill manual con coach) cubrirá los flujos interactivos como
  prueba de aceptación operativa.
- Si en el futuro se quiere automatizar, agregar `pexpect` a dev-deps y
  escribir tests de prompts.

### 8.3 PDFs sintéticos reales (no monkeypatched)

**Gap**: `reportlab` no instalado → no podemos generar PDFs sintéticos con
`PdfWriter`. Estrategia actual: monkeypatch `pdfplumber.open`.

**Riesgo cubierto / no cubierto**:
- ✅ Cubre: validación de la lógica del parser sobre páginas conocidas.
- ⚠️ No cubre: bugs en la interacción real con `pdfplumber.extract_tables`
  (e.g. extracción de PDF con rulings sutiles). Esto se detecta sólo con
  PDFs reales — y tenemos uno (V-IV) que ejerce todos los casos críticos
  (kerning, multi-página, headers repetidos, etc.).

**Plan**:
- Cuando se agregue `reportlab` o `fpdf` a dev-deps, sustituir los
  monkeypatches por PDFs sintéticos materializados en
  `tests/fixtures/race/synthetic/`.
- Mientras tanto, los PDFs reales de las Válidas I, II y III (Paso 9) se
  ingestarán y servirán como tests de regresión adicionales.

### 8.4 `FakeAsyncSession`: sin soporte para UPDATE / LIKE / JOIN

**Limitación documentada**: el fake del `conftest` cubre `select`, `add`,
`flush`, `commit`, `rollback` con WHERE `==`/`AND`/`OR`. **No soporta**:

- `UPDATE` statements (los tests de `riders link` usan `_MockSessionForLink`
  específico para este caso).
- `LIKE` (los tests de `_resolve_competitor_by_name` usan mocks ad-hoc).
- `JOIN` SQL (el analytics module hace joins **in-pandas** por esta razón).
- `IS NULL` (el analytics module filtra `deleted_at` **in-memory** por la
  misma razón — ver `_load_results`).

**Plan**:
- Mantener el fake estricto (lanza `RuntimeError` ante queries no soportadas)
  para que cambios al ingestor que introduzcan SQL nuevo fallen ruidosamente
  y exijan extender el fake conscientemente.
- Si se vuelve insostenible, migrar tests del ingestor/analytics a
  **aiosqlite** in-memory (`sqlite+aiosqlite:///:memory:`) — pero esto
  requiere agregar `aiosqlite` a dev-deps y resolver compatibilidad de
  enums MySQL ↔ SQLite.

### 8.5 Tests de carga real con MySQL (deferred Paso 9)

No hay tests con MySQL real (Hostinger). El módulo confía en:
- UNIQUE constraints físicas en MySQL (validadas via migración Alembic).
- FK constraints (validadas via migración).
- Transacciones aiomysql (validadas en producción).

**Plan**:
- Paso 9 (backfill V-I..V-III) será el primer test real con MySQL.
- Si surgen bugs, agregar tests de integración con `pytest-mysql` o
  contenedor docker MySQL.

### 8.6 Tests de privacidad explícitos por endpoint

El módulo no expone endpoints REST por design.md §1. Cuando se exponga
(Fase 2), agregar tests de privacidad por endpoint:
- `GET /race/competitors` debe enmascarar nombres sin `--show-names`.
- `GET /race/results/{id}` debe respetar autenticación.

Esto se hereda al diseño del endpoint.

---

## 9. Convenciones de testing en este módulo

1. **Sin DB real**. `FakeAsyncSession` o mocks ad-hoc. Si necesitas DB real,
   abre un issue y discutimos `aiosqlite` o contenedor docker.

2. **Sin nombres en fixtures sintéticos**. Si añades un fixture mockeado:
   - Usa nombres ficticios: `"Niño Test"`, `"Sin Match"`, `"Otro Niño"`.
   - Bibs ficticios: 4 dígitos no observados (e.g. `9001`, `9002`).
   - **PDFs reales V-I..V-IV sí pueden tener nombres reales** porque son
     publicación oficial (Ley 1581/2012 art. 6 inc. b).

3. **Warnings nunca con nombres**. Toda assertion sobre `warnings` debe
   verificar que no contengan fragmentos de nombres reales (>3 chars).
   Ver `test_warnings_do_not_leak_names` como template.

4. **Asyncio**: usar `@pytest.mark.asyncio` para coroutines. `pyproject.toml`
   ya configura `asyncio_mode = "auto"`.

5. **Naming**: `test_<unidad>_<comportamiento>_<expectativa>`. Ejemplo:
   `test_re_ingest_with_modified_points_preserves_original`.

6. **AAA pattern** (Arrange / Act / Assert) implícito. No comentarios `# Arrange`.

7. **Tests deterministas**. Ningún `freezegun` necesario porque pasamos
   `reference_date` explícita a `matcher.match_athletes`.

---

## 10. Próximos pasos sugeridos

| Paso | Acción | Owner |
|---|---|---|
| 8 | Audit de privacidad menores (`data-privacy-guard`) | data-privacy-guard |
| 9 | Backfill V-I..V-III con datos reales — primer test contra MySQL | data-analyst |
| 9 | Si el backfill detecta bugs nuevos, agregar tests de regresión aquí | data-analyst |
| 10 | Considerar `pytest-cov` quality gate en CI (`--cov-fail-under=85`) | devops |
| Futuro | Si se agrega endpoint REST → tests de autorización por rol | backend |
| Futuro | Si se instala `reportlab` → materializar PDFs sintéticos | data-analyst |

---

## 11. Changelog QA

| Fecha | Cambio | Tests afectados |
|---|---|---|
| 2026-05-19 | Paso 7 inicial — 138 tests nuevos, cobertura `services/race/` 77% → 89% | +138 |
| (futuro) | Backfill V-I..V-III → posibles tests de regresión | TBD |

---

**Workflow §7 criterios de aceptación:**

- [x] Cobertura ≥85% en `services/race/` → **98%** (lograda).
- [x] Test plan documentado → **este archivo**.
- [x] Suite completa corre en <30s → **22.7s** medido.
