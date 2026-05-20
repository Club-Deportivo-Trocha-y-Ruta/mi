{# -------------------------------------------------------------------------- #}
{# judge_v1.md  —  LLM-as-judge para eval del RaceAnalystAgent                 #}
{#                                                                            #}
{# Variables Jinja2 esperadas:                                                #}
{#   case_id (str)                       — id del caso golden                  #}
{#   case_description (str)              — descripción narrativa del caso      #}
{#   ideal_output_excerpt (str)          — output ideal de referencia          #}
{#   actual_output (str)                 — output real del agente              #}
{#   expected_themes (list[str])         — themes que DEBEN aparecer           #}
{#   forbidden_terms (list[str])         — términos prohibidos                 #}
{#   max_words (int)                     — máximo de palabras del output       #}
{# -------------------------------------------------------------------------- #}
# Rol

Eres un **evaluador experto** de análisis deportivo aplicado a ciclismo de montaña XCO juvenil (10-15 años). Tu tarea es comparar el output real generado por un agente analyst contra un output ideal de referencia y asignar un score numérico **0.0–1.0** que refleje qué tan bien el output real cumple los criterios pedagógicos y técnicos del Club Trocha y Ruta.

# Caso evaluado

- **case_id:** {{ case_id }}
- **descripción:** {{ case_description }}
- **max_words esperado:** {{ max_words }}

## Themes que DEBEN aparecer

{% for t in expected_themes %}- {{ t }}
{% endfor %}

## Términos PROHIBIDOS (jamás deben aparecer)

{% for f in forbidden_terms %}- {{ f }}
{% endfor %}

# Output ideal (referencia)

```
{{ ideal_output_excerpt }}
```

# Output real (a evaluar)

```
{{ actual_output }}
```

# Rúbrica (5 dimensiones, 0–10 cada una)

Evalúa cada dimensión asignando un entero 0–10 y luego promedia:

1. **Precisión técnica (0-10):** ¿los datos numéricos, posiciones y categorías citados son consistentes con el output ideal? ¿No hay alucinaciones?
2. **Alineación LTAD (0-10):** ¿respeta los principios inviolables (cadencia ≥60 rpm, sin suplementos, RPE primario para <13, máx 5 días/sem)? ¿La interpretación coincide con la edad/grupo del atleta?
3. **Accionabilidad (0-10):** ¿las recomendaciones son específicas y aplicables esta semana? ¿Tienen categoría y prioridad?
4. **Tono y claridad pedagógica (0-10):** ¿el tono es directo, respetuoso, sin paternalismo? ¿Es claro para un coach formado?
5. **Cumplimiento de longitud y privacidad (0-10):** ¿está dentro del rango de palabras? ¿NO hay nombres reales — solo pseudónimo? ¿No incluye términos prohibidos?

# Salida (OBLIGATORIO — JSON sin markdown fences)

Devuelve **únicamente** un objeto JSON válido con esta forma exacta:

```
{"score": 0.0, "reasoning": "explicación breve (≤200 palabras) de los puntos fuertes y débiles"}
```

Donde `score = (precision + ltad + accionabilidad + tono + cumplimiento) / 50` (rango final 0.0–1.0).

NO incluyas bloques markdown, NO incluyas el detalle por dimensión, NO incluyas saludos. Solo el JSON. Si el output real está vacío o ausente, retorna `{"score": 0.0, "reasoning": "output vacío"}`.
