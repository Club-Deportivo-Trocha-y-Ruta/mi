# Quickstart: validating season comparison groups

**Feature**: 039 · Prerequisites: `backend/.venv` active, `frontend/node_modules` installed. MySQL only for the opt-in lanes.

## 1. Backend offline lane (default)

```bash
cd backend && source .venv/bin/activate
pytest tests/services/race/test_comparison_groups.py \
       tests/services/race/test_analytics.py \
       tests/services/race/test_analytics_charts.py \
       tests/routers/test_athlete_race_analysis_evolution_groups.py \
       tests/services/training/test_newsletter_builder.py \
       tests/test_newsletter_builder_024.py \
       tests/services/race/ai/nodes/test_compute_metrics.py \
       tests/services/test_compute_metrics_season.py -q
ruff check
```

Expected: all green. Key assertions to look for:
- `split_progression` puts cup rows under their `series_id` and championships apart; two cups stay separate (US4).
- `build_evolution(series_id=<cup>)` returns only cup points, `groups` lists cup + championships in order, `confidence` computed on the filtered series.
- Parent requesting another athlete's evolution with `series_id` → denied.
- Newsletter `charts_context.cups[0].points_accumulated[-1].y == standings total` for the fixture athlete; `championships[0]` has `field_size`, `percentile`, `gap_pct`; a DNF championship yields `finished=false` and nulls.
- `_compute_season_comparative` for a championship → `([], "first_reference")`; for a cup round → priors only from the same `series_id`.

## 2. MySQL dialect lane (opt-in)

```bash
TEST_DATABASE_URL='mysql+aiomysql://…/<db>_test' pytest -m mysql tests/services/race/test_mysql_dialect.py -q
```

Expected: the extended `build_evolution` CTE returns `series_id` / `series_name` / `series_level` under MySQL enums.

## 3. Newsletter PDF with real data (SC-1 style)

```bash
# with MySQL up and .env pointing to a dev copy
uvicorn app.main:app --reload
# as coach: regenerate the newsletter of an athlete who raced the CD and the CN, then download the PDF
```

Expected in the PDF: heading `Evolución en la Copa Valle de Ciclomontañismo 2026` with three charts over V1..Vn only; section `Campeonatos` with one card per championship (position, pelotón, gap al P1, percentil) and the note sentence; no CD/CN on any chart axis. For an athlete without championships the section is absent.

## 4. Frontend

```bash
cd frontend
npm run typecheck
npx vitest run src/components/athletes/ai/__tests__/EvolutionChart.test.tsx \
               src/components/athletes/ai/__tests__/MiniSparkline.test.tsx \
               src/components/athletes/ai/__tests__/a11y.v2.test.tsx
```

Expected: selector `Competencia` lists cups then championships, default first cup; selecting a championship shows `ChampionshipReadingCard` + table and no line; `Cto. Nal.` label on national; jest-axe zero violations. Manual check on `npm run dev`: switch groups on an athlete with CD + CN; sparkline in Panorama shows only cup rounds.

## 5. AI pipeline

```bash
cd backend
pytest tests/services/race/ai -q                    # offline, FakeLLM
RACE_AI_API_KEY=… pytest -m golden -q               # blocking gate, needs Gemini key
```

Expected: `evals/race_analyst/results/last_run.md` shows case 009 scored and the average ≥ 0.75. Launch an analysis for the national championship from the competitions page (anchored `event_id`) and confirm the insight labels it `Cto. Nacional` and never states a position delta against a cup round.

## 6. Post-deploy smoke

```bash
curl -s https://mi-2yzi.onrender.com/health
# authenticated: GET /api/athletes/{id}/race-analysis/evolution?season=2026&metric=ranking&series_id=<cup>
```

Expected: 200 with `groups` populated and `series` limited to the cup.

See [contracts/](./contracts/) for payload shapes and [data-model.md](./data-model.md) for field rules.
