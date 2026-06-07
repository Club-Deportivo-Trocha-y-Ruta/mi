/**
 * API client functions for the Profile & Account Settings module.
 * Base path: /api/profile
 * All authenticated endpoints rely on the shared apiClient JWT interceptor.
 */
import { apiClient } from "@/api/client";
import type {
  EmailChangeConfirm,
  EmailChangeRequestBody,
  PasswordChangeRequest,
  ProfileBasicUpdate,
  ProfileMessage,
  ProfileOut,
} from "@/types/profile.types";

/** GET /api/profile/me — fetch own profile (auth required). */
export async function getProfile(): Promise<ProfileOut> {
  const response = await apiClient.get<ProfileOut>("/api/profile/me");
  return response.data;
}

/** PATCH /api/profile/basic — update own basic info (auth required). */
export async function updateBasicInfo(
  payload: ProfileBasicUpdate,
): Promise<ProfileOut> {
  const response = await apiClient.patch<ProfileOut>(
    "/api/profile/basic",
    payload,
  );
  return response.data;
}

/** POST /api/profile/change-password — re-auth then change password (auth required).
 *  400 if current_password wrong; 422 if new_password fails policy or equals current.
 */
export async function changePassword(
  payload: PasswordChangeRequest,
): Promise<ProfileMessage> {
  const response = await apiClient.post<ProfileMessage>(
    "/api/profile/change-password",
    payload,
  );
  return response.data;
}

/** POST /api/profile/change-email/request — initiate email change (auth required).
 *  Always returns 200 (anti-enumeration). 400 if current_password wrong.
 */
export async function requestEmailChange(
  payload: EmailChangeRequestBody,
): Promise<ProfileMessage> {
  const response = await apiClient.post<ProfileMessage>(
    "/api/profile/change-email/request",
    payload,
  );
  return response.data;
}

/** POST /api/profile/change-email/confirm — PUBLIC endpoint (no auth required).
 *  200 on success; 404 unknown token; 410 used/expired; 409 email taken.
 */
export async function confirmEmailChange(
  payload: EmailChangeConfirm,
): Promise<ProfileMessage> {
  const response = await apiClient.post<ProfileMessage>(
    "/api/profile/change-email/confirm",
    payload,
  );
  return response.data;
}
