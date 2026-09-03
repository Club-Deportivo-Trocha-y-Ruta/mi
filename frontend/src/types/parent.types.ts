import type { FamilyRelationship } from "@/types/enums";
import type { MaturationStatus } from "@/types/enums";
import type { Sex } from "@/types/enums";

// --- Parent-Athlete relationship ---

export interface ParentAthleteCreate {
  parent_id: number;
  athlete_id: number;
  relationship: FamilyRelationship;
}

export interface ParentAthleteOut {
  id: number;
  parent_id: number;
  athlete_id: number;
  relationship: FamilyRelationship;
  parent_name: string;
  parent_email: string | null;
  parent_phone: string | null;
  athlete_name: string;
}

export interface ParentAthleteListOut {
  items: ParentAthleteOut[];
  total: number;
}

// --- Portal parent (my-athletes) ---

export interface MyAthleteOut {
  athlete_id: number;
  athlete_first_name: string;
  athlete_last_name: string;
  birth_date: string;
  sex: Sex;
  age_decimal: number | null;
  category: string | null;
  relationship: FamilyRelationship;
  latest_anthropometry_date: string | null;
  maturation_status: MaturationStatus | null;
  standing_height_cm: string | null; // Decimal in Python → string in JSON
  weight_kg: string | null; // Decimal in Python → string in JSON
  measurement_status: "ok" | "due_soon" | "overdue" | "never";
  // Bitácoras (feature 038) enviadas y aún no leídas por este padre.
  // Opcional en el tipo: `?? 0` defensivo en el consumidor (ChildCard) por
  // si el backend de una versión previa a la Wave 2 (T202) no lo incluye.
  unread_newsletters?: number;
}

// --- Invitations ---

export interface ParentInviteCreate {
  athlete_id: number;
  email: string;
  /**
   * Si el coach pre-creó al padre antes de invitar, su user.id va aquí para
   * que el backend ate la invitación a ese registro y el onboarding actualice
   * en lugar de duplicar.
   */
  parent_user_id?: number | null;
  /**
   * Tipo de parentesco que el coach asoció al crear el vínculo. Si difiere
   * del actual en parent_athlete, el backend lo actualiza al generar el invite.
   */
  relationship_type?: FamilyRelationship | null;
}

export interface ParentInviteOut {
  id: number;
  athlete_id: number;
  email: string;
  expires_at: string;
  used: boolean;
  created_at: string;
  /**
   * Padre al que pertenece la invitación. `GET /invites` filtra solo por
   * athlete_id (un atleta puede tener varios padres/acudientes vinculados),
   * así que un componente que representa a UN padre debe filtrar por este
   * campo — de lo contrario muestra el estado de otro padre.
   */
  parent_user_id?: number | null;
}

export interface ParentInviteCreatedOut extends ParentInviteOut {
  token: string; // exposed once at creation
}

export interface ParentInviteTokenValidation {
  athlete_id: number;
  athlete_name: string;
  email: string;
  expires_at: string;
  valid: boolean;
  /** Nombre del club al que pertenece el atleta. Presente en el wizard de onboarding. */
  club_name?: string;
  /** Rol del usuario invitado (ej: "parent"). Presente en el wizard de onboarding. */
  role?: string;
  /** ID del usuario padre pre-creado por el coach (None si flujo legacy). */
  parent_user_id?: number | null;
  /** Datos pre-cargados por el coach para pre-llenar el wizard. */
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  relationship_type?: FamilyRelationship | null;
}

/**
 * Shape base para registro de padre via API directa.
 * El wizard de onboarding usa ParentOnboardingPayload en
 * hooks/onboarding/index.ts que extiende este shape con
 * relationship_type y consent.
 */
export interface ParentRegisterRequest {
  token: string;
  first_name: string;
  last_name: string;
  password: string;
  phone?: string | null;
}

export interface ParentRegisterOut {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  message: string;
}

// --- Parent user (coach view) ---

export interface ParentUserOut {
  id: number;
  email: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  is_active: boolean;
  linked_athletes_count?: number; // enriched client-side
}

export interface ParentUserListOut {
  items: ParentUserOut[];
  total: number;
}
