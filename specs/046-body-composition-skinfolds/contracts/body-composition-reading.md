# Contract — Body-composition reading: change classifier, traffic light, copy (feature 046)

Pure function `build_reading(...)` in `backend/app/services/body_composition.py`; nothing here is persisted. All thresholds come from `Settings` (data-model §4). This contract is the single source for backend tests, the frontend band vocabulary (`lib/growth/bands.ts`) and the AI leaf codes.

## 1. Inputs

`latest_set`, `previous_set` (the most recent earlier set with ≥ 1 non-declined site, any gap), their records (`weight_kg`, `standing_height_cm`, `bmi_z_score`, `maturation_status`, `evaluation_date`), athlete `sex`, `GrowthVelocity` from `growth_summary` (may be `None`), expected velocity range for the stage, FUPRECOL percentiles for triceps and subscapular of the latest set (may be unavailable).

## 2. Leg codes

| Leg | Code | Rule |
|---|---|---|
| Σ4 change | `none` | no previous set or Σ4 missing in either |
| | `within_noise` | \|Δ\| < `BODY_COMP_MDC_SUM4_MM` |
| | `up_real` / `down_real` | Δ ≥ threshold / Δ ≤ −threshold |
| Weight | `up` | Δweight ≥ +1.5 kg |
| | `flat_or_down` | otherwise |
| | `unavailable` | no previous record |
| Height | `growing` | Δheight ≥ 0.7 cm |
| | `stalled` | otherwise |
| Velocity | `within_or_above` / `below` / `unavailable` | `cm_per_year` vs expected range lower bound; `unavailable` when velocity is `None` or `interval_short` |
| BMI-z | `ok` / `drop_moderate` / `drop_large` / `unavailable` | Δz > −0.5 / −1.0 < Δz ≤ −0.5 / Δz ≤ −1.0 |
| Reference (each of triceps, subscapular) | `low_extreme` < P5, `low` P5–P10, `normal`, `high` P85–P95, `high_extreme` ≥ P95, `unavailable` | FUPRECOL by sex and age; unavailable outside 108–216 months or when the site is declined |
| Growth explanation | `expected_pubertal_gain` | sex F, stage circa/post PHV, weight `up`, velocity `within_or_above` |
| | `pre_spurt_accumulation` | stage pre-PHV, velocity `within_or_above` |
| | `post_phv_lean_gain` | sex M, stage post PHV, Σ4 `within_noise` or `down_real` with weight `up` |
| | `none` | otherwise |

## 3. Band rules (evaluated in order; first match wins)

1. `sets_count == 0` → no reading (`has_data=false`).
2. **rojo** — `sets_count ≥ 2` and Σ4 `down_real` and weight `flat_or_down` and height `growing`. Reason `energy_availability_pattern`.
3. **ámbar** — any of:
   - Σ4 `down_real` with weight `flat_or_down` but height `stalled`/`unavailable` → `sum_down_unexplained`;
   - Σ4 `up_real` and growth explanation `none` → `sum_up_unexplained`;
   - Σ4 `up_real` and velocity `below` → `sum_up_velocity_low`;
   - any reference code `low_extreme` or `high_extreme` → `reference_extreme`;
   - BMI-z `drop_large` → `bmi_z_drop`;
   - velocity `below` on the latest and the previous cycle (two consecutive) → `velocity_low_persistent`.
4. **verde** — everything else, with reason:
   - Σ4 `within_noise` → `no_real_change`;
   - `up_real` + `expected_pubertal_gain` → `expected_pubertal_gain`;
   - `up_real` + `pre_spurt_accumulation` → `pre_spurt_accumulation`;
   - `post_phv_lean_gain` → `post_phv_lean_gain`;
   - `sets_count == 1` → `first_set` (reference context may still add a note);
   - otherwise `stable`.

`legs_missing` lists every leg that was `unavailable`/`none` because data was absent. A missing `previous_set` or `height`/`weight` leg makes rule 2 impossible (documented in the reason).

## 4. Copy (español, Colombia)

### Family (band + one sentence; the only body-composition text a parent ever sees)

| Band | `family_label` | `family_sentence` |
|---|---|---|
| verde | En su curva esperada | La composición corporal de tu hijo/a se mantiene dentro de lo esperado para su etapa de desarrollo. Sigue acompañando el proceso: esto va de la mano de un crecimiento saludable. |
| ámbar | En observación | Notamos un cambio que vale la pena conversar. El entrenador se pondrá en contacto contigo para revisarlo juntos; no es una alarma, es una oportunidad de acompañar mejor a tu hijo/a. |
| rojo | Requiere acompañamiento profesional | Identificamos una señal que amerita una valoración con un profesional de la salud. El entrenador ya está coordinando contigo los siguientes pasos; este acompañamiento adicional es normal y forma parte de cuidar bien a los deportistas en crecimiento. |

### Coach (`coach_reason`, one sentence per reason code)

| Reason code | Sentence |
|---|---|
| `no_real_change` | Sin cambio real en la suma de pliegues desde la última toma (dentro del margen de medición). |
| `expected_pubertal_gain` | La suma de pliegues subió de forma real, con peso y talla creciendo dentro de lo esperado: patrón habitual alrededor del pico de crecimiento en niñas. |
| `pre_spurt_accumulation` | La suma de pliegues subió de forma real con la talla creciendo a ritmo esperado: acumulación previa al estirón, frecuente en esta etapa. |
| `post_phv_lean_gain` | Peso arriba con pliegues estables o a la baja después del pico de crecimiento: ganancia de masa magra esperada. |
| `first_set` | Primera toma de pliegues: hace falta una segunda toma (≥ 90 días) para leer una tendencia. |
| `stable` | Composición corporal estable respecto a la toma anterior. |
| `sum_up_unexplained` | La suma de pliegues subió más allá del margen sin un patrón de crecimiento que lo explique: vale una conversación en privado, sin cifras. |
| `sum_up_velocity_low` | La suma de pliegues subió de forma real mientras la velocidad de talla está por debajo de lo esperado: conversa en privado y revisa en la próxima toma. |
| `sum_down_unexplained` | La suma de pliegues bajó más allá del margen con el peso estancado; falta confirmar el crecimiento en talla para leer el patrón. |
| `reference_extreme` | Un pliegue está en el extremo de la referencia poblacional (≤ P5 o ≥ P95): es contexto, no un veredicto; observa la tendencia en la próxima toma. |
| `bmi_z_drop` | El índice de masa corporal para la edad cayó más de una desviación estándar: conversa con la familia y revisa alimentación con enfoque «comida primero». |
| `velocity_low_persistent` | La velocidad de talla lleva dos ciclos por debajo de lo esperado: revisa junto con la composición corporal y considera consultar. |
| `energy_availability_pattern` | Patrón combinado: la suma de pliegues cayó más allá del margen, el peso se estancó y la talla sigue creciendo. Compatible con baja disponibilidad energética. No es un diagnóstico: conversa con la familia en lenguaje neutro y considera remitir a un profesional de salud. |

### Coach escalation prompt (shown with ámbar/rojo, never to families)

- ámbar: "Sugerencia: conversa en privado con el/la deportista y la familia, sin mencionar números ni porcentajes. Si el patrón se repite en la próxima toma o aparecen otras señales (fatiga persistente, cambios de ánimo, enfermedad frecuente), pasa a seguimiento con la familia."
- rojo: "Esto NO es un diagnóstico. Conversa con la familia en lenguaje neutro (nunca calorías ni peso frente al/a la deportista) y coordina la remisión a un profesional de salud con la nota de remisión."

### Change reading (coach card)

- `within_noise`: "Dentro del margen de medición ({delta:+.1f} mm; umbral {threshold} mm)"
- `up_real` / `down_real`: "Cambio real ({delta:+.1f} mm; umbral {threshold} mm)"
- `none`: "Sin toma anterior comparable"

## 5. Test scenarios (SC-004, parametrised)

| Scenario | Inputs (synthetic) | Expected |
|---|---|---|
| A — girl circa→post PHV | Σ4 32→39, weight 38→42.5, height 148→152.5, velocity within, F | verde `expected_pubertal_gain` |
| B — boy post PHV | Σ4 28→27, weight 45→49.5, height 158→161, M | verde `post_phv_lean_gain` |
| C — energy-availability | Σ4 30→22, weight 40.0→40.5, height 145→148.5 | rojo `energy_availability_pattern` |
| D — single set, triceps ≥ P95 | one set, reference `high_extreme` | ámbar `reference_extreme`, never rojo |
| E — threshold edge | Σ4 Δ = 6.9 vs 7.0 | `within_noise` vs `up_real` |
| F — missing height leg | Σ4 30→22, weight flat, previous record without height delta | ámbar `sum_down_unexplained`, `legs_missing` contains `height` |
| G — all declined | six declined | no reading, `has_data=false`, interval counter unchanged |
