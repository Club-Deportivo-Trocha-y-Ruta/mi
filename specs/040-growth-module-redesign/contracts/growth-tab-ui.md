# Contract — Growth tab UI (coach and family modes)

Location: `frontend/src/components/athletes/growth/` (new folder). Entry: `GrowthTab.tsx`, loaded with `React.lazy` from `routes/athletes/AthleteDetailPage.tsx` and `routes/parents/MyAthleteDetailPage.tsx` with `key={athlete.id}`.

## Component tree

```text
GrowthTab { athlete, mode, onRecordMeasurement? }
├── GrowthAlerts            ← summary.alerts → <Alert> rows (icon + text), same copy as dashboard
├── GrowthStatusRow         ← 4 × shared/StatCard (+ Sparkline) — coach only
│     Etapa · Velocidad talla · Talla / edad · IMC / edad
├── NextMeasurementCard     ← summary.measurement → StatusBadge (Vencida / Próxima / Al día / Sin medir)
├── FamilyStageCard         ← parent only: stage sentence (existing phvParentMessage), evaluated month-year
├── FamilyBandCards         ← parent only: 2 narrative cards (height, BMI) — no numerals
├── TrainingReadiness       ← coach only; rules from lib/growth/rules.ts; Collapsible "Ver todas"
├── GrowthCurveSection
│   ├── PercentileToolbar   ← indicator ToggleGroup · axis ToggleGroup (coach) · range toggle · view toggle · export
│   ├── PercentileChart     ← recharts ComposedChart (lazy chunk), role="img" + aria-label
│   ├── PercentileTable     ← visible <Table> (view="table"), also the a11y alternative
│   └── PercentileInterpretationBlock (existing; hideAdvanced when mode==="parent")
├── MaturationTimeline      ← coach only; SVG/CSS; text alternative
├── MorphologyCard          ← coach only; tiles → shared/StatCard
├── PHVExplanationCard      ← audience by mode; title "Explicación PHV"
├── AnthropometryHistory    ← compact mode (coach) / parent mode (existing)
└── ResearchReferences      ← coach only
```

## Props and state

See `data-model.md` §7. `GrowthTab` owns `indicator`, `axis`, `range`, `detail`, `view`. Children are controlled.

## Data

- `useAthlete(id)`, `useAnthropometry(id)` (existing), `useGrowthSummary(id)` (new, `api/growth.ts::getGrowthSummary`, Zod `GrowthSummarySchema`), `usePHVExplanationCached(id, audience)`.
- WHO reference rows: `import("@/data/growth-reference-who.json")` inside `PercentileChart` (dynamic) — never a static import outside the growth folder.
- Chart rows carry the record's **stored** `z_score` / `percentile` / `band`; only the reference curves are computed from LMS.

## States (per async surface)

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Status row / next measurement | `StatCard isLoading` skeletons | `records_count === 0` → `EmptyState` "Registra la primera medición" with CTA (coach) | `ErrorState` with retry (refetch summary only) |
| Curve | chart skeleton (fixed aspect box) | < 1 record → not rendered | `ErrorState` inside the card |
| Table | rows skeleton | "Sin mediciones" | same as curve |
| Family cards | skeleton | "Aún no hay mediciones" | `ErrorState` |
| Server cold start | existing `ServerWakingBanner` behaviour applies (no change) | | |

## Copy (español neutro, diacritics)

- Tiles: "Etapa", "Velocidad de talla", "Talla para la edad", "IMC para la edad"; hints "PHV estimado a los {age} años · hace {n} meses" / "en {n} meses"; "{v} cm/año · últimos {m} meses"; "esperado {a}–{b} cm/año (orientativo)"; "Se necesitan 2 mediciones"; "Intervalo corto: valor orientativo".
- Next measurement: "Próxima medición: {fecha} · cada {n} días en {etapa}"; badges "Al día" / "Próxima" / "Vencida" / "Sin medir".
- Toolbar: "Talla" / "IMC" / "Peso"; "Cronológica" / "Biológica"; "Ver 5–19 años" / "Ver alrededor de las mediciones"; "Detalle" (P10/P25/P75/P90); "Gráfica" / "Tabla"; "Descargar PNG".
- Curve legend: "Deportista", "Mediana (P50)", "P3–P97".
- Timeline: "Pre-PHV", "Estirón (Circa-PHV)", "Post-PHV"; caption "Offset {±x.x} · PHV estimado a los {age} años".
- Rules block: "Qué cambia en el entrenamiento" · "Ver todas las reglas" · statuses "Permitido" / "Con cuidado" / "No permitido".
- Family: titles "Etapa de desarrollo", "Estatura para su edad", "Peso para su estatura"; curve caption "Línea gris: promedio para su edad. Franja: rango esperado."

## Accessibility

- Chart: `role="img"` with an `aria-label` summarising indicator, number of measurements and latest band; visible table view is the alternative.
- All toolbar controls are `ToggleGroup`/`Button` with `min-h-12` (48 px) and visible focus rings; keyboard operable.
- Status conveyed by `StatusBadge` (icon + label); band fills carry no meaning.
- `prefers-reduced-motion`: recharts animations stay off.
- jest-axe: zero violations for `GrowthTab` in both modes, with and without records.

## Test ids (stable)

`growth-tab`, `growth-alerts`, `growth-status-row`, `growth-next-measurement`, `growth-curve`, `growth-curve-toolbar`, `growth-curve-table`, `growth-timeline`, `growth-rules`, `family-stage-card`, `family-band-cards`, `export-png-button` (kept).

## Removed

`GrowthCharts.tsx` longitudinal charts (`LongitudinalCharts`, "Maturity Offset vs Tiempo"), the page-local `StatCard` in both detail pages, the auto-select-growth effect, PHV colour maps in `TrainingReadiness.tsx` and `AthleteDetailPage.tsx`, the athlete-name chip in `TrainingReadiness`.
