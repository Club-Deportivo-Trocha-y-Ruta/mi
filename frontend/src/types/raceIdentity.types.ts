/**
 * Tipos del módulo race-identity (feature 044, US4 — revisión de identidad).
 *
 * Mirror de `backend/app/schemas/race_identity.py` (schemas Pydantic v2) y
 * `backend/app/services/race/identity_review.py` (constantes `SIGNAL_*`,
 * `DEFAULT_PAGE_SIZE`). Contrato:
 * specs/044-race-history-backfill/contracts/identity-review-api.md
 *
 * Privacidad: `IdentityRecordRead` es el ÚNICO schema del sistema que
 * serializa `city`. `athlete_linked` es un booleano — nunca el nombre real
 * del deportista enlazado.
 */

// ---------------------------------------------------------------------------
// GET /api/race-identity/candidates
// ---------------------------------------------------------------------------

export type IdentityCandidateKind = "same_person_suspect" | "homonym_suspect";

export type IdentityCandidateState =
  | "pending"
  | "same_person"
  | "different_people";

/**
 * Código de señal — cada uno se traduce a una frase en español en el
 * componente (nunca se muestra el código crudo). Tipado como `string`, no
 * como union cerrada: el backend puede sumar señales nuevas sin que el
 * frontend deje de compilar; `signalLabel()` en `IdentityReviewPage.tsx`
 * usa un lookup con reserva genérica para cualquier código no reconocido.
 *
 * Códigos conocidos a la fecha (`identity_review.py::SIGNAL_*`):
 * `same_valida_two_categories`, `same_valida_same_category`, `sex_conflict`,
 * `age_path_backwards`, `club_and_city_differ`,
 * `multiple_existing_competitors`, `age_incompatible_categories` (lado
 * homónimo) · `extra_or_missing_surname`, `inverted_surname_order`,
 * `spelling_variant` (lado misma persona).
 */
export type IdentitySignalCode = string;

export interface IdentityRecordRead {
  name_printed: string;
  /** Nunca `null` — el backend rellena con `""` cuando no hay dato. */
  club: string;
  /** Nunca `null` — el backend rellena con `""` cuando no hay dato. */
  city: string;
  seasons: number[];
  category_labels: string[];
  competitor_id?: number | null;
  athlete_linked: boolean;
}

export interface IdentityCandidateRead {
  id: number;
  kind: IdentityCandidateKind;
  /** Entero 0-100 (rapidfuzz `token_set_ratio`) — NO un ratio 0-1. */
  score: number;
  signals: IdentitySignalCode[];
  left: IdentityRecordRead;
  right: IdentityRecordRead;
  state: IdentityCandidateState;
  linked_athlete_involved: boolean;
  decided_at?: string | null;
  reversed_at?: string | null;
}

export interface IdentityCandidatesParams {
  state?: IdentityCandidateState;
  kind?: IdentityCandidateKind;
  page?: number;
}

export interface IdentityCandidatesResponse {
  items: IdentityCandidateRead[];
  total: number;
  page: number;
  /** Fijo en 20 (`DEFAULT_PAGE_SIZE`) — el frontend no lo negocia. */
  page_size: number;
}

// ---------------------------------------------------------------------------
// GET /api/race-identity/summary
// ---------------------------------------------------------------------------

export interface IdentitySummaryResponse {
  pending: number;
  same_person: number;
  different_people: number;
}

// ---------------------------------------------------------------------------
// POST /api/race-identity/candidates/{id}/decide
// ---------------------------------------------------------------------------

export type IdentityDecisionAnswer = "same_person" | "different_people";

export interface IdentityDecideRequest {
  answer: IdentityDecisionAnswer;
}

export interface IdentityDecideResponse {
  id: number;
  state: IdentityCandidateState;
  /** `true` si ambos lados ya eran competidores confirmados y se fusionaron. */
  merged: boolean;
  results_moved: number;
}

// ---------------------------------------------------------------------------
// POST /api/race-identity/candidates/{id}/reverse
// ---------------------------------------------------------------------------

export interface IdentityReverseResponse {
  id: number;
  state: IdentityCandidateState;
  /** `true` si se separó un competidor ya confirmado. */
  split: boolean;
  results_moved: number;
  links_cleared: number;
}

// ---------------------------------------------------------------------------
// POST /api/race-identity/rebuild
// ---------------------------------------------------------------------------

export interface IdentityRebuildResponse {
  created: number;
  unchanged: number;
  pending: number;
  /** Ids de imports en staging cuyo archivo no se pudo re-leer en este rebuild. */
  imports_unreadable: number[];
}
