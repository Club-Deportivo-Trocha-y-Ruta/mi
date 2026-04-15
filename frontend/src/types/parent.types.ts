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
}

// --- Invitations ---

export interface ParentInviteCreate {
  athlete_id: number;
  email: string;
}

export interface ParentInviteOut {
  id: number;
  athlete_id: number;
  email: string;
  expires_at: string;
  used: boolean;
  created_at: string;
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
}

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
