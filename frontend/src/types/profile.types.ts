/**
 * Types for the User Profile & Account Settings module (spec 004-user-profile).
 *
 * All shapes mirror the backend contract at /api/profile/*.
 * Privacy: no password, token_hash, or raw token ever appears here.
 */
import type { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

/** GET /api/profile/me → 200 | PATCH /api/profile/basic → 200 */
export interface ProfileOut {
  id: number;
  email: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  role: UserRole;
}

/** POST /api/profile/change-password → 200
 *  POST /api/profile/change-email/request → 200
 *  POST /api/profile/change-email/confirm → 200 | 404 | 410 | 409
 */
export interface ProfileMessage {
  message: string;
}

// ---------------------------------------------------------------------------
// Request shapes
// ---------------------------------------------------------------------------

/** PATCH /api/profile/basic — at least one field must be present */
export interface ProfileBasicUpdate {
  first_name?: string;
  last_name?: string;
  phone?: string;
}

/** POST /api/profile/change-password */
export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

/** POST /api/profile/change-email/request */
export interface EmailChangeRequestBody {
  current_password: string;
  new_email: string;
}

/** POST /api/profile/change-email/confirm */
export interface EmailChangeConfirm {
  token: string;
}
