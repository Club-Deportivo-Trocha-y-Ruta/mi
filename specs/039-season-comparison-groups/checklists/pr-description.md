# feat(competitions): separa copa y campeonatos en las gráficas de temporada

> Título del PR / commit de merge (Conventional Commits: tipo en inglés, descripción en español latino).
> Rama: `feat/039-season-comparison-groups` → `main`. Spec: `specs/039-season-comparison-groups/`.

## Contexto

Las gráficas de "Evolución en la temporada" (boletín familiar y detalle del deportista) dibujaban en una sola línea las válidas de la copa y los campeonatos departamental y nacional. Un campeonato reúne un pelotón distinto —todo el Valle o todo el país—, así que su puesto y su gap no son comparables con los de una válida: la línea conectada sugería una caída de rendimiento que no existió, y la IA repetía esa lectura en el texto que aprueba el entrenador y que llega a las familias.

Este cambio introduce el **grupo de comparación**: cada copa es un grupo con sus válidas y cada campeonato es su propio grupo de una sola carrera. Se deriva de `race_series` (tipo + id), no se persiste: **cero migraciones**.

## Alcance por historia

### US1 — El boletín lee la copa y los campeonatos por separado (P1)

- El PDF de la bitácora dibuja **un bloque de tres gráficas por copa** (`Evolución en la {copa} {año}`), con solo las válidas de esa copa; el acumulado de puntos suma únicamente esa copa y coincide con el total de la tabla de posiciones (verificado por prueba contra `standings`).
- Debajo aparece la sección **`Campeonatos`**: una tarjeta por campeonato con `Posición`, `Pelotón` (tamaño del pelotón en su categoría), `Gap al P1` y `Percentil`, más la nota "Un campeonato reúne un pelotón distinto al de la copa: se lee por separado y no se compara con las válidas.".
- Un campeonato no terminado muestra "No completó la prueba." en lugar de números. Sin campeonatos, la sección no se renderiza; sin válidas de copa, no se dibuja ninguna gráfica y las tarjetas siguen apareciendo.
- La sección de temporada dejó de vivir dentro del anexo de crecimiento: ahora es una página propia y ya no depende de que haya medición antropométrica en el mes.
- El deduplicado del histórico pasó de `event_date` a `event_id`, para que dos carreras del mismo día (dos copas, o copa y campeonato) no se pisen.
- La tarjeta solo expone el resultado propio del deportista (puesto, tamaño del pelotón, gap y percentil): ningún nombre, dorsal ni identificador de terceros.

### US2 — El detalle del deportista deja elegir la competencia (P2)

- Nuevo selector **`Competencia`** en la gráfica de evolución: primero las copas (por su válida más temprana), luego los campeonatos por fecha; por defecto la primera copa (o el primer campeonato si no corrió copa). Cambiar de temporada resetea la selección.
- Al elegir un campeonato se muestra la tarjeta de lectura (pelotón propio) y la tabla, nunca una línea de un solo punto.
- El sparkline del Panorama dibuja solo la primera copa y muestra "Sin válidas de copa en esta temporada." cuando la temporada no tiene copa.
- `GET /api/athletes/{id}/race-analysis/evolution` acepta `series_id` (opcional) y agrega `groups[]` y `selected_group`; todos los campos previos conservan nombre, tipo y semántica, así que un cliente que ignore `groups` sigue funcionando. RBAC sin cambios: un padre que pide otro deportista recibe exactamente la misma negación con o sin el filtro.

### US3 — La IA nunca compara un campeonato con una válida (P3)

- El pipeline resuelve la carrera analizada por `event_id` cuando el lanzamiento viene anclado a una competencia, y solo cae a `valida_num` entre filas de copa (desde la spec 014 un campeonato comparte `sequence_number` con la Válida I).
- El comparativo de temporada usa únicamente carreras **anteriores de la misma serie**; un campeonato devuelve lista vacía y estado "primera referencia".
- La tabla "Recorrido hasta acá" gana una columna `serie` (`Válida N · Copa`, `Cto. Departamental`, `Cto. Nacional`) y el prompt v3 suma la regla inviolable 10: nunca comparar puesto ni gap de un campeonato contra una válida; leerlo por percentil y tamaño del pelotón.
- El rollback sigue disponible sin desplegar (`RACE_AI_PROMPT_VERSION=race_analyst_v2`).
- Las etiquetas quedan conscientes del nivel en todas las superficies: PDF, marcador de la gráfica, tooltip, línea de tiempo de insights, tarjeta destacada e historial de diálogo — un campeonato nacional nunca se rotula como departamental.

### US4 — Una temporada con más de una copa mantiene cada copa aparte (P4)

- El boletín renderiza un bloque de evolución por copa, el selector lista cada copa por su nombre (sin "Copa Valle" hardcodeado en ningún lado) y el acumulado de puntos es por copa.
- Cubierto con dataset sintético de dos copas + un campeonato, tanto en el boletín como en el endpoint.

## Estado del gate de evaluación golden (abierto)

`pytest -m golden` (umbral bloqueante 0.75) se corrió hoy con la clave real: **caso 001 = 0.840** y **caso 002 = 0.820**; a partir del caso 003 se agotó la cuota gratuita de Gemini (HTTP 429 `RESOURCE_EXHAUSTED`) y los casos 003–009 cayeron al camino determinista, por lo que **no fueron medidos**. El archivo de marcador se restauró a su versión previa a la corrida.

**El gate no está aprobado ni reprobado: está abierto.** Debe re-ejecutarse completo cuando la cuota se restablezca, antes de dar por cerrada la historia US3 (FR-016 / SC-005). El caso nuevo `case_009` (campeonato nacional, pelotón de 34) ya forma parte del dataset.

## Cumplimiento de la constitución

Cumple los cinco principios de `.specify/memory/constitution.md` v1.2.0 (I calidad de código, II pruebas, III consistencia de UX, IV rendimiento, V salvaguardas de evaluación psicológica — no aplica a esta feature). Las diez desviaciones/hallazgos registrados en `specs/039-season-comparison-groups/checklists/integration-review.md` §D (F-1 a F-10) quedaron resueltos en el review de integración y su pasada de seguimiento (detalle uno a uno en §G) — incluida la que bloqueaba el merge (F-1: la tarjeta de campeonato del detalle ahora muestra las cuatro lecturas sin importar la métrica activa). Auditoría de privacidad (Ley 1581) sin hallazgos críticos, altos ni medios.

## Pruebas

- Backend, archivos de la feature: **186 pruebas verdes** (lane offline, aiosqlite).
- Backend, lane offline completo: 3628 verdes; los 222 fallos restantes están en archivos con diff de 0 líneas contra `main` (MySQL fuera de Docker, librerías nativas de WeasyPrint ausentes en local, tres expectativas obsoletas ajenas a esta feature).
- Frontend: **131 pruebas verdes** en las seis specs tocadas; suite completa 3691 verdes con un fallo preexistente dependiente de zona horaria (`src/lib/__tests__/datetime.test.ts`), ajeno a la feature.
- `ruff` limpio en los archivos tocados (la rama deja el repo con dos errores menos que la línea base), `tsc --noEmit` limpio, `jest-axe` sin violaciones con el selector nuevo presente.
- `pytest -m mysql` (caso de dialecto del CTE) no se ejercitó en esta pasada: `TEST_DATABASE_URL` sin definir por diseño.

## Notas de despliegue

- Sin migraciones, sin variables de entorno nuevas, sin dependencias nuevas.
- Los boletines generados antes de esta feature conservan su snapshot antiguo: al volver a descargarlos ya no traen la página de gráficas de temporada (no hay error; era justamente la gráfica mezclada que esta feature elimina). Los boletines nuevos la traen con la separación por copa.

## Seguimiento

Solo quedan dos pendientes abiertos; los diez hallazgos del review de integración (F-1 a F-10) están resueltos — detalle uno a uno en `checklists/integration-review.md` §G.

- Re-ejecutar el gate golden completo cuando se restablezca la cuota (T040).
- Humo post-despliegue (T050): `/health` y `GET /api/athletes/{id}/race-analysis/evolution?season=2026&metric=ranking&series_id=<copa>` autenticado, más carga del dashboard en dispositivo real.


## Actualización 2026-09-04 — gate golden

`pytest -m golden` (v3, 9 casos) promedio **0.821** (umbral 0.75), caso 009 del campeonato nacional **0.850** con la regla 10 respetada (`forbidden` 1.00). El analista corrió en `gemini-3.1-flash-lite` porque la cuota gratuita diaria de `gemini-3.8-flash` (20 solicitudes, compartida con producción) estaba agotada; con `gemini-3.8-flash` los casos 001/002 dieron 0.840/0.820 el 2026-09-03. Pendiente únicamente el smoke post-deploy (T050).
