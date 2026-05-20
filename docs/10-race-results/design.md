# Diseño — Módulo Resultados Copa Valle XCO

**Fecha:** 2026-05-19
**Fase:** 1.7
**Estado:** Diseño aprobado, pendiente kickoff

---

## 1. Objetivo

Cargar de forma incremental los resultados de cada válida de la Copa Valle de Ciclomontañismo (XCO) a partir de los PDFs oficiales (RESULTADOS por evento + GENERAL acumulado), filtrar y marcar los corredores del Club Trocha y Ruta, persistir en MySQL para análisis longitudinales, y ofrecer cuatro analíticas: evolución por atleta, gap al podio, ranking del club y proyección de próxima válida.

La operación es CLI-only (no UI, no endpoint REST en este milestone). Se ejecuta por el entrenador desde la consola con un agente especializado Opus que conduce el flujo interactivo.

---

## 2. Decisiones de scope (cerradas)

| Decisión | Valor |
|---|---|
| Storage | MySQL Hostinger (DB existente) |
| FK a `athletes` | Opcional, solo TyR matcheados |
| Filtro corredores | Guardar todos, flag `is_trocha_y_ruta` |
| Categoría | Por resultado (no por rider) |
| Match athletes | Sugerir top-3, coach confirma siempre |
| Match club TyR | Fuzzy `rapidfuzz` ≥85 vs variantes |
| Ingest | CLI Opus, PDFs locales |
| Condiciones de carrera | Captura manual interactiva |
| Backfill | Válidas I–IV + nuevas |
| Deps | pdfplumber + rapidfuzz + pandas |
| Predicción | Regresión lineal simple sobre puntos/posición histórica |

---

## 3. Modelo de datos

### 3.1 `race_categories` (catálogo)

Seed inicial con 22 categorías oficiales Copa Valle 2026.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `code` | varchar(40) UNIQUE | `TET_SP`, `TET_CP`, `PRE_A`, `PRE_B`, `PRE_A_F`, `PRE_B_F`, `INF_A`, `INF_B`, `INF_A_F`, `INF_B_F`, `PJUV_A`, `PJUV_B`, `PJUV_A_F`, `PJUV_B_F`, `JUN_M`, `JUN_F`, `ELITE_M`, `ELITE_F`, `PROMO`, `MAS_A`, `MAS_B1`, `MAS_B2`, `MAS_C1`, `MAS_C2`, `MAS_D`, `MAS_F` |
| `name` | varchar(80) | "Teteros con Pedales", etc. |
| `gender` | enum(`M`, `F`, `MIXED`) | |
| `age_min` | int NULL | Heurístico (Teteros≤5, Preinf 6-8, Inf 9-12, Prejuv 13-14, Jun 15-16, Elite 17+, Master según subcategoría) |
| `age_max` | int NULL | |
| `tier` | enum(`menores`, `juvenil`, `adulto`, `master`) | Para filtros analytics |

### 3.2 `race_events`

Un registro por válida.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `season` | smallint | 2026 |
| `copa_code` | varchar(40) | `copa_valle` |
| `valida_num` | tinyint | 1..7 + `CD` (Campeonato Departamental, usar 99) |
| `name` | varchar(120) | "Válida IV Cali" |
| `event_date` | date | |
| `location` | varchar(80) | "Cali", "Roldanillo"... |
| `climate` | varchar(60) NULL | "soleado", "nublado parcial"... |
| `temperature_c` | decimal(4,1) NULL | |
| `surface_condition` | enum(`seca`,`humeda`,`barro`,`lluvia`,`mixta`) NULL | |
| `altitude_msnm` | smallint NULL | |
| `weather_notes` | text NULL | |
| `pdf_results_filename` | varchar(255) NULL | trazabilidad |
| `pdf_general_filename` | varchar(255) NULL | |
| `ingested_at` | datetime | |

Unique: `(season, copa_code, valida_num)`.

### 3.3 `riders`

Corredores (todos, no solo TyR). Persona física a lo largo de temporadas.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `full_name_raw` | varchar(120) | tal cual PDF |
| `full_name_normalized` | varchar(120) | lower + unidecode + trim |
| `city_raw` | varchar(80) NULL | |
| `club_raw` | varchar(120) NULL | |
| `club_normalized` | varchar(120) NULL | lower + unidecode |
| `is_trocha_y_ruta` | bool | true si fuzzy club ≥85 |
| `athlete_id` | int NULL FK→`athletes.id` | solo si TyR + match confirmado |
| `first_seen_event_id` | int FK→`race_events.id` | |
| `created_at` | datetime | |
| `updated_at` | datetime | |

Index: `(full_name_normalized)`, `(is_trocha_y_ruta)`, `(athlete_id)`.

### 3.4 `race_results`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `event_id` | int FK→`race_events.id` | |
| `category_id` | int FK→`race_categories.id` | |
| `rider_id` | int FK→`riders.id` | |
| `bib_number` | varchar(10) NULL | dorsal |
| `position` | smallint NULL | NULL si DNF/DSQ |
| `time_seconds` | int NULL | NULL si DNF/DSQ |
| `laps_down` | tinyint default 0 | `-1 VUELTA`→1, `-2 VUELTAS`→2 |
| `status` | enum(`FINISHED`,`DNF`,`DSQ`,`MINUS_LAPS`) | |
| `points` | smallint | |
| `created_at` | datetime | |

Unique: `(event_id, category_id, rider_id)`.
Index: `(event_id, position)`, `(rider_id, event_id)`, `(category_id, points DESC)`.

### 3.5 VIEW `season_standings`

```sql
CREATE OR REPLACE VIEW season_standings AS
SELECT
  e.season,
  r.category_id,
  r.rider_id,
  SUM(r.points) AS total_points,
  COUNT(*) AS races_run,
  SUM(CASE WHEN r.position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
  SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) AS wins
FROM race_results r
JOIN race_events e ON e.id = r.event_id
GROUP BY e.season, r.category_id, r.rider_id;
```

---

## 4. Servicios backend

```
backend/app/services/race/
├── __init__.py
├── pdf_parser.py     # pdfplumber, extrae bloques por categoría
├── normalizer.py     # nombre/club/tiempo/status normalize
├── matcher.py        # rapidfuzz vs athletes existentes
├── ingestor.py       # transacción atómica event+results+riders
└── analytics.py      # 4 funciones de análisis
```

### 4.1 pdf_parser

- `parse_results_pdf(path) -> ResultsDocument`
- `parse_general_pdf(path) -> GeneralDocument`
- Estrategia: usar `pdfplumber.extract_tables()` por página. Detecta header `CAT: <NOMBRE>` para agrupar filas. Maneja header repetido entre páginas y filas multi-línea (nombres truncados).
- Validación: descarta filas sin dorsal numérico o sin posición válida.
- Warnings: tiempo anómalo (Matias Sabogal infantil A muestra `0:04:33` siendo categoría que corre >30min → flag).

### 4.2 normalizer

- `normalize_name(s)`: lower + `unidecode` + collapse spaces + strip puntuación
- `normalize_club(s)`: idem
- `is_trocha_y_ruta(club)`: `rapidfuzz.fuzz.ratio` ≥85 vs `["trocha y ruta", "club trocha y ruta", "trochy ruta", "trochayruta"]`
- `parse_time(s)`: `H:MM:SS` → segundos. `DNF`, `DSQ`, `(-N VUELTA[S])` → status
- `parse_status(time_str)`: retorna tupla `(status, time_seconds, laps_down)`

### 4.3 matcher

- `match_athletes(rider, athletes_list, threshold=0.90) -> list[MatchCandidate]`
- Solo se invoca si `rider.is_trocha_y_ruta`
- Combina `fuzz.token_set_ratio(name)` + boost si categoría compatible con `age_decimal` calculada de `athletes.birth_date`
- Retorna top-3 con score. Coach confirma siempre.

### 4.4 ingestor

- Transacción única por válida
- Pasos: upsert `event` → upsert `riders` (por `full_name_normalized + club_normalized`) → insert `race_results`
- Idempotente: re-ingest mismo PDF no duplica (clave unique `(event_id, category_id, rider_id)`)

### 4.5 analytics

| Función | Retorna |
|---|---|
| `athlete_progression(rider_id)` | DataFrame `[event, valida, position, time_seconds, points, gap_to_winner_pct]` |
| `podium_gap(category_id, season)` | Para cada corredor TyR de la categoría: `gap_to_p1_seconds`, `gap_to_p3_seconds`, `gap_pct` por válida |
| `club_ranking(season)` | Por categoría: total points TyR, podios, wins, riders activos |
| `projection(rider_id, next_event_id)` | Regresión lineal sobre `time_seconds` y `position` históricas; retorna `expected_position`, `confidence` |

---

## 5. CLI

`backend/scripts/ingest_race.py` (typer):

```
ingest_race.py ingest \
  --results PATH \
  --general PATH \
  [--copa copa_valle] \
  [--valida N] \
  [--non-interactive]   # para tests

ingest_race.py analyze evolution --rider-name "Thiago Duque"
ingest_race.py analyze gap --category-code INF_A --season 2026
ingest_race.py analyze ranking --season 2026
ingest_race.py analyze projection --rider-name "Thiago Duque" --next-valida 5
ingest_race.py analyze export --season 2026 --output reports/copa_2026.md
```

---

## 6. Agentes

Los agentes Opus orquestan ejecución por fase. Definidos como subagentes locales en `.claude/agents/` o invocados vía `Agent` tool con `model: opus`.

| Agente | Rol | Fase |
|---|---|---|
| `data-analyst` (nuevo, Opus) | Diseña pipeline, valida modelo, decide normalización, conduce ingest interactivo, ejecuta analytics y narra hallazgos | PASOS 1, 4, 5, 9 |
| `fastapi-architect` (existente, override a Opus) | Define modelos SQLAlchemy, migración Alembic, schemas Pydantic si surgen | PASO 2 |
| `quality-engineer` (global, Opus) | Test plan, fixtures PDF, cobertura | PASO 7 |
| `data-privacy-guard` (local, Opus override) | Audita exposición datos de menores (nombres en logs, reportes) | PASO 8 |

Todos invocados con `model: opus` en el Agent tool (override sobre frontmatter).

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| PDFs cambian de formato en futuras válidas | Parser tolerante: detecta header `CAT:` flexible; tests con PDFs Válidas I-IV asegura cobertura |
| Mismo nombre, distintos riders (homónimos) | Match athletes pregunta siempre; rider único por `(name_norm, club_norm)` para reducir colisión |
| Datos de menores filtrados en logs | `data-privacy-guard` audita; logs DEBUG nunca incluyen nombres completos en producción |
| Tiempos erróneos en PDF origen | Warning automático si `time_seconds` está fuera de rango categoría (validación rango por `tier`) |
| Backfill incompleto (I-III sin PDFs) | Coach provee PDFs manualmente; agente reporta válidas faltantes |
| Predicción imprecisa con n=4 | Marcar `confidence: low` cuando n<5; mostrar intervalo de confianza |
