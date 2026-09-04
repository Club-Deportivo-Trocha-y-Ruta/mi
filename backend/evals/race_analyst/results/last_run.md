# Race Analyst Golden Eval — Last Run

- **Fecha:** 2026-09-04 13:42:00 UTC
- **Versión del eval:** v3
- **Modelo del analista en esta corrida:** `gemini-3.1-flash-lite` (override `RACE_AI_ANALYST_MODEL` por cuota agotada del tier gratuito de `gemini-3.8-flash`, 20 solicitudes/día compartidas con producción). Con `gemini-3.8-flash` (2026-09-03) los casos 001/002 puntuaron 0.840/0.820 antes del 429.
- **Threshold CI:** 0.75
- **Casos ejecutados:** 9
- **Promedio compuesto:** **0.821**
- **Verdict:** PASS

## Detalle por caso

| case_id | rule | judge | composite | words | cites | tokens_in | tokens_out | cost_usd |
|---|---|---|---|---|---|---|---|---|
| 001 | 1.000 | 0.733 | 0.840 | 264 | 3 | 3432 | 725 | 0.001945 |
| 002 | 0.925 | 0.733 | 0.810 | 247 | 3 | 3500 | 658 | 0.001862 |
| 003 | 1.000 | 0.667 | 0.800 | 238 | 3 | 3650 | 715 | 0.001985 |
| 004 | 0.967 | 0.883 | 0.916 | 255 | 2 | 3148 | 716 | 0.001861 |
| 005 | 0.975 | 0.633 | 0.770 | 285 | 3 | 3562 | 781 | 0.002062 |
| 006 | 0.833 | 0.833 | 0.833 | 278 | 2 | 3234 | 764 | 0.001955 |
| 007 | 0.850 | 0.567 | 0.680 | 305 | 2 | 3194 | 773 | 0.001958 |
| 008 | 0.975 | 0.833 | 0.890 | 228 | 3 | 3246 | 690 | 0.001847 |
| 009 | 0.975 | 0.767 | 0.850 | 277 | 3 | 3818 | 752 | 0.002083 |

> `*` indica que el parser del juez usó fallback neutral 0.5.
> En v3 la columna `cites` cuenta principios citados (`principles_cited`), no chunks de RAG.

## Sub-rúbricas rule-based (v3)

| case_id | catalog | coach_question | forbidden | grounding | headline | schema | themes | word_limits |
|---|---|---|---|---|---|---|---|---|
| 001 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 002 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| 003 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 004 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| 005 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| 006 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.33 | 1.00 |
| 007 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 008 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| 009 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |

## Descripción de los casos

- **001**: Mini-bambino (10 años) en mejora sostenida: mejor percentil de la temporada tras la ventana de entrenamiento con mayor asistencia. Pre-PHV, catálogo técnico disponible.
- **002**: Bambino (12 años) en declive: pierde tres puestos respecto de lo esperado en la válida con la asistencia más baja del ciclo y RPE alto en los últimos siete días.
- **003**: Juvenil (14 años) en campeonato departamental con pelotón más fuerte y más numeroso: termina 3 puestos por encima de lo esperado. Hallazgo positivo pese a caer en posición absoluta frente a las válidas de copa.
- **004**: N=1: primera y única válida con resultado de la temporada. Sin historial comparable y con menos de la mitad del pelotón con índice previo, la expectativa no se calcula. El análisis debe declararse como referencia inicial y no inventar tendencia.
- **005**: Circa-PHV con caída esperable: 13 años, pico de crecimiento en curso (velocidad 9.1 cm/año) y pérdida de percentil pese a asistencia alta. La lectura correcta es madurativa, sin diagnóstico médico y sin subir carga.
- **006**: Sin antropometría: el bloque de maduración no llega al modelo. Con ventana de entrenamiento completa, el análisis debe apoyarse en pelotón + entrenamiento y declarar el vacío madurativo en data_gaps, sin afirmar fase PHV.
- **007**: Sin ventana de entrenamiento: el atleta no tiene asistencia registrada en los 28 días previos. El análisis debe leer pelotón + maduración + historia, declarar el vacío en data_gaps y no afirmar nada sobre carga, RPE ni foco técnico.
- **008**: Resumen de temporada (analysis_kind=season, valida_num=0): 6 carreras de copa más un campeonato, trayectoria mixta con un bache a mitad de año y recuperación al cierre. Sin fila de carrera ni lectura de pelotón propia: field_reading debe quedar en null.
- **009**: Bambino (13 años) en campeonato NACIONAL: pelotón de 34 y gap de 35.6% frente a una temporada de copa con pelotones de 11-12 y un departamental de 18. El análisis debe leer el campeonato por percentil, tamaño y fuerza del pelotón, sin comparar el puesto ni el gap contra las válidas de copa (regla inviolable 10).
