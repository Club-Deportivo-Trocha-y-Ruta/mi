# Edge Cases — Válida IV Copa Valle 2026 (Paso 1)

**Fecha:** 2026-05-19
**Agente:** `data-analyst` (Opus)
**Insumos:** `snapshots/valida_iv_2026_resultados.pdf` (10 págs) + `snapshots/valida_iv_2026_general.pdf` (12 págs)
**Estado workflow:** [`workflow.md`](./workflow.md) — Paso 1 cerrado, listo para Paso 2.

> Este documento valida [`design.md`](./design.md) contra los PDFs oficiales de la
> Válida IV y captura todos los edge cases observados. Sirve como **oracle de tests**
> para Paso 3 (parser) y Paso 4 (ingestor).
>
> No modifica `design.md`. Cualquier delta queda registrado aquí.

---

## 1. Resumen ejecutivo

- **26 categorías observadas** en Válida IV (RESULTADOS y GENERAL coinciden). El `design.md §3.1` declara textualmente "22 categorías oficiales" pero enumera 26 codes; la discrepancia es un error tipográfico del design — **no hay categorías observadas fuera del catálogo de 26 codes ni codes del catálogo sin observación**. Recomendación: ajustar texto del design "22" → "26" en una sub-edición posterior (no en este paso).
- **227 corredores totales** parseados en RESULTADOS (filas válidas con dorsal + posición + tiempo/status + puntos). El workflow declara `≈287` en `§3 PASO 3` y `§4 PASO 4`; la diferencia (60) se explica porque el GENERAL tiene 339 filas-temporada (acumula riders que corrieron alguna I-IV pero no necesariamente las cuatro). El target ≈287 del workflow probablemente venía de una estimación previa — el conteo actual real es **227 finalistas** en V-IV.
- **10 corredores Trocha y Ruta detectados en RESULTADOS Válida IV** (oracle test de fuzzy ≥85). En GENERAL aparecen **16 riders TyR únicos en la temporada 2026** (los 10 anteriores + 6 que no corrieron V-IV pero acumulan puntos de I-III).
- **Condiciones inferibles del PDF:** ubicación `CALI`, fecha `MAYO 17 DE 2026`, válida número `IV`. Climate / temperature / surface / altitude / weather_notes **no están en el PDF** — se capturan vía CLI interactivo (workflow §6.2 paso 3).
- **Filtro de fuzzy ≥85 vs variantes TyR funciona al 100%**: las 10 filas TyR de RESULTADOS dan score 100 con `rapidfuzz.fuzz.partial_ratio` contra `"trocha y ruta"`. No hay falsos positivos (no hay clubs como "Trocha Vieja" o "Ruta Larga" que disparen el umbral).

---

## 2. Mapping codes ↔ texto PDF (26/26 sin ambigüedad)

| Code (design §3.1) | Texto literal `CAT:` en PDF | Regla de detección (case-insensitive, sobre header normalizado) |
|---|---|---|
| `TET_SP` | `TETEROS SIN PEDALES` | `== "teteros sin pedales"` |
| `TET_CP` | `TETEROS CON PEDALES` | `== "teteros con pedales"` |
| `PRE_A` | `PREINFANTIL A` | `== "preinfantil a"` (sin `femenino` al final) |
| `PRE_A_F` | `PREINFANTIL A FEMENINO` | `== "preinfantil a femenino"` |
| `PRE_B` | `PREINFANTIL B` | `== "preinfantil b"` (sin `femenino`) |
| `PRE_B_F` | `PREINFANTIL B FEMENINO` | `== "preinfantil b femenino"` |
| `INF_A` | `INFANTIL A` | `== "infantil a"` (sin `femenino`) |
| `INF_A_F` | `INFANTIL A FEMENINO` | `== "infantil a femenino"` |
| `INF_B` | `INFANTIL B` | `== "infantil b"` (sin `femenino`) |
| `INF_B_F` | `INFANTIL B FEMENINO` | `== "infantil b femenino"` |
| `PJUV_A` | `PREJUVENIL A` | `== "prejuvenil a"` (sin `femenino`) |
| `PJUV_A_F` | `PREJUVENIL A FEMENINO` | `== "prejuvenil a femenino"` |
| `PJUV_B` | `PREJUVENIL B` | `== "prejuvenil b"` (sin `femenino`) |
| `PJUV_B_F` | `PREJUVENIL B FEMENINO` | `== "prejuvenil b femenino"` |
| `JUN_M` | `JUNIOR` | `== "junior"` (sin `femenino`) |
| `JUN_F` | `JUNIOR FEMENINO` | `== "junior femenino"` |
| `ELITE_M` | `ELITE` | `== "elite"` (sin `femenino`) |
| `ELITE_F` | `ELITE FEMENINO` | `== "elite femenino"` |
| `PROMO` | `PROMOCIONAL` | `== "promocional"` |
| `MAS_A` | `MASTER A` | `== "master a"` |
| `MAS_B1` | `MASTER B1` | `== "master b1"` |
| `MAS_B2` | `MASTER B2` | `== "master b2"` |
| `MAS_C1` | `MASTER C1` | `== "master c1"` |
| `MAS_C2` | `MASTER C2` | `== "master c2"` |
| `MAS_D` | `MASTER D` | `== "master d"` |
| `MAS_F` | `MASTER FEMENINO` | `== "master femenino"` |

### 2.1 Regla canónica para `parse_category_header(s)` (sugerida para Paso 3)

```python
def parse_category_header(s: str) -> Optional[str]:
    # s viene como "CAT: <NOMBRE>" — extraer el nombre, normalizar
    m = re.match(r"^\s*CAT:\s*(.+?)\s*$", s)
    if not m:
        return None
    header = unidecode(m.group(1)).lower().strip()
    header = re.sub(r"\s+", " ", header)  # colapsar espacios
    return HEADER_TO_CODE.get(header)
```

**Clave técnica:** la distinción `INF_A` vs `INF_A_F` (y todas las masculino/femenino) se resuelve por **igualdad exacta** sobre el header normalizado, no por keyword "FEMENINO". Si una válida futura usa variantes como `INFANTIL A (FEMENINO)` o `INF A FEM`, el mapping debe ampliarse — esto es candidato a regex tolerante pero por ahora la igualdad estricta es suficiente y previene falsos positivos.

---

## 3. Codes del catálogo no observados en Válida IV

**Ninguno.** Los 26 codes del catálogo `design.md §3.1` aparecen en RESULTADOS y/o GENERAL. La Válida IV (Cali) presentó participación completa del catálogo oficial.

> Nota para válidas futuras: si una categoría aparece en RESULTADOS pero **no** en GENERAL (o viceversa), el ingestor debe registrar warning. Esperamos por experiencia: categorías como `JUN_F` (1 sola corredora en V-IV) o `MAS_F` (2) pueden no convocar en alguna válida pequeña.

---

## 4. Edge cases (con cita textual)

### 4.1 Dorsal 1411 — Anomalía estructural confirmada

**Síntoma:** rider `1411 Dulce Maria Herrera` aparece en GENERAL Válida IV pero **no** en RESULTADOS Válida IV.

**Cita GENERAL (p1, línea 16):**
```
11 1411 Dulce Maria Herrera Roldanillo Club Súper Amigos Bike 0 0 27 0 27
```

**Interpretación:** las columnas `I II III IV Total` muestran `0 0 27 0 27` — la rider corrió y obtuvo 27 puntos en Válida III pero **no participó en Válida IV** (columna IV = 0). El total temporada (27) coincide. No es una anomalía del PDF — es un rider que sencillamente faltó a V-IV.

**Manejo en parser/ingestor:**
- El parser no debe crear `race_result` para `(event=V-IV, rider=1411)`.
- El GENERAL es **referencia secundaria** para construir el rider master (sirve para detectar `first_seen_event_id` y total temporada), pero las filas `race_results` provienen exclusivamente del RESULTADOS de cada válida.
- Sugerencia paso 4: warning informativo si un rider del GENERAL no tiene resultado V-X correspondiente y la columna `X != 0`. En este caso `IV=0`, así que es consistente.

### 4.2 Matias Sabogal — Tiempo anómalo `0:04:33` en INFANTIL A

**Cita RESULTADOS (p4, línea 9):**
```
9 424 Matias Sabogal La Cumbre Fundacion Acti-Vida 0:04:33 19
```

**Interpretación:** rango típico INF_A en esta válida es 33–65 min (`p1` 0:33:19 → `p23` 1:08:25). Un tiempo de 4 min 33 s es físicamente imposible — el rider hubiera promediado >300 km/h. Casi seguro **error de digitación**: probablemente debió ser `0:40:33` o `0:43:33`. La organización le otorgó 19 puntos (posición 9) consistente con un tiempo intermedio, lo que confirma que el tiempo capturado en el PDF está mal pero la posición es correcta.

**Manejo:**
- Parser: **NO descartar la fila** (la posición y puntos son válidos). Cargar el tiempo tal cual y emitir warning.
- Validación de rango por tier (workflow §7.2): `INFANTIL` debe correr entre 25–90 min. Si `time_seconds < 1500` (25 min) en tier `menores`/`juvenil`, marcar `time_anomaly=True` en el log de ingest (NO en producción).
- El UNIQUE `(event_id, category_id, rider_id)` impide duplicar — re-ingest con corrección requiere UPDATE explícito (decisión queda para Paso 7).
- **Sugerencia Paso 5 analytics:** `athlete_progression()` debería filtrar tiempos `time_anomaly` para no envenenar la regresión lineal de `projection()`. Alternativa: marcarlos con `points` válido pero `time_seconds=NULL`.

### 4.3 Ciudad / Club = "0" — Datos vacíos

**Cita RESULTADOS:**
```
p7: 4 1305 Andrés Felipe Rodríguez Díaz 0 0 1:24:56 30      (PROMOCIONAL)
p10: 6 529 Samuel Nuñez 0 0 1:08:30 25                      (PREJUVENIL B)
```

**Interpretación:** la organización registró `0` como placeholder cuando el rider no declaró ciudad ni club. Aparece en exactamente **2 filas** de Válida IV.

**Manejo en `normalize_club()` y `normalize_city()`:**
- Tratar `"0"` (string) como vacío: `city_raw = "", club_raw = ""`.
- Validación recomendada: `if club_raw_token.strip() in ("0", "-", "N/A", "")` → vacío.
- `is_trocha_y_ruta("")` → `False` (no entra al matcher).
- `rider.club_raw = NULL` permitido por schema (`design §3.3`).

### 4.4 Categoría duplicada FEMENINO / Mapping sin keyword

**Cita RESULTADOS (extracto):**
```
p2: CAT: PREINFANTIL A
p2: CAT: PREINFANTIL A FEMENINO
p4: CAT: INFANTIL A
p4: CAT: INFANTIL B
p5: CAT: ELITE FEMENINO
```

**Interpretación:** el sufijo `FEMENINO` aparece literal en el header. Los headers masculinos NO llevan sufijo `MASCULINO` ni `M` (excepto que `MASTER A`, `MASTER B1`, etc. usan letras directamente para distinguir tier de edad — no género).

**Regla canónica:** la igualdad exacta sobre header normalizado (ver §2.1) es **suficiente y unívoca**. NO usar regex con keyword `FEMENINO` (`"infantil a" in header`) porque `"INFANTIL A FEMENINO"` también contiene `"INFANTIL A"` como substring y dispararía colisión.

### 4.5 Artefacto kerning PDF — Ciudad/Club mezclados visualmente

**Cita RESULTADOS (p1 TETEROS SIN PEDALES, varias filas):**
```
3 1405 Valentina Escobar Durango SANTIAGO DE CCAlLuIb Olguita García 0:04:11 33
6 1406 Alan David Ararat Fernandez SANTANDER DEC QluUbIL UICRHRAEOA BIKERS 0:05:06 25
8 1413 Nicolás Camargo Salamanca SANTIAGO DE CCAlLuIb Olguita García 0:05:09 21
```

**Interpretación:** pdfplumber renderiza dos columnas adyacentes (`Ciudad`, `Club`) con sus caracteres intercalados cuando los anchos no calzan. Lo que **realmente** dice el PDF en cada celda separada:
- `Ciudad = "SANTIAGO DE CALI"`, `Club = "Club Olguita García"` → texto serializado `"SANTIAGO DE CCAlLuIb Olguita García"`.
- `Ciudad = "SANTANDER DE QUILICHAO"`, `Club = "Club URREA BIKERS"` → texto serializado `"SANTANDER DEC QluUbIL UICRHRAEOA BIKERS"`.

**Verificación cruzada con GENERAL** (mismas filas, sin distorsión a veces):
```
p1: 5 1405 Valentina Escobar DuranSgoANTIAGOC DluEb COAlgLuIita García 0 27 30 33 90
p1: 7 1406 Alan David Ararat FernanSdAeNzTANDECRlu bD EU RQRUEILAIC BHIKAEORS 0 23 0 25 48
```

GENERAL muestra el mismo artefacto. El problema es la extracción columna-a-columna mediante `page.extract_text()`. La solución:

**Manejo en `pdf_parser.py` (Paso 3):**
- Usar `page.extract_tables(table_settings=...)` con `vertical_strategy="lines"` o `"text"` y `horizontal_strategy="lines"` — pdfplumber detecta las celdas por las líneas/rulings y devuelve cada celda separada (sin interleave).
- Si `extract_tables` falla (PDF sin rulings explícitos), caer a `extract_words()` + reconstrucción de columnas por posición X.
- **NO confiar en `extract_text()` línea-por-línea** para el bloque ciudad+club.
- Validación cruzada para tests: el oracle TyR (sección 5) confirma 10 filas detectables porque "Yumbo" es un token corto que no se entrelaza con "Club Trocha y Ruta" — pero en producción **muchas filas non-TyR fallarán si no usamos `extract_tables`**.

### 4.6 Nombre pegado a ciudad (sin espacio intermedio)

**Cita RESULTADOS:**
```
p4: 13 406 Daniel Stephen Márquez VásquezSANTIAGO DE CIAnLdIependiente 0:45:57 11   (INFANTIL A)
p6: 3 906 Isabel Cristhina Quiñones BateroYumbo Club Trocha y Ruta 0:59:05 33        (PREJUV_A_F)
p6: 4 904 Mariana Coronado DelgaYduombo Club Trocha y Ruta 1:01:41 30 (en GENERAL)   (PREJUV_A_F)
p9: 5 2 Juan Fernando Monroy CerqueraTuluá Club Team Monroy 1:39:41 27               (ELITE)
```

**Interpretación:** cuando el apellido es largo y la celda Ciudad empieza, no hay espacio entre ellas en el `extract_text()`.

**Manejo:** mismo que §4.5 — `extract_tables()` separa por celda y elimina el problema. Si se usa fallback regex sobre texto plano, la heurística `[A-Za-záéíóúñ]+(?=[A-Z]{2,})` para detectar la frontera nombre→ciudad es frágil (rompería en nombres con mayúsculas).

### 4.7 Posiciones DNF / DSQ / MINUS_LAPS

**Citas RESULTADOS:**
```
p1 TET_SP : 11 1415 Matías Artunduaga SANTIAGO DE CCAlLuIb Olguita García (-1 VUELTA) 15
p1 PRE_A  : 6 813 Emmanuel Perez Yumbo Club BTT Recio Norte DNF 1
p4 INF_A  : 24 426 Matías Montoya Yumbo Club Trocha y Ruta DNF 1
p9 ELITE  : 14 10 Juan Diego Garcia Yumbo Club Trocha y Ruta (-1 VUELTA) 9
p9 ELITE  : 15 24 Esteban Ortega PASTO Otro (-2 VUELTAS) 7
p9 ELITE  : 18 14 José Alejandro Chala Chala Jamundí Independiente DSQ 1
```

**Patrones observados:**
- `(-1 VUELTA)` (singular), `(-2 VUELTAS)`, `(-3 VUELTAS)` (plural).
- `DNF`, `DSQ` literal.
- No vimos `DNS` (Did Not Start) en Válida IV, pero `design §3.4` no lo contempla — está OK porque DNS se traduce a ausencia de fila en RESULTADOS.

**Regla canónica `parse_time()` (sugerida Paso 3):**

```python
STATUS_RE = re.compile(r"^\(-(\d+)\s*VUELTAS?\)$", re.IGNORECASE)

def parse_time(raw: str) -> tuple[ResultStatus, Optional[int], int]:
    s = raw.strip().upper()
    if s == "DNF":    return ResultStatus.DNF,  None, 0
    if s == "DSQ":    return ResultStatus.DSQ,  None, 0
    if s == "DNS":    return ResultStatus.DNS,  None, 0   # futuro
    m = STATUS_RE.match(s)
    if m:             return ResultStatus.MINUS_LAPS, None, int(m.group(1))
    m = re.match(r"^(\d+):(\d{2}):(\d{2})$", raw.strip())
    if m:
        h, mm, ss = map(int, m.groups())
        return ResultStatus.FINISHED, h*3600 + mm*60 + ss, 0
    raise ValueError(f"Tiempo no parseable: {raw!r}")
```

> Si decidimos agregar `DNS` al enum, hay que actualizar `design §3.4`. Por ahora `design` solo lista 4 status (`FINISHED`, `DNF`, `DSQ`, `MINUS_LAPS`) — coherente con lo observado.

### 4.8 Dorsales no estándar — Todos numéricos en Válida IV

**Observación:** los 227 dorsales de Válida IV son **enteros** entre 1 y 1419, sin letras ni guiones. El schema `design §3.4` declara `bib_number varchar(10)` lo cual es prudente para tolerar futuras válidas con dorsales tipo `1A`/`E-23` (algunas federaciones lo usan).

**Manejo:** convertir a `str` al persistir (no `int`), preservar zero-padding si existe. El regex de fila debe aceptar `\d+` por ahora pero ser fácilmente reemplazable por `[A-Z0-9-]+`.

### 4.9 Headers repetidos entre páginas

**Cita RESULTADOS (cada página):**
```
COPA VALLE DE CICLOMONTAÑISMO
VALIDA IV CALI MAYO 17 DE 2026
RESULTADOS
CAT: <NOMBRE>          # solo si la página inicia categoría nueva
Ord N° Nombre completo Ciudad Club/Patrocinador Tiempo Puntos
```

**Manejo:**
- Las 3 primeras líneas son siempre las mismas (3 líneas fijas) y deben **descartarse** antes de procesar.
- La línea `Ord N° Nombre completo...` es header de tabla — descartar.
- El header `CAT: <NOMBRE>` puede o no repetirse según corte de página. **Truco**: si una página inicia con filas sin haber visto `CAT:` en esa página, **persistir el `current_cat`** de la página anterior. Ej: `INFANTIL B` (p4) continúa en p5 sin re-imprimir `CAT:`.
- Cita p4→p5 (INFANTIL B sigue):
```
p4 (final): 8 357 Juan Diego Londoño Gonzalez ...
p5 (inicio): 9 360 Nicolas Trullo Soto Jamundí ICL Training CAPF SAS 0:38:27 19
```

### 4.10 Línea espuria "0" entre páginas (artefacto separador)

**Cita GENERAL (p1→p2 transición):**
```
18 1410 Ihsan Garces Romero Yumbo Club Trocha y Ruta 0 0 13 0 13
0 COPA VALLE DE CICLOMONTAÑISMO
VALIDA IV CALI MAYO 17 DE 2026
CLASIFICACION GENERAL
```

**Interpretación:** la línea `0 COPA VALLE...` parece ser un "0" sobrante del separador de columnas pegado al inicio del header de página. El regex de fila `^\d+\s+\d+\s+` filtra esto solo (la línea no tiene un dorsal después del 0).

**Manejo:** descartar cualquier línea que matchee `^(COPA VALLE|VALIDA|RESULTADOS|CLASIFICACION|GENERAL|Ord N|ORD N)`, tolerando prefijo `\d+\s*` espurio.

### 4.11 Tildes y encoding — Aparentemente bien

**Observación:** los nombres como `Matías`, `García`, `Quiñones`, `Cuéllar` aparecen con tildes y eñes correctas. pdfplumber respeta UTF-8 sin problemas en estos PDFs.

**Manejo:**
- `normalize_name()` debe aplicar `unidecode` para comparación fuzzy (igualar `Matías` ≡ `Matias`).
- `full_name_raw` preserva tildes para mostrar.

### 4.12 Riders TyR en GENERAL que NO corrieron Válida IV (6 casos)

**Cita GENERAL:**
```
p1 TET_SP : 16 1414 Mathiw Bohorquez YUMBO TROCHA Y RUTA 0 0 15 0 15
p1 TET_SP : 18 1410 Ihsan Garces Romero Yumbo Club Trocha y Ruta 0 0 13 0 13
p2 PRE_A  : 6 808 Samuel Anaya Molano Yotoco Club Trocha y Ruta 27 19 30 0 76
p7 PJUV_A : 9 609 Samuel Ortiz Valencia Yumbo Club Trocha y Ruta 25 33 0 0 58
p7 PJUV_A : 17 611 Nicolas Segura Lopez Yumbo Club Trocha y Ruta 11 0 0 0 11
p8 PROMO  : 15 1319 Héctor Eduardo Giraldo Ramírez Yumbo Club Trocha y Ruta 0 1 25 0 26
```

**Interpretación:** estos 6 corredores TyR participaron en alguna Válida I-III pero **no** en V-IV (columna IV = 0). Confirman que el GENERAL es la fuente correcta para construir el **catálogo histórico de riders TyR de la temporada** (`first_seen_event_id`, `is_trocha_y_ruta`), incluso sin haber corrido la válida actual.

**Manejo Paso 4 (ingestor):**
- Al ingerir Válida IV, primero parsear el GENERAL → upsert de riders TyR con `is_trocha_y_ruta=True` y `first_seen_event_id` proyectado a partir de la primera columna no-cero.
- Luego parsear RESULTADOS V-IV → insert `race_results` solo para los que sí corrieron.
- Esto previene "perder" historia de un rider TyR que faltó a V-IV.

**Nota mayúsculas:** `Mathiw Bohorquez` aparece con club `TROCHA Y RUTA` (todo mayúsculas, sin "Club" prefijo). El fuzzy `partial_ratio("trocha y ruta", "trocha y ruta")` = 100 funciona post-normalización (`unidecode + lower`).

### 4.13 Doble corredor con apellido común "Yule Mendoza"

**Citas:**
```
p1 TET_SP  : 4 1401 Sebastian Yule Mendoza Jamundí Club Caña y Trapiche 0:04:28 30
p1 TET_CP  : 1 550 Sebastian Yule Mendoza Jamundí Club Caña y Trapiche 0:03:38 40
p2 PRE_B   : 16 702 Samuel Yule Mendoza Jamundí Club Caña y Trapiche 0:18:38 5
```

**Interpretación:** `Sebastian Yule Mendoza` aparece **dos veces** en la misma válida — en `TET_SP` (Teteros Sin Pedales, dorsal 1401) y `TET_CP` (Teteros Con Pedales, dorsal 550). Es el **mismo niño** corriendo dos categorías. Si UNIQUE es `(event_id, category_id, rider_id)`, esto funciona: dos `race_result` distintos para el mismo `rider_id`.

**Manejo:** el upsert de riders por `(full_name_normalized, club_normalized)` lo consolida correctamente como **un solo rider** con dos resultados.

**Caso adicional:** `Samuel Yule Mendoza` (dorsal 702, hermano) es persona distinta — el nombre completo difiere ("Sebastian" vs "Samuel"). El matcher no debe colapsarlos. Test recomendado.

### 4.14 Espacios dobles / múltiples en nombres

**Citas (extract_text rinde espacios consistentes):** no observamos espacios dobles internos en nombres ni en clubs en Válida IV. Sin embargo, la regla `re.sub(r"\s+", " ", s).strip()` en `normalize_name()` es defensiva para válidas futuras.

### 4.15 Categoría "Otro" / "Sin club" / "Independiente"

**Citas:**
```
p5 ELITE_F : 2 113 Ana María Roa Chía Otro 1:30:22 36
p5 ELITE_F : 3 112 Diana Pinilla CHIQUINQUIRÁSin club 1:30:32 33
p4 INF_B   : 1 364 Dilan Maya Arias SANTIAGO DE CIAnLdIependiente 0:33:02 40
```

**Interpretación:** valores válidos pero no-club. `is_trocha_y_ruta("Otro")` debe dar `False` (`partial_ratio("otro", "trocha y ruta")` ≈ 25). Igual para `Sin club`, `Independiente`. Sin riesgo de falso positivo.

### 4.16 Punto-coma en ciudad `BOGOTÁ, D.C.`

**Cita:**
```
p5 ELITE_F : 4 114 Angie Lara BOGOTÁ, D.C. Sin club 1:36:35 30
```

**Manejo:** la coma y los puntos en `BOGOTÁ, D.C.` no rompen el regex de fila (`time` y `points` están claramente delimitados al final). `normalize_city()` debería preservar la ciudad para legibilidad pero `normalize` la deja como `"bogota d.c."` para comparación interna — sin afectar al matcher (la ciudad no se usa en el match).

### 4.17 PROMOCIONAL — Categoría sin género ni edad estricta

**Citas (PROMOCIONAL, 5 corredores V-IV):**
```
p7: 1 1312 Edwin Rivera CALI Club BTT Recio Norte 1:06:07 40
p7: 4 1305 Andrés Felipe Rodríguez Díaz 0 0 1:24:56 30
p7: 5 1309 Juan Felipe Maya Duque SANTIAGO DE CIAnLdIependiente 1:34:29 27
```

**Interpretación:** `PROMO` es categoría mixta sin restricción estricta de edad/género. El `gender=MIXED` en seed es correcto. `age_min/age_max=NULL` recomendado.

---

## 5. Oracle TyR Válida IV (10 corredores) — verdad de fundamento para Paso 3

Los siguientes 10 corredores deben ser **detectados con `fuzz.partial_ratio ≥ 85`** vs `["trocha y ruta", "club trocha y ruta", "trochy ruta", "trochayruta"]` por el parser del Paso 3. Todos los scores observados son `100.0`.

| Cat (code) | Bib  | Nombre completo (raw del PDF)        | Pos | Tiempo (raw) | Status     | s   | Puntos | Club (raw) | Fuzzy score | Variante mejor match |
|---|---|---|---|---|---|---|---|---|---|---|
| `TET_CP`   | 553  | Thiago Duque Cardona                  | 4   | `0:04:49`     | FINISHED   | 289 | 30 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `PRE_B`    | 718  | Juan David Giraldo Ortiz              | 15  | `0:18:37`     | FINISHED   | 1117 | 7  | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `INF_A_F`  | 1257 | Sofia Gomez                           | 6   | `1:03:15`     | FINISHED   | 3795 | 25 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `INF_A_F`  | 1259 | Eileen Sophia Vargas Bonilla          | 7   | `1:13:52`     | FINISHED   | 4432 | 23 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `INF_A`    | 407  | Miguel Angel Anaya                    | 5   | `0:37:43`     | FINISHED   | 2263 | 27 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `INF_A`    | 426  | Matías Montoya                        | 24  | `DNF`         | DNF        | NULL | 1  | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `INF_B`    | 362  | Jostin Villamizar García              | 11  | `0:43:51`     | FINISHED   | 2631 | 15 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `PJUV_A_F` | 906  | Isabel Cristhina Quiñones Batero      | 3   | `0:59:05`     | FINISHED   | 3545 | 33 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `PJUV_A_F` | 904  | Mariana Coronado Delgado              | 4   | `1:01:41`     | FINISHED   | 3701 | 30 | `Club Trocha y Ruta` | 100 | `trocha y ruta` |
| `ELITE_M`  | 10   | Juan Diego Garcia                     | 14  | `(-1 VUELTA)` | MINUS_LAPS | NULL | 9  | `Club Trocha y Ruta` | 100 | `trocha y ruta` |

**Conteos esperados para asserts del Paso 3 / Paso 4:**
- `riders.where(is_trocha_y_ruta=True).count()` en Válida IV ingesta: **10**.
- `race_results.where(rider.is_trocha_y_ruta=True, event=V-IV).count()`: **10**.
- De esos 10: `status=FINISHED`: **8**, `status=DNF`: **1**, `status=MINUS_LAPS`: **1**, `status=DSQ`: **0**.
- Suma de puntos TyR Válida IV: **200** (30+7+25+23+27+1+15+33+30+9).

### 5.1 Catálogo extendido — TyR únicos en temporada 2026 (16, según GENERAL)

Estos 16 son la **referencia para el matcher de athletes** (Paso 4) — no todos corrieron V-IV pero todos son del club:

| Cat (code) | Bib  | Nombre (raw) | I  | II | III | IV | Total | Corrió V-IV |
|---|---|---|---|---|---|---|---|---|
| `TET_SP`   | 1414 | Mathiw Bohorquez                  | 0  | 0  | 15  | 0  | 15   | NO |
| `TET_SP`   | 1410 | Ihsan Garces Romero               | 0  | 0  | 13  | 0  | 13   | NO |
| `TET_CP`   | 553  | Thiago Duque Cardona              | 0  | 0  | 0   | 30 | 30   | SÍ |
| `PRE_A`    | 808  | Samuel Anaya Molano               | 27 | 19 | 30  | 0  | 76   | NO |
| `PRE_B`    | 718  | Juan David Giraldo Ortiz          | 11 | 7  | 0   | 7  | 25   | SÍ |
| `INF_A_F`  | 1257 | Sofia Gomez                       | 21 | 23 | 27  | 25 | 96   | SÍ |
| `INF_A_F`  | 1259 | Eileen Sophia Vargas Bonilla      | 25 | 1  | 25  | 23 | 74   | SÍ |
| `INF_A`    | 407  | Miguel Angel Anaya                | 36 | 1  | 36  | 27 | 100  | SÍ |
| `INF_A`    | 426  | Matías Montoya                    | 1  | 1  | 0   | 1  | 3    | SÍ |
| `INF_B`    | 362  | Jostin Villamizar García          | 15 | 15 | 1   | 15 | 46   | SÍ |
| `PJUV_A_F` | 906  | Isabel Cristhina Quiñones Batero  | 30 | 30 | 30  | 33 | 123  | SÍ |
| `PJUV_A_F` | 904  | Mariana Coronado Delgado          | 1  | 36 | 36  | 30 | 103  | SÍ |
| `PJUV_A`   | 609  | Samuel Ortiz Valencia             | 25 | 33 | 0   | 0  | 58   | NO |
| `PJUV_A`   | 611  | Nicolas Segura Lopez              | 11 | 0  | 0   | 0  | 11   | NO |
| `PROMO`    | 1319 | Héctor Eduardo Giraldo Ramírez    | 0  | 1  | 25  | 0  | 26   | NO |
| `ELITE_M`  | 10   | Juan Diego Garcia                 | 21 | 21 | 27  | 9  | 78   | SÍ |

**Nota privacidad:** los PDFs de la Federación Colombiana de Ciclismo se publican en sitio público oficial — usar nombres completos en este oracle es **conforme** con la Ley 1581/2012 colombiana (datos sensibles ya públicos por la federación). Aún así, ver §6.3 para evaluar si conviene mover el oracle a YAML gitignored.

---

## 6. Recomendaciones para Paso 3 (parser + normalizer)

### 6.1 Estrategia de extracción (alta prioridad)

1. **Usar `page.extract_tables(table_settings)`** como primario, NO `extract_text()`. Sugerencia:
   ```python
   settings = {
       "vertical_strategy": "lines",
       "horizontal_strategy": "lines",
       "snap_tolerance": 3,
       "intersection_tolerance": 3,
   }
   tables = page.extract_tables(settings)
   ```
   Si `tables` devuelve celdas correctamente separadas, perfecto. Si no (PDFs sin rulings visibles), caer a `"text"` strategy.
2. **Fallback** sobre `page.extract_words()` agrupando por coordenada `top` y luego ordenando por `x0` para reconstruir filas. Esto resuelve el artefacto §4.5/§4.6 si `extract_tables` falla.
3. **Detectar categoría actual** via regex `CAT:\s*(.+)` sobre `extract_text()` línea-por-línea — la línea `CAT:` siempre va sola (no se entrelaza con celdas).
4. **Persistir `current_cat`** entre páginas cuando una categoría continúa sin reimpresión del header.

### 6.2 Tests sugeridos adicionales (sobre lo declarado en workflow §3.3)

- `test_parse_category_header_femenino_distinct`: `parse_category_header("CAT: INFANTIL A FEMENINO") == "INF_A_F"` y `parse_category_header("CAT: INFANTIL A") == "INF_A"`. **No invertir.**
- `test_parse_time_minus_laps_singular_vs_plural`: `(-1 VUELTA)` y `(-2 VUELTAS)` ambos parsean.
- `test_normalize_club_zero_treated_as_empty`: `normalize_club("0") == ""` y `is_trocha_y_ruta("0") == False`.
- `test_oracle_tyr_count_valida_iv`: parser sobre `valida_iv_2026_resultados.pdf` retorna exactamente 10 filas con `is_trocha_y_ruta=True`.
- `test_oracle_tyr_bibs_valida_iv`: el set de bibs detectados = `{553, 718, 1257, 1259, 407, 426, 362, 906, 904, 10}`.
- `test_dorsal_1411_not_in_results`: parser de RESULTADOS V-IV NO devuelve fila para `bib=1411`.
- `test_general_extends_tyr_catalog`: parser GENERAL detecta los 16 TyR únicos temporada (incluidos los 6 que no corrieron V-IV).
- `test_matias_sabogal_time_anomaly_flag`: `bib=424` parseable pero `time_seconds=273` (< 25 min) dispara warning para tier menores.
- `test_dual_category_same_rider`: `Sebastian Yule Mendoza` (1401 TET_SP + 550 TET_CP) consolida 1 rider con 2 race_results.

### 6.3 Privacidad — Decisión sobre oracle (criterio data-analyst)

**Recomendación:** mantener el oracle TyR (sección 5 de este documento) en `edge-cases.md` **público** porque:
1. Los PDFs originales son publicación oficial de la Federación Colombiana de Ciclismo Liga del Valle, accesibles sin autenticación.
2. Solo se publican: nombre + dorsal + categoría + tiempo + puntos. **NO** fecha de nacimiento, **NO** dirección, **NO** datos médicos.
3. El oracle es **assertion técnica de tests**, no perfilamiento — sirve para validar que el parser detecta a estos riders, no para análisis individual.

**Alternativa si el coach prefiere conservadurismo extremo:** mover sección 5 a `docs/10-race-results/oracles/valida_iv_tyr.yaml` y agregar al `.gitignore`. En este caso, los tests del Paso 3 leerían el YAML como fixture local y la assertion sería sobre el set de **bibs** (`{553, 718, 1257, 1259, 407, 426, 362, 906, 904, 10}`) en lugar de nombres. Esto preserva la utilidad del test sin exponer nombres en el repo público.

**Acción del agente coach (Paso 2 kickoff):** confirmar cuál de las dos opciones prefiere. Sin confirmación, **default = mantener nombres en repo público** (postura actual del workflow §1.2 que ya menciona "Matias Sabogal" explícitamente).

### 6.4 Metadatos de carrera (paso 2-3-6)

El PDF aporta solo: `valida_num=IV`, `name="VALIDA IV CALI MAYO 17 DE 2026"`, `location=CALI`, `event_date=2026-05-17`. Todo lo demás (`climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes`) se captura manualmente vía CLI interactivo (workflow §6.2 paso 3). El parser puede detectar:

```python
HEADER_RE = re.compile(r"VALIDA\s+(IV|V|VI|VII|I+|CD)\s+(\w+)\s+(\w+)\s+(\d+)\s+DE\s+(\d{4})")
# match: ('IV', 'CALI', 'MAYO', '17', '2026')
```

Esto pre-rellena los prompts de `ingest` y baja fricción para el coach.

---

## 7. Resumen de decisiones técnicas tomadas (con justificación)

1. **Mapping header→code por igualdad exacta sobre header normalizado** (no por keyword `FEMENINO`). Por qué: previene colisión `"INFANTIL A" ⊂ "INFANTIL A FEMENINO"` que daría falso positivo masculino. Coste: si una válida futura altera el texto del header, hay que actualizar el dict — pero el dict es un punto único de cambio.
2. **Oracle TyR Válida IV = 10 corredores** (los que corrieron). Por qué: la categoría "rider TyR" debe distinguir histórico (16 en GENERAL) vs participante de evento (10 en RESULTADOS). El test del Paso 3 verifica los 10 de V-IV; el test del Paso 4 ingestor verifica los 16 acumulados.
3. **Tolerar `bib=429 Matias Sabogal time=0:04:33` como tiempo anómalo, no como error de parseo.** Por qué: la organización le asignó puntos consistentes con su posición — la posición es la fuente de verdad, el tiempo es metadato sospechoso. Marcar `time_anomaly` en log, NO bloquear ingest.
4. **`fuzz.partial_ratio` mejor que `fuzz.ratio` para detección club TyR.** Por qué: `ratio("club trocha y ruta", "trocha y ruta")` = 76 (falla umbral 85), pero `partial_ratio` = 100 porque la subcadena coincide. Esto importa porque algunos riders aparecen con club `"TROCHA Y RUTA"` (sin prefijo "Club"), otros con `"Club Trocha y Ruta"`.
5. **Conservar 26 codes en el catálogo, NO 22.** Por qué: 26 es el número real observado y enumerado en `design §3.1`. El texto "22 categorías oficiales" del design parece error de redacción que conviene corregir en pasa posterior (no en este paso por restricción de no modificar `design.md`).

---

## 8. Ambigüedades sin resolver (requieren input del coach antes de Paso 2)

1. **¿Mantener oracle TyR con nombres en `edge-cases.md` público o moverlo a YAML gitignored?** Default propuesto: público (los PDFs son ya públicos por la federación). Coach puede decidir lo contrario sin impacto técnico — solo cambia path del fixture y el shape del assert.
2. **¿Status `DNS` debe sumarse al enum `ResultStatus` o se ignora?** No observado en V-IV pero típico en futuras válidas. Recomendación técnica: agregarlo al enum (`design §3.4`) en Paso 2 antes de la migración inicial, así evitamos migración de enum posterior. Pendiente confirmación.
3. **¿UPSERT o IGNORE en re-ingest de PDF con cambios?** Si la federación publica corrección post-evento (ej. fixing `Matias Sabogal` tiempo a `0:40:33`), el ingest debe actualizar `time_seconds` para race_results existentes o ignorarlos. El `design §4.4` dice "idempotente: re-ingest mismo PDF no duplica" pero no aclara correcciones. Workflow §7.2 (Paso 7) anuncia decisión pendiente. Recomendación: UPDATE si `(event_id, category_id, rider_id)` existe Y `time_seconds` OR `position` cambia, además de un log explícito.
4. **Tratamiento de "Mathiw Bohorquez" (1414)** — nombre con typo evidente (debería ser "Mathias"). Política: persistir `full_name_raw` tal cual el PDF, normalizar para fuzzy. Si el coach tiene certeza de la grafía correcta, link manual a athlete posterior la fija. Sin decisión bloqueante.

---

**Próximo paso:** Paso 2 (`fastapi-architect` Opus override) — modelos SQLAlchemy + migración Alembic + seed 26 categorías. Este documento queda como referencia obligatoria para Paso 3 (parser) y Paso 4 (ingestor).
