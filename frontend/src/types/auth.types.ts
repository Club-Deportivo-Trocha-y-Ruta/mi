import type { UserRole } from "@/types/enums";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

export interface PasswordResetMessage {
  message: string;
}

export interface PasswordResetValidate {
  valid: boolean;
}

export interface MeResponse {
  id: number;
  email: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  can_login: boolean;
  club_ids: number[];
  created_at: string;
}
