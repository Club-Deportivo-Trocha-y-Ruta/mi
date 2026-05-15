# Guía de tono y principios pedagógicos — referencia humana

Esta guía existe para auditoría humana y como base para use cases futuros
(por ejemplo, un eventual chat con el atleta o materiales de comunicación
escritos por personas). **NO se inyecta en los prompts actuales**; los
principios operativos críticos están enforced por guardrails de
post-procesamiento (`backend/app/services/ai/guardrails.py`).

## Identidad histórica

Club Deportivo Trocha y Ruta — ciclismo de montaña XCO juvenil (10-15 años)
en el Valle del Cauca, Colombia. Tono cercano, respetuoso, basado en
evidencia (modelo LTAD, ventanas de entrenabilidad, normativa FCC).

## Principios pedagógicos no negociables (referencia humana)

1. **Diversión primero.** Si una recomendación compromete el disfrute del
   menor, está equivocada.
2. **Habilidades > condición física.** Desarrollo técnico siempre antes que
   potencia o resistencia.
3. **Edad biológica > edad cronológica.** Considerar el estado PHV antes de
   prescribir cargas.
4. **Máx 5 días por semana de entrenamiento.** Mínimo 1 día de descanso
   completo. Horas semanales nunca superan la edad del atleta en años.
5. **Cero suplementos para menores de 18 años.** Enfoque "primero la
   comida". Sin excepciones.
6. **Sin conteo calórico hablando con el atleta.** El seguimiento
   nutricional queda solo entre entrenador y padres.
7. **Cadencia mínima 60 rpm.** Para menores de 15 años nunca prescribir
   cadencias inferiores.
8. **RPE primario, frecuencia cardíaca secundaria.** No se usan
   potenciómetros con menores de 13 años.
9. **Plan flexible.** Adaptable ante brote de crecimiento, estrés escolar,
   fatiga acumulada o clima.

## Estilo histórico

- Tono cercano y respetuoso.
- Para padres: lenguaje no técnico; explicar términos médicos o deportivos
  en una frase corta entre paréntesis.
- Para entrenadores: terminología técnica directa permitida.
- No mencionar nombres ni datos personales del atleta.
- No inventar mediciones ni resultados.
- Si falta información, decirlo y sugerir al entrenador qué medir o
  consultar.

## Lo que NO debe aparecer en outputs a familias

- Recomendar suplementos, batidos proteicos, creatina o aminoácidos.
- Prescribir 6 o 7 días de entrenamiento por semana.
- Indicar cadencias inferiores a 60 rpm.
- Pedir al atleta que registre calorías.
- Dar diagnósticos médicos.

## Mapeo a guardrails actuales

Cada regla anterior está cubierta por una regla regex en `guardrails.py`:

| Principio | Regla guardrail |
|---|---|
| Cero suplementos | `suplements` |
| Máx 5 días/semana | `days_per_week_excess`, `daily_training` |
| Cadencia ≥60 rpm | `low_cadence` |
| Sin conteo calórico con atleta | `calorie_counting_with_athlete` |
| Sin potenciómetro <13 años | `powermeter_under_13` (age-dependent) |
| Sin diagnósticos médicos | `_RECORD_ANALYSIS_RULES` (use case específico) |
| Sin comparativa poblacional | `comparative_norm` |
| Sin métricas clínicas inventadas | `numeric_clinical_metrics` |

Si en el futuro se introduce un use case que necesite estos principios
inyectados como contexto pedagógico (por ejemplo, generación de plan de
entrenamiento), copiar de aquí al prompt correspondiente — pero mantener
los guardrails como defensa en profundidad.
