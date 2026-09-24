# Race Analyst Golden Eval — Last Run

- **Fecha:** 2026-09-24 02:51:10 UTC
- **Versión del eval:** v3
- **Threshold CI:** 0.75
- **Casos ejecutados:** 14
- **Promedio compuesto:** **0.780**
- **Verdict:** PASS

## Detalle por caso

| case_id | rule | judge | composite | words | cites | tokens_in | tokens_out | cost_usd |
|---|---|---|---|---|---|---|---|---|
| 006 | 0.917 | 0.617 | 0.737 | 396 | 2 | 43107 | 6297 | 0.000000 |
| 002 | 0.925 | 0.808 | 0.855 | 401 | 3 | 43482 | 10175 | 0.000000 |
| 001 | 0.850 | 0.783 | 0.810 | 357 | 3 | 43346 | 9086 | 0.000000 |
| 005 | 0.925 | 0.833 | 0.870 | 413 | 3 | 43565 | 9173 | 0.000000 |
| 003 | 1.000 | 0.783 | 0.870 | 404 | 3 | 43671 | 9160 | 0.000000 |
| 004 | 0.767 | 0.633 | 0.686 | 421 | 3 | 43002 | 11097 | 0.000000 |
| 007 | 0.850 | 0.733 | 0.780 | 412 | 3 | 43059 | 11801 | 0.000000 |
| 009 | 1.000 | 0.800 | 0.880 | 404 | 3 | 43863 | 9788 | 0.000000 |
| 010_course_present | 0.917 | 0.783 | 0.837 | 436 | 3 | 43544 | 10627 | 0.000000 |
| 011_course_absent | 0.950 | 0.817 | 0.870 | 433 | 3 | 43438 | 9821 | 0.000000 |
| 012_conditions_absent_course_present | 0.883 | 0.817 | 0.844 | 425 | 3 | 43522 | 9179 | 0.000000 |
| 014_adult_athlete | 1.000 | 0.850 | 0.910 | 381 | 2 | 43677 | 7308 | 0.000000 |
| 008 | 0.512 | 0.000 | 0.205 | 125 | 0 | 0 | 0 | 0.000000 |
| 013_two_cups_same_valida | 0.750 | 0.783 | 0.770 | 444 | 3 | 43676 | 8390 | 0.000000 |

> `*` indica que el parser del juez usó fallback neutral 0.5.
> En v3 la columna `cites` cuenta principios citados (`principles_cited`), no chunks de RAG.

## Sub-rúbricas rule-based (v3)

| case_id | catalog | coach_question | forbidden | grounding | headline | schema | themes | word_limits |
|---|---|---|---|---|---|---|---|---|
| 006 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| 002 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| 001 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| 005 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| 003 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 004 | 0.50 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| 007 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 009 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 010_course_present | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| 011_course_absent | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 012_conditions_absent_course_present | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.33 | 1.00 |
| 014_adult_athlete | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 008 | 0.50 | 1.00 | 1.00 | 0.00 | 0.00 | 0.75 | 0.50 | 1.00 |
| 013_two_cups_same_valida | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |

## Descripción de los casos

- **006**: Sin antropometría: el bloque de maduración no llega al modelo. Con ventana de entrenamiento completa, el análisis debe apoyarse en pelotón + entrenamiento y declarar el vacío madurativo en data_gaps, sin afirmar fase PHV.
- **002**: Bambino (12 años) en declive: pierde tres puestos respecto de lo esperado en la válida con la asistencia más baja del ciclo y RPE alto en los últimos siete días.
- **001**: Mini-bambino (10 años) en mejora sostenida: mejor percentil de la temporada tras la ventana de entrenamiento con mayor asistencia. Pre-PHV, catálogo técnico disponible.
- **005**: Circa-PHV con caída esperable: 13 años, pico de crecimiento en curso (velocidad 9.1 cm/año) y pérdida de percentil pese a asistencia alta. La lectura correcta es madurativa, sin diagnóstico médico y sin subir carga.
- **003**: Juvenil (14 años) en campeonato departamental con pelotón más fuerte y más numeroso: termina 3 puestos por encima de lo esperado. Hallazgo positivo pese a caer en posición absoluta frente a las válidas de copa.
- **004**: N=1: primera y única válida con resultado de la temporada. Sin historial comparable y con menos de la mitad del pelotón con índice previo, la expectativa no se calcula. El análisis debe declararse como referencia inicial y no inventar tendencia.
- **007**: Sin ventana de entrenamiento: el atleta no tiene asistencia registrada en los 28 días previos. El análisis debe leer pelotón + maduración + historia, declarar el vacío en data_gaps y no afirmar nada sobre carga, RPE ni foco técnico.
- **009**: Bambino (13 años) en campeonato NACIONAL: pelotón de 34 y gap de 35.6% frente a una temporada de copa con pelotones de 11-12 y un departamental de 18. El análisis debe leer el campeonato por percentil, tamaño y fuerza del pelotón, sin comparar el puesto ni el gap contra las válidas de copa (regla inviolable 10).
- **010_course_present**: Bambino (12 años), válida de copa con circuito registrado (terreno mixto y técnico, con desnivel). El gap sube frente a las válidas previas en el circuito más exigente de la temporada — el análisis debe contextualizar por el circuito, no leerlo como una caída de forma (feature 043, User Story 4).
- **011_course_absent**: Mismo escenario base que case_010 (bambino 12 años, válida de copa, gap más alto que en las cuatro válidas previas) pero SIN perfil de circuito registrado para esta válida — el análisis debe declarar el vacío y no puede mencionar distancia, vueltas, terreno, desnivel ni dificultad técnica del recorrido (feature 043, User Story 4, veto SIN DATO).
- **012_conditions_absent_course_present**: Mismo escenario que case_010 (bambino 12 años, circuito registrado con superficie mixta y técnica) pero SIN condiciones del día de carrera. El análisis puede usar el circuito y no puede mencionar clima, temperatura, altitud ni el estado de la pista ese día. Cubre la combinación en la que el veto de condiciones y el bloque de circuito conviven en el mismo prompt.
- **014_adult_athlete**: Atleta ADULTO (31 años, categoría Élite) — feature 'adult athlete path'. Sin marco LTAD/PHV, sin anthro_context (maduración no aplica), objetivos de resultado permitidos, sin lenguaje familiar/escolar. Válida el flujo adulto añadido al pipeline v3.
- **008**: Resumen de temporada (analysis_kind=season, valida_num=0): 6 carreras de copa más un campeonato, trayectoria mixta con un bache a mitad de año y recuperación al cierre. Sin fila de carrera ni lectura de pelotón propia: field_reading debe quedar en null.
- **013_two_cups_same_valida**: Regresión del hotfix de identidad de válida (plans/multicopa-identidad-valida.md): el atleta corrió Copa Valle V4/V5 antes en la temporada y ahora corre la Válida IV de una segunda copa distinta, Copa Let's Go Interdepartamental, que comparte número de válida con la primera. El input que llega al analista (ya filtrado por series_id por el pipeline) contiene ÚNICAMENTE datos de Copa Let's Go Interdepartamental — ninguna fila, condición ni referencia de Copa Valle. El análisis no debe mencionar la otra copa, inventar un estado de carrera (reprogramada/aplazada/cancelada/suspendida) ni tratar la Válida IV de esta copa como si fuera la misma carrera que la Válida IV/V de la otra.
