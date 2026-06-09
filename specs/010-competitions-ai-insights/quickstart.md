# Quickstart: 010-competitions-ai-insights

## Run locally
```bash
# Backend (needs AI_ENABLED=true; AI calls can be stubbed via set_graph_factory in tests)
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Tests
cd backend && pytest tests/routers/test_race_event_runs.py tests/services/test_compute_metrics_season.py -q
cd frontend && npx vitest run src/components/competitions
```

## Manual verification path (coach: entrenador@trochyruta.com / Coach2026!)
1. **Insights tab launch (US1)**: open `/competitions/{id}?tab=insights` for an event with imported results → "Analizar con IA" visible → launch → per-athlete progress rows → approve HITL steps → insights appear in the tab. Refresh mid-run → progress restored (FR-012). Event without results → button disabled + tooltip (FR-002). Parent login → no launch controls (FR-001).
2. **Season context (US2)**: athlete with ≥2 válidas → insight contains "Contexto de temporada" with comparatives + progression label; athlete with 1 válida → "primera referencia de la temporada", no comparisons (SC-002).
3. **Post-import offer (US3)**: complete an import commit → success panel shows "Analizar con IA ahora" → accepts → lands in Insights tab with run in progress; declining does nothing.
4. **Per-athlete row action (US4)**: Results tab → club athlete row → launch action; if a fresh insight exists → ConfirmModal before re-run.
5. **Chat (US5)**: Insights tab → "Preguntar a la IA" panel → ask about the válida → grounded answer; with `AI_ENABLED=false` → unavailable message, module still usable.
6. **Safeguards (FR-009/010)**: set `RACE_AI_BUDGET_USD_30D=0` → launch blocked with budget copy (503); saturate 10 runs → backpressure items with retry.

## es-CO copy inventory (product strings — keep in Spanish)
- "Analizar con IA" / "Analizar con IA ahora" / "Re-ejecutar" (existing) / "Reintentar pendientes"
- "La competencia no tiene resultados importados."
- "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo."
- "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos."
- "Ya hay un análisis en curso para este deportista."
- "El asistente de IA no está disponible en este momento."
- "Análisis en curso…" / "Completado" / "Parcial: N de M completados"
- "Primera referencia de la temporada" (insight content rule)

## Key reuse map (do not rebuild)
| Need | Reuse |
|---|---|
| Run lifecycle/polling/HITL | `frontend/src/hooks/ai/useRaceRun.ts` (`useRunStatus`, `useApproveStep`, `useRunResult`) |
| Per-athlete launch | `startAthleteRun` (`src/api/athleteRaceAnalysis.ts`) |
| Insights listing | `useClubInsightsByRace` + `InsightsTab` cards |
| Confirmation dialogs | `ConfirmModal` (`src/components/common/`) |
| Backend run creation | `submit_run()` + `StartRunRequest` (`app/routers/race_analysis.py`) |
| Event→runs resolution | `run_staleness.invalidate_runs_for_event()` logic |
| Budget/backpressure | `check_budget()`, `RunBackpressureError` — unchanged |
