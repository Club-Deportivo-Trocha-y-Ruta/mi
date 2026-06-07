import { apiClient } from "@/api/client";
import type {
  LoginRequest,
  MeResponse,
  PasswordResetConfirm,
  PasswordResetMessage,
  PasswordResetRequest,
  PasswordResetValidate,
  RefreshRequest,
  TokenResponse,
} from "@/types/auth.types";
import type {
  ParentInviteTokenValidation,
  ParentRegisterOut,
  ParentRegisterRequest,
} from "@/types/parent.types";

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/api/auth/login", payload);
  return response.data;
}

export async function refreshToken(
  payload: RefreshRequest,
): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/api/auth/refresh", payload);
  return response.data;
}

export async function getMe(): Promise<MeResponse> {
  const response = await apiClient.get<MeResponse>("/api/auth/me");
  return response.data;
}

export async function validateInviteToken(
  token: string,
): Promise<ParentInviteTokenValidation> {
  const response = await apiClient.get<ParentInviteTokenValidation>(
    `/api/auth/invite/${token}`,
  );
  return response.data;
}

export async function registerParent(
  payload: ParentRegisterRequest,
): Promise<ParentRegisterOut> {
  const response = await apiClient.post<ParentRegisterOut>(
    "/api/auth/parent-register",
    payload,
  );
  return response.data;
}

export async function requestPasswordReset(
  payload: PasswordResetRequest,
): Promise<PasswordResetMessage> {
  const response = await apiClient.post<PasswordResetMessage>(
    "/api/auth/password-reset/request",
    payload,
  );
  return response.data;
}

export async function validateResetToken(
  token: string,
): Promise<PasswordResetValidate> {
  const response = await apiClient.get<PasswordResetValidate>(
    "/api/auth/password-reset/validate",
    { params: { token } },
  );
  return response.data;
}

export async function confirmPasswordReset(
  payload: PasswordResetConfirm,
): Promise<PasswordResetMessage> {
  const response = await apiClient.post<PasswordResetMessage>(
    "/api/auth/password-reset/confirm",
    payload,
  );
  return response.data;
}
