# UI contract: feature 048

All copy is español neutro (Colombia). The primary device is a coach tablet; phone is secondary. Touch targets are ≥ 48×48 px, numeric inputs use `inputmode="decimal"`, and every page and dialog must pass jest-axe with 0 violations.

## Routes (coach and admin, lazy-loaded)

| Path | Screen |
|---|---|
| `/athletes/:id/anthropometry/new` | Single capture (guided or quick). The group session page embeds the same capture component (no separate route or query parameter). |
| `/athletes/:id/anthropometry/:recordId/edit` | Edit (quick layout pre-filled, plus plausibility review). |
| `/anthropometry/session` | Group session: picker → queue → summary. |

Entry points:
- On the athlete page's "Antropometría" tab, "+ Nueva medición" becomes a link to `/new`.
- The athletes list gets a "Jornada de medición" button.

## Single capture

**Mode switch.** The header holds a segmented control, "Guiado" / "Rápido". It is persisted in `tyr.anthro.captureMode` and defaults to "Guiado".

**Guided mode** uses the `Stepper` with these steps: Preparación → Peso → Talla de pie → Talla sentado → Envergadura → Revisar.

- **Preparación**:
  - Illustration (`precheck.webp` if available).
  - A non-blocking checklist: «Sin zapatos», «Ropa liviana», «A una hora parecida a la de la última medición», «Antes de entrenar», «Báscula y tallímetro en superficie plana».
  - Evaluation date (default today).
  - The button is «Empezar».
- **Measure step**:
  - Illustration on the left at ≥ 768 px, above the fields at 360 px.
  - «Dónde» / «Cómo» text.
  - One numeric input.
  - «Anterior» / «Siguiente».
  - The Envergadura step adds «Omitir (opcional)».
- **Talla sentado**:
  - Adds «Altura del banco (cm)», pre-filled from `tyr.anthro.benchHeightCm` and editable (0 is allowed).
  - The input is labelled «Lectura en el tallímetro (cm)».
  - A live line shows «Talla sentado neta: 72,0 cm».
  - The net value must be > 0, otherwise an inline error appears.
- **Revisar**:
  - A values table.
  - `PlausibilityWarnings`: one amber callout per warning, naming the measure, with «Volver a medir» (jumps to that step) and «Está bien así».
  - `PhvPlainSummary`: a headline label («Aún no llega al estirón» / «Está en pleno estirón» / «Ya pasó el estirón»), the training implication, and a collapsible «Detalle técnico» (maturity offset, age at PHV, leg length).
  - Save exits: «Guardar y terminar», plus «Guardar y agregar pliegues» under the 046 eligibility rules.
  - The interval note from 046 stays as it is.

**Quick mode** keeps today's grid: date, weight, standing height, sitting height with the bench field, and arm span. The primary button is «Revisar y guardar», which opens the same Revisar panel (warnings, PHV) inline below the grid before the save exits.

**Warning copy** (frontend map `lib/anthropometry/plausibilityCopy.ts`):

| Code | Copy |
|---|---|
| `height_decreased` | «La talla de pie es más de 1 cm menor que en la medición anterior. Revisa la postura y vuelve a medir.» |
| `height_velocity_implausible` | «El aumento de talla desde la medición anterior es inusualmente alto. Revisa que el dato esté bien escrito.» |
| `weight_change_large` | «El peso cambió más de un 10 % desde la medición anterior. Confirma la lectura de la báscula.» |
| `sitting_ratio_atypical` | «La talla sentado no guarda la proporción habitual con la talla de pie. ¿Restaste la altura del banco?» |
| `arm_span_ratio_atypical` | «La envergadura no guarda la proporción habitual con la talla. Revisa que el dato esté bien escrito.» |

**Save states:**
- Saving: the button reads «Guardando…» and is disabled.
- Offline or network failure: a red banner reads «Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.», with «Reintentar». The values stay on screen.
- Opening the screen while offline shows «Necesitas conexión a internet para registrar mediciones.» and disables «Empezar».
- 409 same date:
  - With `same_values` on a retry, it counts as saved.
  - Otherwise a dialog reads «Ya existe una medición de esta fecha», offering «Abrir la existente» (links to edit if `can_modify`, otherwise the history) and «Cambiar la fecha».
- Cold start: the existing «Iniciando servidor…» pattern.

## Edit

- The quick layout comes pre-filled, with the net sitting height and an empty bench field (0 by default on edit).
- «Revisar y guardar» runs the plausibility check with `record_id`.
- The page states «Al guardar se recalculan el estado de maduración, los percentiles y la explicación de IA de esta medición.»
- A 403 is shown as «Solo quien tomó esta medición o un administrador puede modificarla.»

## History (`AnthropometryHistory`, coach mode)

- A row whose `plausibility_flags` is non-empty shows an amber «Revisar» badge. Its tooltip, also available as text on tap (it does not rely on hover), lists the copies.
- Row actions appear only when `can_modify`: «Editar» and «Eliminar».
- «Eliminar» opens a `ConfirmDialog` with `tone="danger"`:
  - Title: «¿Eliminar la medición del {fecha}?»
  - Body: «Se eliminarán también los pliegues cutáneos y la explicación de IA de esta fecha, si existen. Esta acción no se puede deshacer.»
  - Confirm button: «Eliminar».
- The parent mode is unchanged: no badge and no actions.

## Group session (`/anthropometry/session`)

1. **Picker**:
   - A date (default today).
   - A category filter (chips).
   - A list of athletes with a checkbox, the last evaluation date, and a «Medido hoy» badge when `has_record_on_date`.
   - «Seleccionar todos los visibles».
   - «Empezar jornada (N)».
   - At 360 px the list is stacked cards; there is no table.
2. **Queue**:
   - The header shows «3 de 12» with a progress bar.
   - The current athlete's name and category are shown.
   - It embeds the single-capture component in the chosen mode, date locked to the session date.
   - After a save: a toast «Guardado», then the next pending athlete.
   - Secondary actions: «Omitir por hoy» and «Ver lista» (a sheet listing pending, measured and skipped, where you can jump to any pending or skipped athlete).
   - If eligible, the post-save screen also offers «Agregar pliegues». It navigates to the 046 wizard with `?returnTo=/anthropometry/session`, and the wizard's finish or cancel returns to the queue.
3. **Summary**:
   - Three sections: Medidos (a link to each record, with a «Revisar» badge if warnings), Omitidos (a «Medir ahora» button) and Pendientes.
   - «Terminar jornada» clears the store.
- A reload loses the session (clarification 1). A new session shows «Medido hoy» on those already saved.

## Field guide

- The «Descargar instructivo» button already exists (046, `FieldGuideDownloadButton`).
- The button is also shown on the capture page's Preparación step.

## Copy added during implementation

Extra Spanish strings introduced beyond the copy listed above:

- Capture page (`AnthropometryCapturePage`): title «Nueva medición»; subtitle fallback «Peso, tallas y envergadura.»; back link «Volver al perfil»; loading «Cargando deportista...»; errors «No se pudo cargar el deportista. Revisa tu conexión e intenta de nuevo.» / «No encontramos este deportista.»; toast «Medición guardada.»
- Capture component (`AnthropometryCapture`): «Modo de captura», «Guiado», «Rápido», «Anterior»; offline «Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.» and «Necesitas conexión a internet para registrar mediciones.»; generic error «No se pudo guardar la medición. Intenta de nuevo.»; same-date dialog «Ya existe una medición de esta fecha» with «Abrir la existente» and «Cambiar la fecha» (or «Cerrar» when the date is locked by a session).
- Edit page (`AnthropometryEditPage`): title «Editar medición»; back link «Volver al perfil»; loading «Cargando medición...»; errors «No se pudo cargar la medición. Revisa tu conexión e intenta de nuevo.» / «No encontramos esta medición.»; toast «Medición actualizada.»; «Solo quien tomó esta medición o un administrador puede modificarla.»; «Ya existe una medición de esta fecha. Elige otra fecha o corrige la medición existente.»; «Los pliegues cutáneos se miden desde los 9 años. Esta evaluación no admite medición.»; interval message «Ya hay una medición de pliegues reciente. Entre dos mediciones debe pasar un intervalo mínimo para que el cambio sea confiable…».
- Session page (`MeasurementSessionPage`): title «Jornada de medición»; subtitle «Mide a varios deportistas seguidos en la misma fecha.»; back link «Volver a atletas»; loading «Cargando deportistas...» / «Cargando jornada...»; error «No se pudo cargar la lista de deportistas.»; list label «Deportistas»; «Sin mediciones»; progress label «Avance de la jornada»; «Guardado: <nombre>.»; info toast «Ya tenía una medición en esta fecha. Quedó en «Medidos».»; summary sections «Pendientes», «Omitidos», «Medidos».
- Skinfold capture page (`SkinfoldCapturePage`): back link «Volver a la jornada» when opened with `returnTo` from a session, otherwise «Volver al perfil».

### Session decisions

- «Seleccionar todos los visibles» skips athletes already marked «Medido hoy».
- «Abrir la existente» inside a session marks the athlete as measured with the existing record.
- The «N de M» progress indicator is `min(done + 1, total)`.
