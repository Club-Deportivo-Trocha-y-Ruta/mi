# Race Analyst Golden Eval — Last Run

- **Fecha:** 2026-09-01 15:15:39 UTC
- **Threshold CI:** 0.75
- **Casos ejecutados:** 11
- **Promedio compuesto:** **0.651**
- **Verdict:** FAIL

## Detalle por caso

| case_id | rule | judge | composite | words | cites | tokens_in | tokens_out | cost_usd |
|---|---|---|---|---|---|---|---|---|
| 001 | 0.700 | 0.900 | 0.820 | 300 | 0 | 2768 | 487 | 0.001423 |
| 002 | 0.500 | 0.700 | 0.620 | 257 | 0 | 2759 | 431 | 0.001336 |
| 003 | 0.700 | 0.700 | 0.700 | 292 | 0 | 2763 | 456 | 0.001375 |
| 004 | 0.700 | 0.600 | 0.640 | 270 | 0 | 2774 | 446 | 0.001362 |
| 005 | 0.700 | 0.700 | 0.700 | 231 | 0 | 2498 | 358 | 0.001161 |
| 006 | 0.700 | 0.600 | 0.640 | 304 | 0 | 2773 | 496 | 0.001437 |
| 007 | 0.700 | 0.600 | 0.640 | 300 | 0 | 2792 | 477 | 0.001414 |
| 008 | 0.800 | 0.600 | 0.680 | 317 | 0 | 2772 | 511 | 0.001460 |
| 009 | 0.700 | 0.800 | 0.760 | 281 | 0 | 2762 | 432 | 0.001339 |
| 010 | 0.500 | 0.000 | 0.200 | 16 | 0 | 0 | 0 | 0.000000 |
| 011 | 0.700 | 0.800 | 0.760 | 267 | 0 | 2725 | 439 | 0.001340 |

> `*` indica que el parser del juez usó fallback neutral 0.5.

## Descripción de los casos

- **001**: Atleta 10 años (mini-bambino) en INF_A con progresión positiva sostenida 4 válidas y podio recurrente; categoría diversión + ventana entrenabilidad.
- **002**: Atleta 12 años (bambino) con gap creciente al podio en INF_B: regresión que requiere replanteo, no presión.
- **003**: Atleta 13 años (juvenil) con alta dispersión: 3 podios + 1 DNF mecánico. Mostrar análisis de consistencia técnica sin penalizar por el DNF.
- **004**: Atleta 14 años (juvenil) en transición PJUV → JUV, mostrar diferencias de carga y enfoque LTAD para el cambio categórico.
- **005**: Atleta 11 años (bambino) en su primera temporada con sólo 2 válidas (n=2). El análisis debe marcar baja confianza y enfocar en diversión + adaptación.
- **006**: Atleta 15 años (juvenil) en tapering pre-Campeonato Departamental (carrera A). Recomendaciones de carga descendente y descanso.
- **007**: Atleta 10 años (mini-bambino) con brote de crecimiento detectado en antropometría reciente: cargas previas excesivas → fatiga visible. Reducir, no diagnosticar.
- **008**: Atleta 13 años (juvenil) con estancamiento técnico: cadencia observada en video <70 rpm. Recomendar trabajo específico de pedaleo y cadencia.
- **009**: Atleta 12 años (bambino) con DNF en V-IV por mecánico (pinchazo). 3 carreras previas con mejora sostenida. No penalizar al atleta.
- **010**: Atleta femenina 14 años (juvenil) en PJUV_F: evolución sólida con primer podio reciente. Recomendaciones equilibradas con perspectiva de género (sin estereotipos).
- **011**: Atleta 13 años (juvenil) con mejora sostenida en descensos tras trabajo técnico específico; caso diseñado para ejercer season_comparative con 2+ válidas previas (specs/036 T053, camino 'con historial' del prompt v2 — antes nunca evaluado).
