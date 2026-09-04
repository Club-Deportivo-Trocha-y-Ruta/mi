# Contract — band vocabulary (Res. 2465/2016 on WHO 2007)

Single definition of cut-offs (backend) and labels (frontend). Any surface that names a band reads this table.

## Cut-offs (backend `services/growth.py`, unchanged functions)

| Indicator | Z range | `NutritionalStatus` value |
|---|---|---|
| height_for_age | z < −2 | `retraso_talla` |
| | −2 ≤ z < −1 | `riesgo_retraso_talla` |
| | −1 ≤ z ≤ 2 | `talla_adecuada` |
| | z > 2 | `talla_alta` (informational) |
| bmi_for_age | z < −2 | `delgadez_severa` |
| | −2 ≤ z < −1 | `delgadez` |
| | −1 ≤ z ≤ 1 | `adecuado` |
| | 1 < z ≤ 2 | `sobrepeso` |
| | z > 2 | `obesidad` |
| weight_for_age (≤ 10 y only) | same shape as height (low / watch / ok / high) | mapped client-side to the height vocabulary labels "Peso bajo" … |

Frontend `classifyBand(indicator, z)` MUST reproduce this table exactly (parity test against 10 z values per indicator). It is used only as a fallback for rows without stored values.

## Labels and tone (frontend `lib/growth/bands.ts`)

| Value | Coach label | Family label | Tone | Referral hint (coach only) |
|---|---|---|---|---|
| `retraso_talla` | Talla baja | Por debajo del rango esperado | danger | Derivar a médico |
| `riesgo_retraso_talla` | En vigilancia | Un poco por debajo del promedio | warning | — |
| `talla_adecuada` | Adecuada | Dentro del rango esperado | success | — |
| `talla_alta` | Talla alta | Por encima del promedio | neutral | — |
| `delgadez_severa` | Delgadez | Por debajo del rango esperado | danger | Derivar a nutricionista |
| `delgadez` | Riesgo de delgadez | Un poco por debajo del rango | warning | — |
| `adecuado` | Adecuado | Dentro del rango esperado | success | — |
| `sobrepeso` | Sobrepeso | Por encima del rango esperado | warning | — |
| `obesidad` | Obesidad | Por encima del rango esperado | danger | Requiere evaluación |

Narratives: the existing sentences in `bands.ts` (family-safe) are kept, re-keyed to these values; the coach view shows the narrative beneath the curve, the family view shows it inside the card.

Rules:

- Tone maps 1:1 to `StatusBadge` status; every badge renders icon + label (Constitution III).
- Family surfaces never render the coach label; coach surfaces may render both (label + narrative).
- Source caption on every coach classification: "OMS 2007 · Res. 2465/2016". When `growth_source` is `null`/`CDC` (not recomputed yet) the caption reads "Referencia anterior — pendiente de actualizar".
- The IMC caveat stays: "El IMC puede subestimar adiposidad en atletas. Úsese como referencia." (coach only).
