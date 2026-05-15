/**
 * Tipos compartidos para el sistema de consentimiento parental.
 *
 * Alineados con el contrato API de /api/me/consent y /api/auth/active-policy.
 * Política v1.1 (2026-05-06): dos checkboxes obligatorios (data_collection + anthropometry).
 */

// ---------------------------------------------------------------------------
// Grants de consentimiento
// ---------------------------------------------------------------------------

/** Autoridades granulares que el padre otorga (o no) a cada tratamiento. */
export interface ConsentGrants {
  data_collection: boolean;
  anthropometry: boolean;
  training_tracking: boolean;
  third_party_sharing: boolean;
}

// ---------------------------------------------------------------------------
// Política de privacidad
// ---------------------------------------------------------------------------

/** Resumen de política — incluido en ConsentStatus sin el HTML completo. */
export interface PrivacyPolicySummary {
  id: number;
  version: string;
  effective_date: string;
  title: string;
  changelog: string | null;
}

/** Política completa — devuelta por GET /api/auth/active-policy. */
export interface PrivacyPolicyFull extends PrivacyPolicySummary {
  content_html: string;
  content_hash: string;
  deprecated_at: string | null;
}

// ---------------------------------------------------------------------------
// Estado de consentimiento por atleta
// ---------------------------------------------------------------------------

/** Registro de consentimiento activo para un atleta. Null si nunca dio consentimiento. */
export interface CurrentConsent {
  id: number;
  policy_version: string;
  consented_at: string;
  /** false cuando la política vigente es más reciente que la versión aceptada. */
  is_current_policy: boolean;
  withdrawn_at: string | null;
  grants: ConsentGrants;
}

/** Estado de consentimiento de un atleta específico del padre. */
export interface AthleteConsentStatus {
  athlete_id: number;
  athlete_name: string;
  current_consent: CurrentConsent | null;
}

/** Respuesta completa de GET /api/me/consent. */
export interface ConsentStatus {
  active_policy: PrivacyPolicySummary;
  consents_per_athlete: AthleteConsentStatus[];
}

// ---------------------------------------------------------------------------
// Eventos de consentimiento (respuesta de mutaciones)
// ---------------------------------------------------------------------------

/** Registro de evento creado por renovar o revocar consentimiento. */
export interface ConsentEvent {
  id: number;
  athlete_id: number;
  policy_version: string;
  consented_at: string;
  withdrawn_at: string | null;
  grants: ConsentGrants;
}

// ---------------------------------------------------------------------------
// Payloads de mutaciones
// ---------------------------------------------------------------------------

/** Body de POST /api/me/consent/renew. */
export interface RenewConsentPayload {
  athlete_id: number;
  policy_version: string;
  accept_data_collection: boolean;
  accept_anthropometry: boolean;
  /** Consentimiento opcional para procesamiento con IA de terceros (Anthropic/Google). */
  accept_third_party_sharing: boolean;
}

/** Body de POST /api/me/consent/withdraw. */
export interface WithdrawConsentPayload {
  athlete_id: number;
  reason?: string;
}
