/**
 * Hooks de TanStack Query para el sistema de consentimiento parental.
 *
 * useActivePolicy    — política vigente pública (sin auth, usada en modal para mostrar changelog)
 * useMyConsentStatus — estado de consentimiento de todos los atletas del padre autenticado
 * useRenewConsent    — mutation para renovar consentimiento ante nueva versión de política
 * useWithdrawConsent — mutation para revocar consentimiento de un atleta específico
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type {
  ConsentEvent,
  ConsentStatus,
  PrivacyPolicyFull,
  RenewConsentPayload,
  WithdrawConsentPayload,
} from "@/types/consent";

// ---------------------------------------------------------------------------
// useActivePolicy
// ---------------------------------------------------------------------------

/**
 * Obtiene la política de privacidad vigente (endpoint público, sin auth).
 *
 * staleTime largo (1h) porque la política no cambia en el transcurso de una
 * sesión normal. Se invalida manualmente si el admin bumpeara la versión en
 * producción (no aplica en el flujo de usuario normal).
 */
export function useActivePolicy() {
  return useQuery<PrivacyPolicyFull>({
    queryKey: ["active-policy"],
    queryFn: () =>
      apiClient.get<PrivacyPolicyFull>("/api/auth/active-policy").then((r) => r.data),
    staleTime: 60 * 60 * 1000, // 1 hora
  });
}

// ---------------------------------------------------------------------------
// useMyConsentStatus
// ---------------------------------------------------------------------------

/**
 * Estado de consentimiento de todos los atletas del padre autenticado.
 *
 * `enabled` permite deshabilitar la query cuando el usuario no es "parent"
 * o cuando el componente aún no está montado.
 */
export function useMyConsentStatus(enabled = true) {
  return useQuery<ConsentStatus>({
    queryKey: ["my-consent"],
    queryFn: () =>
      apiClient.get<ConsentStatus>("/api/me/consent").then((r) => r.data),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutos
  });
}

// ---------------------------------------------------------------------------
// useRenewConsent
// ---------------------------------------------------------------------------

/**
 * Envía la renovación de consentimiento del padre para un atleta.
 *
 * Invalida "my-consent" en onSuccess para que el modal detecte que ya
 * no hay atletas pendientes y se cierre automáticamente.
 */
export function useRenewConsent() {
  const queryClient = useQueryClient();

  return useMutation<ConsentEvent, Error, RenewConsentPayload>({
    mutationFn: (body) =>
      apiClient.post<ConsentEvent>("/api/me/consent/renew", body).then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["my-consent"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useWithdrawConsent
// ---------------------------------------------------------------------------

/**
 * Revoca el consentimiento del padre para un atleta.
 *
 * Invalida "my-consent" para refrescar el estado en el panel.
 */
export function useWithdrawConsent() {
  const queryClient = useQueryClient();

  return useMutation<ConsentEvent, Error, WithdrawConsentPayload>({
    mutationFn: (body) =>
      apiClient.post<ConsentEvent>("/api/me/consent/withdraw", body).then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["my-consent"] });
    },
  });
}
