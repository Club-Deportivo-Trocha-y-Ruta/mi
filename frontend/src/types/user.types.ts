import type { UserRole } from "@/types/enums";

export interface UserOut {
  id: number;
  email: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  can_login: boolean;
  created_at: string;
  /**
   * Nombre de quien creó la cuenta (feature 041 — contracts/staff-admin.md
   * §1.6). `null` cuando `users.created_by` es `NULL` (ej. el admin
   * sembrado). Campo opcional/aditivo — los consumidores existentes
   * (`api/parents.ts`) no lo requieren.
   */
  created_by_display_name?: string | null;
}

export interface UserListOut {
  items: UserOut[];
  total: number;
}

/** Grupos de personal creables/gestionables desde `/admin/usuarios`. */
export type StaffRole = UserRole.coach | UserRole.admin;

export interface StaffCreatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  role: StaffRole;
  club_id: number;
}

export interface SetUserActivePayload {
  is_active: boolean;
  reason_code?: string | null;
}

export interface ClubOut {
  id: number;
  name: string;
  code: string;
  location: string | null;
  is_active: boolean;
  created_at: string;
}
