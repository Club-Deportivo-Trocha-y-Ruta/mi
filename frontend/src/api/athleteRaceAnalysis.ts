/**
 * API client del módulo athlete-race-analysis (FE-1).
 *
 * Endpoints implementados en BE-2 (ver
 * ``backend/app/routers/athlete_race_analysis.py``). Auth: JWT via
 * interceptor de :mod:`@/api/client`.
 *
 * Cobertura RBAC (el backend la enforza; aquí solo describimos):
 *   - insights*       — admin + coach + parent (parent filtra aprobados+activos)
 *   - runs (GET/POST) — admin + coach (parent => 403)
 *   - distribution    — admin + coach + parent (parent ve solo pseudónimos;
 *                        coach/admin ven display_name real de cada corredor,
 *                        incl. de otros clubes — ver DistributionChart.tsx,
 *                        feature 036 Open Question 2 / T037)
 *   - evolution       — admin + coach + parent
 *
 * Privacidad: las funciones jamás reciben datos personales en los
 * params — todas las requests usan el ``athlete_id`` que viene de la
 * ruta /athletes/{id}. Los responses pasan por schemas con
 * ``extra="forbid"`` en backend (sin athlete_id/competitor_id/etc).
 */
import { apiClient } from "@/api/client";
import type {
  AnswerInsightBody,
  AthleteInsightDetailOut,
  AthleteInsightListResponse,
  AthleteInsightsParams,
  AthleteRunListResponse,
  AthleteRunsParams,
  AthleteSeasonSummaryRunResponse,
  AthleteStartRunBody,
  AvailableRaceEvent,
  ClubInsightsByRaceResponse,
  DistributionResponse,
  EvolutionMetric,
  EvolutionResponse,
  RaceParticipationResponse,
  SeasonPanoramaResponse,
} from "@/types/athleteRaceAnalysis.types";

function buildBase(athleteId: number): string {
  return `/api/athletes/${athleteId}/race-analysis`;
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

export async function getAthleteInsights(
  athleteId: number,
  params?: AthleteInsightsParams,
): Promise<AthleteInsightListResponse> {
  const response = await apiClient.get<AthleteInsightListResponse>(
    `${buildBase(athleteId)}/insights`,
    { params },
  );
  return response.data;
}

export async function getAthleteInsight(
  athleteId: number,
  insightId: number,
): Promise<AthleteInsightDetailOut> {
  const response = await apiClient.get<AthleteInsightDetailOut>(
    `${buildBase(athleteId)}/insights/${insightId}`,
  );
  return response.data;
}

/**
 * POST /insights/{insight_id}/answer (feature 037, T104/T205).
 *
 * Responde a `structured.coach_question` y/o califica el insight
 * (`rating`: 1 útil / -1 no útil). Al menos un campo del body debe venir
 * — el backend responde 422 si ambos son `null`/`undefined`. Solo
 * coach/admin (parent → 403, insight de otro atleta → 404).
 */
export async function answerInsight(
  athleteId: number,
  insightId: number,
  body: AnswerInsightBody,
): Promise<AthleteInsightDetailOut> {
  const response = await apiClient.post<AthleteInsightDetailOut>(
    `${buildBase(athleteId)}/insights/${insightId}/answer`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export async function getAthleteRuns(
  athleteId: number,
  params?: AthleteRunsParams,
): Promise<AthleteRunListResponse> {
  const response = await apiClient.get<AthleteRunListResponse>(
    `${buildBase(athleteId)}/runs`,
    { params },
  );
  return response.data;
}

/** Inicia un run agéntico para el atleta. Backend responde con
 * ``{ run_id, status, started_at, status_url, estimated_seconds }`` —
 * reutilizamos el envelope de race-analysis v2.
 *
 * Devuelve solo lo mínimo necesario para el frontend (run_id es UUID
 * hex, NO la pk interna). Mantenemos el shape laxo para tolerar
 * campos extra del envelope.
 */
export interface StartAthleteRunResponse {
  run_id: string;
  status: string;
  started_at: string;
  status_url: string;
  estimated_seconds: number;
}

export async function startAthleteRun(
  athleteId: number,
  body: AthleteStartRunBody,
): Promise<StartAthleteRunResponse> {
  const response = await apiClient.post<StartAthleteRunResponse>(
    `${buildBase(athleteId)}/runs`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Season summary (on-demand)
// ---------------------------------------------------------------------------

/**
 * Shape LEGACY de ``POST /season-summary`` (feature 036, T040 —
 * `schemas/athlete_race_analysis.py::SeasonSummaryResponse`), síncrono:
 * no hay run agéntico polleable, así que no existen `run_id`/`status` —
 * para cuando la promesa resuelve, el resumen ya fue generado y
 * persistido. `insight_id` es la PK del insight (`valida_num=0`).
 *
 * Se mantiene tipado acá solo como referencia histórica — el backend de
 * este endpoint migra a un contrato asíncrono en feature 037 (T203, ver
 * `AthleteSeasonSummaryRunResponse` y `generateSeasonSummary` abajo).
 */
export interface SeasonSummaryResponse {
  insight_id: number;
  season: number;
  summary_text: string;
  prompt_version: string;
  validas_analyzed: number;
  generated_at: string;
}

/**
 * POST /season-summary (feature 037, T203/T205 — contrato v3).
 *
 * A diferencia del contrato legacy (feature 036), esta llamada lanza un
 * run agéntico (`analysis_kind="season"`) y responde `202 {run_id,
 * status}` de inmediato — el resumen se genera en background y se sigue
 * con `getRunStatus`/`useRunStatus` como cualquier otro run (ver
 * `api/raceAnalysis.ts`). El insight resultante aparece en
 * `getAthleteInsights` una vez el run se aprueba/completa.
 *
 * NOTA (T205, honestidad de estado): el router
 * `POST /athletes/{id}/race-analysis/season-summary` en el backend
 * **todavía no fue migrado** a este contrato (T203, Wave 2, fuera de mi
 * propiedad) — hoy sigue respondiendo 200 con el shape
 * `SeasonSummaryResponse` de arriba. Esta función ya implementa el
 * contrato de destino documentado en `data-model.md §API deltas` para
 * que Wave 3 (T302, `SeasonSummaryButton` + `AnalysisRunTimeline`) pueda
 * integrarse sin re-tocar el cliente HTTP; hasta que T203 aterrice, esta
 * llamada fallará el parseo de tipos en runtime real (ver open_issues del
 * reporte de la tarea).
 */
export async function generateSeasonSummary(
  athleteId: number,
): Promise<AthleteSeasonSummaryRunResponse> {
  const response = await apiClient.post<AthleteSeasonSummaryRunResponse>(
    `${buildBase(athleteId)}/season-summary`,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Analytics — distribution + evolution
// ---------------------------------------------------------------------------

export async function getAthleteDistribution(
  athleteId: number,
  season: number,
  eventId: number,
): Promise<DistributionResponse> {
  const response = await apiClient.get<DistributionResponse>(
    `${buildBase(athleteId)}/distribution`,
    { params: { season, event_id: eventId } },
  );
  return response.data;
}

export async function getAthleteRaces(
  athleteId: number,
  season: number,
): Promise<RaceParticipationResponse> {
  const response = await apiClient.get<RaceParticipationResponse>(
    `${buildBase(athleteId)}/races`,
    { params: { season } },
  );
  return response.data;
}

/**
 * `seriesId` (feature 039, `contracts/evolution-api.md`) restringe la
 * respuesta al grupo de comparación (copa o campeonato) indicado — se omite
 * del querystring cuando es `undefined` para pedir la temporada completa.
 */
export async function getAthleteEvolution(
  athleteId: number,
  season: number,
  metric: EvolutionMetric,
  seriesId?: number,
): Promise<EvolutionResponse> {
  const params: Record<string, unknown> = { season, metric };
  if (seriesId !== undefined) params.series_id = seriesId;
  const response = await apiClient.get<EvolutionResponse>(
    `${buildBase(athleteId)}/evolution`,
    { params },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Club insights by race — cross-atleta por válida (Sprint 3)
// ---------------------------------------------------------------------------

export interface ClubInsightsByRaceOpts {
  clubId?: number;
  latestOnly?: boolean;
  limit?: number;
}

export async function getClubInsightsByRace(
  raceEventId: number,
  opts: ClubInsightsByRaceOpts = {},
): Promise<ClubInsightsByRaceResponse> {
  const params: Record<string, unknown> = {};
  if (opts.clubId !== undefined) params.club_id = opts.clubId;
  if (opts.latestOnly !== undefined) params.latest_only = opts.latestOnly;
  if (opts.limit !== undefined) params.limit = opts.limit;
  const response = await apiClient.get<ClubInsightsByRaceResponse>(
    `/api/races/${raceEventId}/club-insights`,
    { params },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Season panorama — agregado cross-válida por temporada (PR3)
// GET /api/race-analysis/insights/season/{year} — coach/admin only.
// ---------------------------------------------------------------------------

export async function getSeasonPanorama(
  year: number,
  clubId?: number,
): Promise<SeasonPanoramaResponse> {
  const params: Record<string, unknown> = {};
  if (clubId !== undefined) params.club_id = clubId;
  const response = await apiClient.get<SeasonPanoramaResponse>(
    `/api/race-analysis/insights/season/${year}`,
    { params },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Calendar helper (independiente del athlete — vive en /race-events)
// ---------------------------------------------------------------------------

export async function getRaceEventsAvailableForCalendar(
  season: number,
): Promise<AvailableRaceEvent[]> {
  const response = await apiClient.get<AvailableRaceEvent[]>(
    `/api/race-events/available-for-calendar`,
    { params: { season } },
  );
  return response.data;
}
