# Backfill Copa Valle 2026 — Trocha y Ruta

**Fecha:** 2026-05-19 (parser + dry-run; sin DB real)
**Estado:** Válida IV LISTA para ingest real | Válidas I, II, III pendientes de PDFs
**Agente:** `data-analyst` (Opus) — Paso 9 del [`workflow.md`](./workflow.md)

> Este documento captura el estado del backfill de la temporada Copa Valle 2026
> al cierre del Paso 9. Backfill operativo real (con MySQL Hostinger) requiere
> acción del coach: proveer PDFs Válidas I/II/III y ejecutar el CLI con DB
> activa. Lo que SÍ entregamos aquí es:
>
> 1. Validación del módulo end-to-end con dry-run sobre Válida IV (sin DB).
> 2. Reporte estructurado de "lo que se ingestaría" para V-IV.
> 3. Agente operativo [`results-analyst`](../../.claude/agents/results-analyst.md) listo
>    para que el coach lo invoque cuando provea PDFs y DB esté disponible.
> 4. Comandos exactos para el coach.

---

## 1. Resumen ejecutivo

- **4 válidas** en calendario regular hasta la fecha (V-I Sevilla 31-ene, V-II
  Ginebra 28-feb, V-III La Cumbre 19-abr, V-IV Cali 17-may). Una quinta
  pendiente: CD Ginebra 26-jun + V-V Palmira 01-ago + V-VI Roldanillo 12-sep +
  V-VII Yumbo 18-oct.
- **Solo V-IV con PDFs en el repo** (`docs/10-race-results/snapshots/`).
- **Smoke test del módulo: 305/305 ✓** en 25.25 s (`tests/services/race/` +
  `test_ingest_race_cli.py` + `test_ingest_race_cli_gaps.py` +
  `test_privacy_audit_race.py`).
- **Dry-run V-IV exitoso**: el parser detecta 26 categorías, 227 corredores,
  10 TyR, 16 TyR únicos en GENERAL, suma puntos TyR V-IV = 200 (coincide con
  oracle [`edge-cases.md`](./edge-cases.md) §5).
- **Próximo paso operativo**: coach provee PDFs V-I/II/III → ejecutar CLI
  ingest secuencial → analytics agregados de temporada.

---

## 2. Estado por válida

| Válida | Fecha       | Sede       | PDF en repo | Ingestada en DB | Notas |
|--------|-------------|------------|-------------|------------------|-------|
| I      | 2026-01-31  | Sevilla    | ⏳          | ⏳               | Coach debe descargar de la Federación y proveer RESULTADOS + GENERAL |
| II     | 2026-02-28  | Ginebra    | ⏳          | ⏳               | Idem |
| III    | 2026-04-19  | La Cumbre  | ⏳          | ⏳               | Idem |
| IV     | 2026-05-17  | Cali       | ✅          | ⏳               | LISTA. Dry-run en §3 |
| CD     | 2026-06-26  | Ginebra    | —           | —                | Aún no se corre (calendario CLAUDE.md) |
| V      | 2026-08-01  | Palmira    | —           | —                | Idem |
| VI     | 2026-09-12  | Roldanillo | —           | —                | Idem |
| VII    | 2026-10-18  | Yumbo      | —           | —                | Idem |

---

## 3. Dry-run Válida IV (script `/tmp/race_backfill_dryrun.py`)

> Output literal del dry-run ejecutado el 2026-05-19, sin DB real (solo
> parser + normalizer). Nombres TyR enmascarados `T. Apellido`
> (política `_mask_name` del CLI). Los PDFs son públicos por la federación,
> pero el reporte que se difunda aplica masking por consistencia.

```
======================================================================
DRY-RUN BACKFILL VÁLIDA IV — sin DB real
======================================================================
RESULTADOS: valida_iv_2026_resultados.pdf
GENERAL:    valida_iv_2026_general.pdf

## Event Header detectado
  valida_num : 4
  location   : CALI
  event_date : 2026-05-17
  raw_text   : VALIDA IV CALI MAYO 17 DE 2026

## RESULTADOS (Válida IV)
  categorías detectadas : 26
  codes                 : ELITE_F, ELITE_M, INF_A, INF_A_F, INF_B, INF_B_F,
                          JUN_F, JUN_M, MAS_A, MAS_B1, MAS_B2, MAS_C1,
                          MAS_C2, MAS_D, MAS_F, PJUV_A, PJUV_A_F, PJUV_B,
                          PJUV_B_F, PRE_A, PRE_A_F, PRE_B, PRE_B_F, PROMO,
                          TET_CP, TET_SP
  filas totales         : 227

## TyR detectados en RESULTADOS: 10
  (esperado por oracle edge-cases §5: 10)

  | Cat       | Bib  | Nombre (mask) | Tiempo  | Status        |
  |-----------|------|---------------|---------|---------------|
  | ELITE_M   |   10 | J. Garcia     | —       | -1 VUELTA     |
  | INF_A     |  407 | M. Anaya      | 0:37:43 | FINISHED      |
  | INF_A     |  426 | M. Montoya    | —       | dnf           |
  | INF_A_F   | 1257 | S. Gomez      | 1:03:15 | FINISHED      |
  | INF_A_F   | 1259 | E. Bonilla    | 1:13:52 | FINISHED      |
  | INF_B     |  362 | J. García     | 0:43:51 | FINISHED      |
  | PJUV_A_F  |  904 | M. Delgado    | 1:01:41 | FINISHED      |
  | PJUV_A_F  |  906 | I. Batero     | 0:59:05 | FINISHED      |
  | PRE_B     |  718 | J. Ortiz      | 0:18:37 | FINISHED      |
  | TET_CP    |  553 | T. Cardona    | 0:04:49 | FINISHED      |

## Warnings que se generarían en ingest real: 1
  - tiempo_anomalo bib=424 cat=INF_A time_ms=273000 (threshold=1500000)

## GENERAL (acumulado temporada)
  categorías detectadas : 26
  filas-temporada       : 345
  corredores únicos     : 345
  TyR únicos temporada  : 16 (esperado oracle §5.1: 16)

## TyR históricos que NO corrieron V-IV: 6
  (corrieron alguna de V-I/II/III pero faltaron a V-IV)

  | Cat       | Bib  | Nombre (mask) | Puntos I-IV          |
  |-----------|------|---------------|----------------------|
  | PJUV_A    |  609 | S. Valencia   | 25 33 0 0            |
  | PJUV_A    |  611 | N. Lopez      | 11 0 0 0             |
  | PRE_A     |  808 | S. Molano     | 27 19 30 0           |
  | PROMO     | 1319 | H. Giraldo    | 0 1 25 0             |
  | TET_SP    | 1410 | I. Romero     | 0 0 13 0             |
  | TET_SP    | 1414 | M. Bohorquez  | 0 0 15 0             |

## EventMeta que se construiría (pre-ingest, pre-CLI prompts)
  season           : 2026
  copa_code        : copa_valle
  valida_num       : 4
  name             : Válida IV Cali
  event_date       : 2026-05-17
  location         : Cali
  climate          : <PROMPT al coach>
  temperature_c    : <PROMPT al coach>
  surface_condition: <PROMPT al coach>
  altitude_msnm    : <PROMPT al coach>
  weather_notes    : <PROMPT al coach>

## IngestReport simulado (lo que retornaría ingest_event)
  event_id           : <auto>
  series_id          : <auto>
  competitors_created: ~345 (primer ingest)
  competitors_updated: 0 (primer ingest)
  results_inserted   : 227
  results_skipped    : 0 (primer ingest)
  tyr_count          : 10
  warnings           : 1

## Pre-analytics
  Suma puntos TyR V-IV : 200 (oracle §5: 200)
  Mejor posición TyR   : P3 en PJUV_A_F (I. Batero)

======================================================================
DRY-RUN OK — módulo LISTO para ingest real
======================================================================
```

### 3.1 Verificación cruzada con oracle [`edge-cases.md`](./edge-cases.md)

| Métrica                              | Oracle | Dry-run | Match |
|--------------------------------------|-------:|--------:|:-----:|
| Categorías RESULTADOS                |     26 |      26 | ✓ |
| Filas RESULTADOS                     |    227 |     227 | ✓ |
| TyR en RESULTADOS                    |     10 |      10 | ✓ |
| TyR únicos GENERAL temporada         |     16 |      16 | ✓ |
| TyR históricos que NO corrieron V-IV |      6 |       6 | ✓ |
| Suma puntos TyR V-IV                 |    200 |     200 | ✓ |
| Warnings tiempo anómalo (V-IV)       |      1 |       1 | ✓ |

---

## 4. TyR únicos detectables en V-IV (oracle público)

Los **10 corredores TyR** que sí corrieron V-IV — fuente
[`edge-cases.md`](./edge-cases.md) §5. Los nombres están en este reporte
porque los PDFs son publicación oficial de la Federación Colombiana de
Ciclismo Liga del Valle (Ley 1581/2012 art. 6 inc. b), conforme política
[`privacy-audit.md`](./privacy-audit.md) §6. Sin embargo, cualquier reporte
que se difunda fuera del coach debe usar masking (§5 más abajo).

| Cat        | Bib  | Nombre completo (raw PDF)         | Pos | Tiempo        | Pts |
|------------|------|-----------------------------------|----:|---------------|----:|
| `TET_CP`   | 553  | Thiago Duque Cardona              |   4 | 0:04:49       |  30 |
| `PRE_B`    | 718  | Juan David Giraldo Ortiz          |  15 | 0:18:37       |   7 |
| `INF_A_F`  | 1257 | Sofia Gomez                       |   6 | 1:03:15       |  25 |
| `INF_A_F`  | 1259 | Eileen Sophia Vargas Bonilla      |   7 | 1:13:52       |  23 |
| `INF_A`    | 407  | Miguel Angel Anaya                |   5 | 0:37:43       |  27 |
| `INF_A`    | 426  | Matías Montoya                    |  24 | DNF           |   1 |
| `INF_B`    | 362  | Jostin Villamizar García          |  11 | 0:43:51       |  15 |
| `PJUV_A_F` | 904  | Mariana Coronado Delgado          |   4 | 1:01:41       |  30 |
| `PJUV_A_F` | 906  | Isabel Cristhina Quiñones Batero  |   3 | 0:59:05       |  33 |
| `ELITE_M`  | 10   | Juan Diego Garcia                 |  14 | (-1 VUELTA)   |   9 |

Los **6 TyR históricos** que no corrieron V-IV (fuente
[`edge-cases.md`](./edge-cases.md) §5.1):

| Cat        | Bib  | Nombre completo (raw PDF)         | I  | II | III | IV | Total |
|------------|------|-----------------------------------|---:|---:|----:|---:|------:|
| `TET_SP`   | 1414 | Mathiw Bohorquez                  |  0 |  0 |  15 |  0 |    15 |
| `TET_SP`   | 1410 | Ihsan Garces Romero               |  0 |  0 |  13 |  0 |    13 |
| `PRE_A`    | 808  | Samuel Anaya Molano               | 27 | 19 |  30 |  0 |    76 |
| `PJUV_A`   | 609  | Samuel Ortiz Valencia             | 25 | 33 |   0 |  0 |    58 |
| `PJUV_A`   | 611  | Nicolas Segura Lopez              | 11 |  0 |   0 |  0 |    11 |
| `PROMO`    | 1319 | Héctor Eduardo Giraldo Ramírez    |  0 |  1 |  25 |  0 |    26 |

---

## 5. Hallazgos analíticos preliminares (sobre V-IV solamente)

> Estos hallazgos se derivan exclusivamente del dry-run V-IV. Una vez
> ingestadas V-I, V-II, V-III en DB, el comando `analyze ranking --season 2026`
> generará el ranking oficial agregado del club. Los hallazgos aquí son
> snapshots — no sustituyen analytics agregados que requieren DB real.

- **Mejor posición TyR en V-IV**: P3 en `PJUV_A_F` — Isabel Cristhina
  Quiñones Batero (bib 906), tiempo 0:59:05, 33 puntos. Único podio del club
  en V-IV.
- **Categoría TyR con más participantes en V-IV**: `INF_A` (2: bibs 407 y 426)
  empatada con `INF_A_F` (2: bibs 1257 y 1259) y `PJUV_A_F` (2: bibs 904 y 906).
- **Tiempo más anómalo**: bib 424 INF_A — Matias Sabogal con `0:04:33`
  (273 000 ms). NO es TyR (club Fundación Acti-Vida), pero el ingestor
  reportará warning `tiempo_anomalo bib=424 cat=INF_A time_ms=273000
  tier=menores`. Documentado en
  [`edge-cases.md`](./edge-cases.md) §4.2 — probable error de digitación
  federación (debería ser `0:40:33` o `0:43:33`); la posición y puntos son
  válidos.
- **TyR DNF/(-1 VUELTA) en V-IV**: 2 casos — INF_A bib 426 (Matías Montoya)
  con DNF, ELITE_M bib 10 (Juan Diego Garcia) con `(-1 VUELTA)`. Ambos
  reciben 1 y 9 puntos respectivamente. Sin filtrar de la regresión de
  `projection()` porque tienen `status != FINISHED` y `time_seconds=NULL` —
  el analytics module respeta este filtro nativamente.
- **6 riders TyR históricos sin participación V-IV** (bibs 1414, 1410, 808,
  609, 611, 1319). Razones plausibles a verificar con el coach: lesión,
  conflicto escolar (mayo es período de exámenes en Colombia), cambio de club,
  o desinterés temporal. Acción: registrar en spreadsheet de seguimiento
  individual del coach (fuera del scope del módulo race).

---

## 6. Comandos para el coach (cuando tenga DB Hostinger + PDFs I-III)

### 6.1 Preparación inicial (una sola vez)

```bash
cd "/Users/juadiga/Documents/Personal/Trocha y Ruta/me/backend"
source .venv/bin/activate

# 1. Confirmar variables MySQL Hostinger en .env (MYSQL_HOST, MYSQL_USER, etc.)
# 2. Aplicar migración delta del módulo race
alembic upgrade head

# 3. Seed de las 26 categorías oficiales Copa Valle
PYTHONPATH=. python scripts/seed_race_categories.py
```

### 6.2 Smoke test pre-ingest (sin tocar PDFs reales)

```bash
# Verifica que el módulo está sano antes de ingerir nada
cd backend && PYTHONPATH=. pytest tests/services/race/ \
    tests/test_ingest_race_cli.py tests/test_ingest_race_cli_gaps.py \
    tests/test_privacy_audit_race.py --tb=short -q
# Esperado: "305 passed in <30s"
```

### 6.3 Ingest secuencial V-I → V-II → V-III → V-IV

```bash
# Para cada válida, ubicar los 2 PDFs (RESULTADOS + GENERAL) y ejecutar:

# Válida I (Sevilla 31-ene-2026) — coach provee paths reales
PYTHONPATH=. python scripts/ingest_race.py ingest \
    --results <PATH_VI_RESULTADOS.pdf> \
    --general <PATH_VI_GENERAL.pdf>
# El CLI preguntará: clima, temperatura, superficie, msnm, notas + matches TyR

# Válida II (Ginebra 28-feb-2026)
PYTHONPATH=. python scripts/ingest_race.py ingest \
    --results <PATH_VII_RESULTADOS.pdf> \
    --general <PATH_VII_GENERAL.pdf>

# Válida III (La Cumbre 19-abr-2026)
PYTHONPATH=. python scripts/ingest_race.py ingest \
    --results <PATH_VIII_RESULTADOS.pdf> \
    --general <PATH_VIII_GENERAL.pdf>

# Válida IV (Cali 17-may-2026) — PDFs ya en repo
PYTHONPATH=. python scripts/ingest_race.py ingest \
    --results docs/10-race-results/snapshots/valida_iv_2026_resultados.pdf \
    --general  docs/10-race-results/snapshots/valida_iv_2026_general.pdf
```

> **Tip**: durante cada ingest el CLI mostrará top-3 candidatos para cada
> rider TyR sin match previo. Coach confirma `1`/`2`/`3`/`skip`/`new`. La
> decisión queda persistida — futuras válidas reusan el match sin re-preguntar.

### 6.4 Analytics post-backfill

```bash
# Ranking agregado de la temporada (output también a archivo .md)
PYTHONPATH=. python scripts/ingest_race.py analyze ranking \
    --season 2026 --output reports/ranking_temporada_2026.md

# Listar riders TyR sin match a athletes
PYTHONPATH=. python scripts/ingest_race.py riders list --tyr-only --unmatched

# Evolución individual de un competidor TyR
PYTHONPATH=. python scripts/ingest_race.py analyze evolution \
    --competitor-name "Isabel Cristhina Quiñones Batero"

# Gap al podio por categoría
PYTHONPATH=. python scripts/ingest_race.py analyze gap \
    --category-code PJUV_A_F --season 2026
```

### 6.5 Pre-Válida V (Palmira 2026-08-01) — proyección

```bash
# Proyección de próxima válida (advertencia confidence:low si n<5)
PYTHONPATH=. python scripts/ingest_race.py analyze projection \
    --competitor-name "Thiago Duque Cardona" --next-valida 5
```

---

## 7. Próximos pasos

- [ ] **Coach provee PDFs** RESULTADOS + GENERAL para Válidas I, II, III
  (descarga oficial de Federación Liga del Valle).
- [ ] **DB Hostinger en estado correcto**: `alembic upgrade head` aplicado y
  `seed_race_categories.py` ejecutado.
- [ ] **Ingest secuencial** vía CLI interactivo (§6.3) confirmando matches
  TyR con top-3 ranking.
- [ ] **Generar ranking agregado temporada** con
  `analyze ranking --season 2026 --output ranking_2026.md`.
- [ ] **Pre-V-V Palmira**: correr `analyze projection --next-valida 5` para
  cada TyR. Si la mayoría retorna `confidence:low` (lo más probable con n=4),
  documentar tendencia tentativa al coach sin presentar como predicción
  cerrada.
- [ ] **Pre-CD Ginebra (26-jun)**: si se ingesta CD, usar `valida_num=99`
  (decisión de diseño consolidada — §3.2 [`design.md`](./design.md)).
- [ ] **Documentar decisiones del coach** sobre los 6 TyR ausentes de V-IV
  (lesión / escolar / cambio de club) en spreadsheet del coach (fuera del
  scope del módulo race).

---

## 8. Trazabilidad

| Concepto                          | Origen                                         |
|-----------------------------------|------------------------------------------------|
| Conteos esperados (oracle)        | [`edge-cases.md`](./edge-cases.md) §5 y §5.1   |
| Política de privacidad            | [`privacy-audit.md`](./privacy-audit.md) §6    |
| Test plan + cobertura             | [`qa.md`](./qa.md)                             |
| Diseño schema + analytics         | [`design.md`](./design.md)                     |
| Pasos del módulo                  | [`workflow.md`](./workflow.md) Paso 9          |
| Agente operativo                  | [`results-analyst.md`](../../.claude/agents/results-analyst.md) |
| Script dry-run usado en §3        | `/tmp/race_backfill_dryrun.py` (local, no en repo) |
| PDFs Válida IV                    | `docs/10-race-results/snapshots/valida_iv_2026_*.pdf` |
| Fixtures tests                    | `backend/tests/fixtures/race/valida_iv_2026_*.pdf` |

---

## 9. Changelog

| Fecha       | Cambio                                                       |
|-------------|--------------------------------------------------------------|
| 2026-05-19  | Documento creado en Paso 9. Dry-run V-IV ✓ (10 TyR, 200 pts, 1 warning). 305/305 tests ✓. Pendiente ingest real con MySQL Hostinger + PDFs V-I/II/III. |
