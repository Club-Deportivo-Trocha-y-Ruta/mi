/**
 * Tipos del módulo race-analysis v2 (Fase 6 frontend).
 *
 * Mirror de los Pydantic schemas en:
 *   - backend/app/schemas/race_ai.py
 *   - backend/app/services/race/schemas.py (ChatResponse, AnalysisOutput)
 *
 * Privacidad: estos schemas NUNCA llevan nombres reales — sólo
 * pseudónimos y run_id. La invariante la garantiza el backend
 * (test_race_analysis_privacy.py).
 */

// ---------------------------------------------------------------------------
// Enums (string literal unions para flexibilidad)
// ---------------------------------------------------------------------------

export type RunState =
  | "running"
  | "hitl_waiting"
  | "done"
  | "failed"
  | "cancelled"
  | "error"; // alias tolerante: el design usa "error" pero el backend emite "failed"

export type HITLDecision = "approve" | "reject" | "edit";

export type UseCase =
  | "race_progression"
  | "race_podium_gap"
  | "race_projection"
  | "race_season_summary";

// ---------------------------------------------------------------------------
// Start run
// ---------------------------------------------------------------------------

export interface StartRunRequest {
  athlete_id: number;
  season: number;
  /** Opcional: null = todas las válidas. */
  valida_nums?: number[] | null;
  explain_mode?: boolean;
  /** No formal en el backend pero algunos use_case llegan en payloads — campo opcional para futuro. */
  use_case?: UseCase;
}

export interface StartRunResponse {
  run_id: string;
  status: RunState;
  started_at: string;
  status_url: string;
  estimated_seconds: number;
}

// ---------------------------------------------------------------------------
// Polling / status
// ---------------------------------------------------------------------------

export interface RunEvent {
  seq: number;
  ts: string;
  type: string;
  node?: string | null;
  payload: Record<string, unknown>;
}

export interface RunStatusResponse {
  run_id: string;
  state: RunState;
  progress_pct: number;
  current_node?: string | null;
  started_at: string;
  estimated_seconds_remaining: number;
  new_events: RunEvent[];
  last_seq: number;
}

// ---------------------------------------------------------------------------
// HITL
// ---------------------------------------------------------------------------

export interface HITLDecisionRequest {
  decision: HITLDecision;
  /** Markdown editado (sólo si decision=edit). */
  edits?: string | null;
  notes?: string | null;
}

export interface HITLDecisionResponse {
  accepted: boolean;
  run_id: string;
  step_id: string;
  next_state: RunState;
}

// ---------------------------------------------------------------------------
// Result / AnalysisOutput
// ---------------------------------------------------------------------------

export type RecommendationCategory = string;
export type Priority = "low" | "med" | "high";
export type Severity = "low" | "med" | "high";

export interface Recommendation {
  text: string;
  category: RecommendationCategory;
  priority: Priority;
}

export interface RiskFlag {
  flag: string;
  severity: Severity;
  evidence: string;
}

export interface AnalysisOutput {
  pseudonym: string;
  sections: Record<string, string>;
  citations_used: string[];
  recommendations: Recommendation[];
  risk_flags: RiskFlag[];
  raw_markdown: string;
  word_count: number;
}

export interface RunResultEnvelope {
  run_id: string;
  status: "completed" | "rejected" | "failed";
  final: AnalysisOutput;
  finished_at?: string | null;
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatRequestBody {
  session_id: string;
  query: string;
  athlete_id?: number | null;
}

export interface ChatResponse {
  answer: string;
  citations_used: string[];
  tools_called: string[];
}

/** Mensaje almacenado localmente en el ChatConsole. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Tools invocados por el LLM, sólo para mensajes assistant. */
  toolsCalled?: string[];
  /** chunk_ids citados, sólo para mensajes assistant. */
  citations?: string[];
  /** Timestamp local ISO. */
  ts: string;
}
