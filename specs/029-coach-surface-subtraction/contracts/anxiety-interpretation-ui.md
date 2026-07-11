# Contract — Anxiety On-Demand Interpretation UI

UI contract for wiring the existing, tested interpretation capability into the individual anxiety view (FR-009, decision D2). No backend change; documents the existing endpoint this UI calls and the states it must render. Constitution Principle V governs every state below — none of them may weaken coach-only access, the consent gate, baseline-anchored wording, or the rule-based fallback.

## Backend endpoint consumed (unchanged, already shipped)

```
POST /api/anxiety/assessments/{assessment_id}/interpret
```

- Auth: coach/admin only (`require_role([admin, coach])`, `backend/app/routers/anxiety.py:80,438`).
- 200 → `InterpretationResponse { assessment_id, interpretation: Interpretation, source: "llm" | "rule", model: string | null }` (`types/anxiety.types.ts:94-99`).
- 422 → assessment has no answers yet (`status == pending`) — `"La evaluación aún no tiene respuestas para interpretar."` (`routers/anxiety.py:442-446`).
- 409 → would map to `consent_missing` via the existing generic `mapAnxietyError` (`api/anxiety.ts:170-171`) if the backend ever returns it from this endpoint; **today it does not** (verified — no consent check exists in `interpret_one`). See "Known limitation" below.
- Client call: `interpretAssessment(id)` (`api/anxiety.ts:85-95`) via `useInterpretation(id)` (`hooks/anxiety/useAnxietyAssessments.ts:85-94`), already implemented, already covered by the mutation's own key/invalidation behavior.

## Mount point

`components/anxiety/IndividualPanel.tsx`, below the scores table (after the flags block, or directly beneath the table — implementation's choice, no visual mock exists yet). Receives `series: AthleteSeries` (unchanged prop) and derives `latest = series.points.at(-1)`.

## States

| State | Trigger | UI | Component(s) |
|---|---|---|---|
| **Not interpretable** | `series.points.length === 0`, or `latest.cognitive === null` (proxy for "assessment still pending", see `research.md` R4) | `AnalyzeButton` not rendered at all (not merely disabled) | — |
| **Idle** | `latest.cognitive !== null`, no interpretation requested yet this session | `AnalyzeButton` visible, label "Analizar con IA" | `AnalyzeButton.tsx` (unchanged) |
| **Loading** | `mutation.isPending` | Button disabled, label "Analizando… (puede tardar)"; helper text "Si el servidor estaba inactivo, la primera respuesta puede tardar ~50 s" (cold-start-aware copy already written) | `AnalyzeButton.tsx:38-44` (unchanged) |
| **Success (LLM)** | `mutation` resolves, `source === "llm"` | `InterpretationPanel` renders: resumen, per-dimension (cognitiva/somática/autoconfianza), estrategias, athlete-facing message (mastery-climate box), flags (amber alert box if any); header badge "IA" | `InterpretationPanel.tsx` (unchanged) |
| **Success (rule fallback)** | `mutation` resolves, `source === "rule"` | Same `InterpretationPanel`, header badge shows "Reglas" (`title="Generada por reglas (respaldo)"`) instead of "IA" — this **is** the graceful-degradation state the constitution requires, not an error | `InterpretationPanel.tsx:19-30` (unchanged) |
| **Error** | `mutation` rejects | Inline `role="alert"` text below the button via `mapAnxietyError(err).message` (`AnalyzeButton.tsx:26,45-49`, unchanged) | `AnalyzeButton.tsx` |
| **Consent-blocked** | Backend returns 409 (theoretical today — see limitation below) | Same inline `role="alert"` path renders `COPY.consent_missing` (`api/anxiety.ts:147-149`) — no new copy needed, already written for the creation flow and generic enough to reuse | `AnalyzeButton.tsx` (unchanged) |

## Known limitation (documented, not silently assumed away)

Guardian-consent for `psychological_assessment` is enforced by the backend **only when an assessment is created** (`services/anxiety/assessments.py:114-115`). Once an assessment exists, nothing in the read/interpret path re-checks consent — this is true today of the entire anxiety read surface (scores, series, group triage), not something this feature changes. Practically: the "Consent-blocked" row above is reachable only if the backend is later changed to re-check consent on `/interpret` (a fast-follow, out of scope per FR-009's explicit "no server-side changes"). Until then, the safeguard this feature actually delivers is: *an interpretation can only ever be requested for an assessment that could only have been created with consent in the first place* — identical to the guarantee the rest of the shipped module already relies on. This is documented here so it is a conscious, named scope boundary rather than a gap discovered later.

## Non-negotiables carried over unchanged (Principle V)

- Coach/admin-only — enforced server-side (`_coach_or_admin` dependency), unaffected by this UI change.
- No diagnostic labels — `Interpretation`'s shape (`resumen`, `por_dimension`, `estrategias`, `mensaje_para_el_atleta`, `banderas`) has no field for a clinical label; the UI renders exactly these fields and nothing else.
- Baseline-anchored — the interpretation text itself is generated server-side against the athlete's baseline; this UI does not compute or alter wording.
- Mastery climate — `mensaje_para_el_atleta` renders in its own visually-distinct box (`InterpretationPanel.tsx:69-71`), unchanged.
- Rule-based fallback — the "Success (rule fallback)" row above, not treated as an error state.
- Human-in-the-loop — this is an on-demand coach action; nothing here sends anything to an athlete or parent.

## Regression test required (Principle II)

`components/anxiety/__tests__/IndividualPanel.test.tsx`: wrap existing renders in `QueryClientProvider` (newly required once `AnalyzeButton`'s `useMutation` is in the tree) and add at least one test proving: button appears when the latest point is interpretable, clicking it renders `InterpretationPanel` with the mutation's resolved data (mock `POST .../interpret` via MSW, both `source: "llm"` and `source: "rule"` cases), and the button does not render when `series.points` is empty or the latest point's `cognitive` is `null`.
