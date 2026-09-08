feat(growth-module): rediseña el módulo de crecimiento con OMS 2007 como referencia única

## Resumen

Rediseño completo del tab "Crecimiento" (spec `040-growth-module-redesign`,
auditoría base en `docs/18-growth-module-redesign/proposal.md`). Cinco
historias de usuario, en orden de prioridad:

1. **Una sola referencia poblacional (P1 — MVP)**: el servidor deja de mezclar
   CDC y OMS 2007 y pasa a usar **OMS 2007 en todas las superficies**
   (tarjeta, curva, tabla y PDF familiar). Se agrega la columna aditiva
   `anthropometric_records.growth_source` (`WHO`/`CDC`, nullable), se vendoriza
   el set OMS en el servidor (`backend/app/data/who_lms/*.csv`, exportado de
   forma determinística desde el JSON del cliente) y se recalculan una sola
   vez los registros históricos con un script idempotente que nunca toca las
   columnas crudas (peso, talla, fecha de evaluación, notas, etc.).
2. **El entrenador lee la decisión antes que la evidencia (P1)**: nuevo
   endpoint `GET /athletes/{id}/growth-summary` (una consulta, dos filas) que
   deriva etapa, velocidad cm/año, próxima medición y alertas; el tab abre
   directamente en ese resumen decision-first, con las reglas de
   entrenamiento condensadas y sin el número de frecuencia cardíaca máxima
   estimada (nunca medida).
3. **Una curva legible (P2)**: la curva de percentiles se divide en
   `PercentileChart` + `PercentileToolbar` + `PercentileTable`, con ventana de
   edad acotada a las mediciones reales (antes mostraba 5–19 años completos),
   vista de tabla accesible, alternancia de eje biológico (solo entrenador) y
   exportación PNG sin datos identificables. Se eliminan `GrowthCharts.tsx` y
   `PercentileCurves.tsx`.
4. **Las familias ven el crecimiento en su propio lenguaje (P2)**: modo
   familiar del tab sin cifras (`Z=`, percentiles) ni etiquetas clínicas,
   siempre sobre la medición más reciente, con explicación de IA de solo
   lectura y una variante de prompt dirigida al acompañante (`audience`
   family/coach).
5. **El tab pertenece al producto (P3)**: componentes y tokens compartidos en
   toda la pantalla, línea de tiempo de maduración, se retira el salto
   automático al tab de crecimiento y los activos del módulo (recharts + el
   set OMS) pasan a un chunk perezoso.

De regalo, se corrigen tres defectos preexistentes detectados por la
auditoría: la vista de padres clasificaba la medición **más antigua** en vez
de la más reciente, el corte de talla alta no seguía la Resolución 2465/2016,
y se mostraba una frecuencia cardíaca máxima estimada que nunca se midió.

## Impacto del recálculo OMS (por ids, sin datos identificables)

El script `backend/app/scripts/backfill_anthropometry.py::recompute_to_source`
recalcula, para cada registro existente con `growth_source` distinto de
`WHO`, los valores derivados (`height_z_score`, `height_percentile`,
`bmi_z_score`, `bmi_percentile`, `nutritional_status`, `weight_z_score`/
`weight_percentile` cuando la edad es ≤ 120.5 meses) usando las tablas OMS
2007, y marca el registro como `growth_source='WHO'`. **Nunca** escribe
`weight_kg`, `standing_height_cm`, `sitting_height_cm`, `arm_span_cm`,
`evaluation_date`, `notes`, `maturity_offset`, `age_at_phv`,
`maturation_status` ni `training_implications`; los valores de PHV/Mirwald no
cambian para ningún deportista.

El reporte de cambio de banda se escribe en
`./data/growth_band_changes_<YYYYMMDD>.json` (gitignored) como una lista de
`{athlete_id, record_id, indicator, previous, current}` — **solo ids e
indicadores, nunca nombre, fecha de nacimiento ni notas**. La ejecución es
idempotente (una segunda corrida recalcula cero filas) y se dispara
automáticamente al desplegar (`entrypoint.sh` ya invoca el backfill después
del seed).

Pruebas offline (aiosqlite) cubren la conmutación CDC→OMS, la nulidad de
peso por encima de 120.5 meses, la idempotencia y la ausencia de PII en
`caplog`. La corrida de verificación contra una base MySQL `_test` real
(conteo de filas OMS 336/336/120 y resumen del reporte) quedó **pendiente**
(T027) por falta de `TEST_DATABASE_URL` en el entorno de desarrollo; el
reporte real de cambio de banda solo existirá tras esa corrida — el equipo
debe revisarlo (por id, nunca por nombre) antes del próximo ciclo de boletín
familiar, tal como pide el runbook de cierre.

## Cambio de bundle medido

Medido con `npm run build && npm run check:chunks` en
`specs/040-growth-module-redesign/checklists/build-baseline.md`:

| | Antes | Después |
|---|---|---|
| Entry (`index-*.js`) | 336.68 kB gzip (incluye el JSON OMS y el código de los componentes retirados) | 283.38 kB gzip |
| Chunk de recharts | 107.39 kB gzip, importado estáticamente y precargado por `index.html` | Solo alcanzable por `import()` dinámico, ya no precargado |
| Chunk nuevo de crecimiento (`GrowthTab-*.js`) | — | 17.42 kB gzip (presupuesto: ≤ 150 kB) |
| JS efectivo de primer render (entry + chunk module-preloaded) | 444.07 kB gzip | 285.17 kB gzip |

**Reducción de 158.90 kB gzip** en el JS de primer render (objetivo: ≥ 100 kB).
El entry sigue por encima del presupuesto de 250 kB gzip de la Constitución
(principio IV) — es una violación **preexistente**, ya registrada en
`plan.md` (Complexity Tracking); cerrarla requiere una división por rutas de
`App.tsx` que queda fuera del alcance de esta feature.

## Pendientes al cierre (no bloquean el merge, requieren seguimiento)

- **T027 / T028** — corrida de migración + seed + recálculo contra MySQL
  `_test` real, y regeneración de un PDF familiar en el stack de desarrollo:
  diferidas por falta de `TEST_DATABASE_URL` y de un deportista de prueba
  sembrado en este entorno. Dueño: `database-architect` / `qa-engineer`.
- **T044, T054, T064** y el tramo Playwright de **T072** — specs e2e de
  crecimiento (`growth.spec.ts`, `growth-parent.spec.ts`) escritas y
  tipadas pero no ejecutadas en verde: el stack e2e aislado
  (`docker-compose.e2e.yml`, proyecto `trocha-e2e`) no logra levantar el
  backend porque una migración histórica de otra feature
  (`e1f2a3b4c5d6_technique_gymkhana_library.py`, y dos hermanas de refuerzo
  y gymkhana) importa un módulo Python ya eliminado
  (`app.data.technique_catalog`) y falla sobre cualquier base de datos
  **nueva**. Confirmado preexistente (anterior a esta rama) y fuera del
  alcance de esta feature; bloquea cualquier despliegue desde cero, no solo
  el e2e. Dueño: `database-architect`.
- **Fase 8** — la documentación (T074–T076: `docs/implementation-status.md`,
  `docs/technical-notes.md`, banners de documentación superada, bloque
  gestionado de `CLAUDE.md`) y la corrida de `quickstart.md` (T077,
  registrada en `checklists/quickstart-run.md`) ya están hechas. Queda
  **T078**, el smoke post-deploy: solo puede ejecutarse después del merge y
  del despliegue en Render. Dueño: `release-manager`.
- Deuda de diseño no bloqueante, preexistente: `MorphologyCard.tsx` conserva
  clases de color crudas para la etiqueta de categoría de ajuste de bicicleta
  (no es un estado, es una categoría) — fuera del alcance de esta feature.

## Calidad

- Auditoría de privacidad obligatoria (`data-privacy-guard`, T065):
  **aprobada, 0 hallazgos críticos/altos** (3 notas informativas de bajo
  riesgo, sin acción requerida).
- Revisión de copy familiar (`parent-communicator`, T063): firmada, con
  ajustes de tono y gramática aplicados sobre las narrativas de banda.
- Revisión de integración (`engineering-lead`, T073) contra la tabla de
  Constitución de `plan.md` y las reglas de dataviz de la feature 033: todo
  en verde, un defecto encontrado y corregido en el propio gate (las
  tarjetas superiores de la página de padres mostraban etapa y percentil en
  lenguaje clínico, violando FR-016; corregido con prueba de regresión
  primero).
- `cd backend && .venv/bin/python -m pytest -q`: 3699 pass / 225 fail, las
  225 fallas son ambientales y preexistentes (conexión a MySQL de docker,
  librerías nativas de WeasyPrint, la migración de tecnicismo eliminada).
- `cd frontend && npx vitest run`: 3950/3952 pass, las 2 fallas son flakys
  preexistentes de huso horario y de temporizador simulado, no tocadas por
  esta rama.
- `cd frontend && npm run typecheck`: limpio. `cd backend && ruff check`:
  limpio en todos los archivos que esta feature toca o crea.
