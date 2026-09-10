/**
 * API client del personal del club (feature 041 — gobernanza multi-coach,
 * US3). Contrato: specs/041-multi-coach-governance/contracts/staff-admin.md
 * §1, §3, §4, §7.
 *
 * Nota: `getParentUsers`/`createParentUser` (`api/parents.ts`) ya cubren
 * `role=parent` sobre los mismos endpoints — este módulo es la variante
 * "personal" (`coach`/`admin`) que consume `/admin/usuarios`.
 */
import { apiClient } from "@/api/client";
import type { UserRole } from "@/types/enums";
import type {
  SetUserActivePayload,
  StaffCreatePayload,
  UserListOut,
  UserOut,
} from "@/types/user.types";

export interface ListUsersParams {
  /** Repetible — axios serializa un arreglo como `role=coach&role=admin`. */
  role?: UserRole[];
  club_id?: number;
  is_active?: boolean;
}

/** GET /api/users */
export async function listUsers(
  params: ListUsersParams = {},
  options?: { signal?: AbortSignal },
): Promise<UserListOut> {
  const response = await apiClient.get<UserListOut>("/api/users", {
    params,
    signal: options?.signal,
  });
  return response.data;
}

/**
 * POST /api/users — alta de personal (`role` ∈ {coach, admin}).
 * `password` nunca viaja: la cuenta se crea sin credencial y la persona la
 * define desde el correo de restablecimiento (FR-023, §1.4).
 */
export async function createStaffUser(
  payload: StaffCreatePayload,
): Promise<UserOut> {
  const response = await apiClient.post<UserOut>("/api/users", {
    first_name: payload.first_name,
    last_name: payload.last_name,
    email: payload.email,
    phone: payload.phone ?? null,
    role: payload.role,
    club_id: payload.club_id,
  });
  return response.data;
}

/** PATCH /api/users/{id} — activar/desactivar una cuenta de personal. */
export async function setUserActive(
  id: number,
  body: SetUserActivePayload,
): Promise<UserOut> {
  const response = await apiClient.patch<UserOut>(`/api/users/${id}`, body);
  return response.data;
}
