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
 *   - distribution    — admin + coach + parent (pseudonimizado)
 *   - evolution       — admin + coach + parent
 *
 * Privacidad: las funciones jamás reciben datos personales en los
 * params — todas las requests usan el ``athlete_id`` que viene de la
 * ruta /athletes/{id}. Los responses pasan por schemas con
 * ``extra="forbid"`` en backend (sin athlete_id/competitor_id/etc).
 */
import { apiClient } from "@/api/client";
import type {
  AthleteInsightDetailOut,
  AthleteInsightListResponse,
  AthleteInsightsParams,
  AthleteRunListResponse,
  AthleteRunsParams,
  AthleteStartRunBody,
  AvailableRaceEvent,
  DistributionResponse,
  EvolutionMetric,
  EvolutionResponse,
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
// Analytics — distribution + evolution
// ---------------------------------------------------------------------------

export async function getAthleteDistribution(
  athleteId: number,
  season: number,
  validaNum: number,
): Promise<DistributionResponse> {
  const response = await apiClient.get<DistributionResponse>(
    `${buildBase(athleteId)}/distribution`,
    { params: { season, valida_num: validaNum } },
  );
  return response.data;
}

export async function getAthleteEvolution(
  athleteId: number,
  season: number,
  metric: EvolutionMetric,
): Promise<EvolutionResponse> {
  const response = await apiClient.get<EvolutionResponse>(
    `${buildBase(athleteId)}/evolution`,
    { params: { season, metric } },
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
