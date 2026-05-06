/**
 * Hooks de TanStack Query para el wizard de onboarding de padres.
 *
 * useValidateToken — valida un token de invitación antes de mostrar el wizard.
 * useCompleteOnboarding — registra al padre al completar el wizard.
 *
 * Notas de coordinación con api/parents.ts:
 *   - ParentInviteTokenValidation no incluye `role` ni `club_name` todavía.
 *     Se define InviteTokenData localmente con los campos adicionales hasta
 *     que el API client sea actualizado.
 *   - ParentRegisterRequest no incluye `relationship_type` ni `consent`.
 *     Se define ParentOnboardingPayload localmente con el shape correcto.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import axios from "axios";

import { apiClient } from "@/api/client";
import type { FamilyRelationship, UserRole } from "@/types/enums";
import type { ConsentData } from "@/schemas/onboarding.schema";

// ---------------------------------------------------------------------------
// Tipos locales
// ---------------------------------------------------------------------------

/**
 * Respuesta del backend para GET /api/auth/invite/{token}.
 * Extiende ParentInviteTokenValidation con `role` y `club_name` que el
 * endpoint de onboarding devuelve pero el tipo compartido aún no tiene.
 */
export interface InviteTokenData {
  valid: boolean;
  email: string;
  athlete_name: string;
  club_name: string;
  role: UserRole | string;
  expires_at: string;
  /** Pre-fill cuando el coach pre-creó al padre antes de invitar. */
  parent_user_id?: number | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  relationship_type?: FamilyRelationship | null;
}

/**
 * Payload para POST /api/auth/parent-register.
 * Incluye `relationship_type` y `consent` que ParentRegisterRequest omite.
 */
export interface ParentOnboardingPayload {
  token: string;
  first_name: string;
  last_name: string;
  password: string;
  phone?: string | null;
  relationship_type: FamilyRelationship;
  consent: ConsentData;
}

/**
 * Respuesta del backend al completar el registro.
 */
export interface ParentOnboardingOut {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Errores estructurados
// ---------------------------------------------------------------------------

/**
 * Códigos de error semánticos para useCompleteOnboarding.
 * Permiten al componente reaccionar sin parsear mensajes de texto.
 */
export type OnboardingErrorCode =
  | "TOKEN_EXPIRED"   // 410 — token vencido o ya usado
  | "EMAIL_CONFLICT"  // 409 — email ya registrado
  | "SERVER_ERROR"    // 500+ — error inesperado del servidor
  | "UNKNOWN";        // otros errores de red / timeout

export interface OnboardingError {
  code: OnboardingErrorCode;
  message: string;
}

function mapOnboardingError(error: unknown): OnboardingError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;

    if (status === 410) {
      return {
        code: "TOKEN_EXPIRED",
        message:
          "Este enlace de invitación ha vencido o ya fue usado. Solicita un nuevo enlace al entrenador.",
      };
    }

    if (status === 409) {
      return {
        code: "EMAIL_CONFLICT",
        message:
          "Ya existe una cuenta con este correo electrónico. Intenta iniciar sesión.",
      };
    }

    if (status !== undefined && status >= 500) {
      return {
        code: "SERVER_ERROR",
        message:
          "Ocurrió un error en el servidor. Por favor intenta de nuevo en unos minutos.",
      };
    }
  }

  return {
    code: "UNKNOWN",
    message: "Ocurrió un error inesperado. Verifica tu conexión e intenta de nuevo.",
  };
}

// ---------------------------------------------------------------------------
// Funciones API (inline — serán migradas a api/parents.ts cuando se actualice)
// ---------------------------------------------------------------------------

async function validateInviteToken(token: string): Promise<InviteTokenData> {
  const response = await apiClient.get<InviteTokenData>(
    `/api/auth/invite/${token}`,
  );
  return response.data;
}

async function registerParentOnboarding(
  payload: ParentOnboardingPayload,
): Promise<ParentOnboardingOut> {
  try {
    const response = await apiClient.post<ParentOnboardingOut>(
      "/api/auth/parent-register",
      payload,
    );
    return response.data;
  } catch (error) {
    // Lanzamos OnboardingError tipado para que TanStack Query lo almacene
    // directamente en `mutation.error` con el tipo correcto.
    throw mapOnboardingError(error);
  }
}

// ---------------------------------------------------------------------------
// useValidateToken
// ---------------------------------------------------------------------------

/**
 * Valida un token de invitación contra el backend.
 *
 * - Solo ejecuta la query si `token` no es nulo ni vacío.
 * - retry: false — un token inválido no mejora con reintentos.
 * - staleTime: 60 s — el token no cambia mientras el usuario rellena el form.
 */
export function useValidateToken(token: string | null) {
  return useQuery<InviteTokenData, OnboardingError>({
    queryKey: ["invite-token", token],
    queryFn: () => validateInviteToken(token!),
    enabled: !!token,
    // Reintentar solo en errores de red/500 (pool DB frío en Render).
    // No reintentar en 404/410 — token genuinamente inválido no mejora.
    retry: (failureCount, error) => {
      if (failureCount >= 2) return false;
      const status = (error as { response?: { status?: number } })?.response?.status;
      return status === undefined || status >= 500;
    },
    retryDelay: 1500,
    staleTime: 60_000,
    select: (data) => data,
  });
}

// ---------------------------------------------------------------------------
// useCompleteOnboarding
// ---------------------------------------------------------------------------

/**
 * Envía el formulario de onboarding completo al backend.
 *
 * El error tipado `OnboardingError` permite a los componentes discriminar
 * por `code` sin parsear mensajes de texto.
 */
export function useCompleteOnboarding() {
  return useMutation<
    ParentOnboardingOut,
    OnboardingError,
    ParentOnboardingPayload
  >({
    mutationFn: registerParentOnboarding,
    // El error tipado llega desde mutationFn — el componente discrimina
    // por `mutation.error.code` para mostrar el mensaje correcto.
  });
}

// Re-exportar para que los consumidores importen desde un solo lugar
export { mapOnboardingError };
