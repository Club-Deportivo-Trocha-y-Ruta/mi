# UI copy (045): product copy in español neutro (Colombia)

## Glossary labels (single meaning, used everywhere)

| Key | Label | Family? |
|---|---|---|
| area | «Competencias» | ✓ |
| athlete tab | «Carreras» | ✓ |
| views | «Progresión» · «Análisis IA» · «Comparar» | Comparar is coach only |
| field_size | «Parrilla» | ✓ |
| percentile | «Percentil» | ✓ |
| gap_to_median_pct | «Brecha vs. mediana» | ✓ |
| gap_to_winner_pct | «Brecha vs. 1.ª posición» | ✗ |
| gap_to_podium_pct | «Brecha vs. podio» | ✗ |
| statuses | «No terminó» (dnf) · «No salió» (dns) · «Descalificado» (dsq) · «Perdió vueltas» (minus_laps) | ✓ |
| sections | «Temporada» · «Cargas e identidades» · «¿Es la misma persona?» · «Sin enlazar» | coach |
| competition tab | «Circuito y condiciones» | coach |
| edit action | «Editar datos» (replaces «Editar metadata») | coach |
| critic line | «Revisión automática» (replaces «Crítico LLM dice») | coach |

Retired everywhere: «Válidas» as an area name, «Gap al P1», «Diferencia al podio», «Pelotón», «Insights IA» as a tab name.

## Family AI label

> Análisis generado con IA y revisado por el entrenador.

## Approval card

- **Existing note (phase 0)**: «Al aprobar, la familia podrá verlo en la app. No se envía correo.»
- **Warning when `family_gap_mentions` is not empty**:
  > Este análisis menciona la brecha con el primer lugar o el podio, y la familia lo verá. Puedes aprobarlo igual o pedir una revisión.

## Identity gate (blocked commit)

> Hay {n} decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.

## Bitácora change notice (inserted by the coach, editable)

> Actualizamos cómo mostramos los resultados: ahora la referencia principal es la brecha con la mediana de su categoría, qué tan cerca estuvo del tiempo típico del grupo. El percentil se calcula con los tiempos, así que algunas cifras de meses anteriores pueden verse distintas. Los resultados no cambiaron, solo la forma de leerlos. Todo está en la pestaña «Carreras».

This is the text `frontend/src/components/newsletter/studio/changeNotice.ts` (`CHANGE_NOTICE_TEXT`) inserts: 59 words, 367 characters. It must stay at 60 words or fewer because the backend caps `coach_note` at 60 words (`AthleteNewsletterPatch` answers 422 and `StageLog` truncates on read), and at 600 characters or fewer. The earlier draft of this notice was 74 words (446 characters), so it could not be saved. It kept the same four points, and the condensed text keeps them too: the median-gap reference, the time-based percentile (older figures may look different), results unchanged, and where to see it. `changeNotice.test.ts` pins both caps. If you edit this text, edit `CHANGE_NOTICE_TEXT` in the same change.
