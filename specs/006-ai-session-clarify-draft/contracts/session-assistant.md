# API Contract: Session Assistant

Two stateless endpoints. Both require an authenticated **coach or admin** who belongs to
`{club_id}` (admin bypasses club membership). Mirrors `monthly_reports.py` RBAC.

Base: `/api/clubs/{club_id}/session-assistant`

Common error responses:

| Status | When | Body (`detail`) |
|---|---|---|
| 401 | no/expired token | standard auth error |
| 403 | not coach/admin, or no access to club | `"No tienes acceso a este club."` |
| 422 | request invalid, or AI returned malformed/unsafe JSON after guardrails | neutral español message |
| 503 | AI disabled/unreachable, or call exceeded `ai_timeout_seconds` | `"El asistente no está disponible en este momento."` |

---

## 1) POST `/clarify`

Returns a single batch of 0–4 clarifying questions.

### Request
```json
{
  "intent_text": "salida de 90 min en La Cumbre, bajadas técnicas, grupo 13-15, faltan 12 días para la válida",
  "selected_athlete_ids": []
}
```
- `intent_text`: optional, ≤500 chars, any language.
- `selected_athlete_ids`: optional; used server-side only to compute aggregate age-mix.

### Response 200
```json
{
  "questions": [
    {
      "id": "q1",
      "header": "Grupo",
      "question": "¿Para qué grupo es la sesión?",
      "multi_select": false,
      "allow_other": true,
      "options": [
        { "label": "10-12 años", "description": "80% juego, sin intervalos estructurados" },
        { "label": "13-15 años", "description": "Máx 2 sesiones intensas por semana" },
        { "label": "Mixto", "description": "Ambos grupos juntos" }
      ]
    },
    {
      "id": "q2",
      "header": "Enfoque",
      "question": "¿Qué quieres priorizar?",
      "multi_select": true,
      "allow_other": true,
      "options": [
        { "label": "Técnica de bajada", "description": "Habilidad antes que fondo" },
        { "label": "Resistencia Z1-Z2", "description": "Base aeróbica suave" },
        { "label": "Diversión / juego", "description": "Formato lúdico" }
      ]
    }
  ],
  "model": "gemini-2.5-flash-lite"
}
```
- `0 ≤ questions ≤ 4`; each `2 ≤ options ≤ 4`. `questions: []` ⇒ client may call `/draft` directly.
- All coach-facing strings in español neutro and guardrail-scrubbed.

---

## 2) POST `/draft`

Returns an editable session draft. Accepts partial/empty answers.

### Request
```json
{
  "intent_text": "salida de 90 min en La Cumbre, bajadas técnicas",
  "selected_athlete_ids": [12, 15, 18],
  "answers": [
    { "question_id": "q1", "selected_labels": ["13-15 años"], "other_text": null },
    { "question_id": "q2", "selected_labels": ["Técnica de bajada", "Resistencia Z1-Z2"], "other_text": null }
  ]
}
```

### Response 200
```json
{
  "technical_focus": "Técnica de descenso en terreno suelto",
  "objectives": "Mejorar trazada y control de frenada en bajada; mantener cadencia ≥70 rpm.",
  "description": "CALENTAMIENTO (15 min): rodaje suave Z1 + movilidad...\nPARTE PRINCIPAL (55 min): 4 repeticiones de tramo técnico de bajada...\nVUELTA A LA CALMA (20 min): rodaje Z1 + estiramientos.",
  "duration_min": 90,
  "session_kind": "salida",
  "location": "La Cumbre",
  "scheduled_date": null,
  "scheduled_start_time": null,
  "athlete_call_up": "grupo_13_15",
  "notes": "Faltan ~12 días para una válida prioridad A: intensidad moderada, sin sobrecarga.",
  "model": "gemini-2.5-flash-lite"
}
```

### Field rules
- `technical_focus` ≤200, `objectives` ≤1000, `description` ≤2000, `duration_min` 15–240,
  `session_kind` ∈ `SessionKind`, `location` ≤200.
- `athlete_call_up` ∈ `{todos_convocados, grupo_10_12, grupo_13_15, ninguno}` — **criterion
  only**, no ids/names. Frontend resolves it to `convocados_athlete_ids` locally.
- `scheduled_date`/`scheduled_start_time` present only if stated in `intent_text`.
- All free-text fields scrubbed by `Guardrails`; principle violations → 422.

### Frontend handoff
The client maps `SessionDraftResponse` → `TrainingSessionFormValues`, resolving
`athlete_call_up` against the loaded roster, then prefills the wizard with
`reset(values, { keepDirtyValues: true })`. Pre-filled fields get a per-field "IA" marker
that clears once the coach edits the field.

---

## Privacy contract (Ley 1581 — minors)
- No athlete id or name is ever placed into the prompt context: `selected_athlete_ids` is
  converted to aggregate counts server-side and discarded before render.
- `ai_log_prompts` MUST remain false; logs reference counts only, never ids/names.
- Responses contain no minor PII; guardrail name-redaction runs on all output as defense.
