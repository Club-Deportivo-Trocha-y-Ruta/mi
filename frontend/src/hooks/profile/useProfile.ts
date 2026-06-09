/**
 * TanStack Query hooks for the Profile & Account Settings module.
 *
 * Privacy / sync contract:
 * - On profile load (useProfile) and on successful basic-info update
 *   (useUpdateBasicInfo), the auth store user is patched in-place so that
 *   the header name display stays consistent without a full re-login.
 * - The query key ["profile", "me"] is always scoped to the current user
 *   via the accessToken presence check in `enabled`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";

import {
  changePassword,
  confirmEmailChange,
  getProfile,
  requestEmailChange,
  updateBasicInfo,
} from "@/api/profile";
import { useAuthStore } from "@/store/auth.store";
import type {
  EmailChangeConfirm,
  EmailChangeRequestBody,
  PasswordChangeRequest,
  ProfileBasicUpdate,
  ProfileMessage,
  ProfileOut,
} from "@/types/profile.types";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const profileKeys = {
  all: ["profile"] as const,
  me: () => [...profileKeys.all, "me"] as const,
};

// ---------------------------------------------------------------------------
// Helper: extract a human-readable error message from an API response.
// ---------------------------------------------------------------------------

export function extractProfileError(error: unknown): string {
  if (isAxiosError(error)) {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;
    if (status === 400) {
      // Current-password wrong — backend sends a localized message.
      return typeof detail === "string"
        ? detail
        : "La contraseña actual no es correcta.";
    }
    if (status === 410) {
      return "El enlace ha expirado o ya fue utilizado. Solicita el cambio nuevamente.";
    }
    if (status === 404) {
      return "Enlace no válido.";
    }
    if (status === 409) {
      return "No se pudo aplicar el cambio. Solicita el cambio nuevamente.";
    }
    if (status === 422) {
      // Validation error from backend; prefer detail if it's a string.
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string };
        if (typeof first.msg === "string") return first.msg;
      }
    }
  }
  return "No fue posible completar la operación. Intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Query — fetch own profile
// ---------------------------------------------------------------------------

/**
 * useProfile — fetches /api/profile/me and keeps the auth store in sync.
 * Enabled only when there is a valid access token (user is authenticated).
 */
export function useProfile() {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery<ProfileOut>({
    queryKey: profileKeys.me(),
    queryFn: async () => {
      const profile = await getProfile();
      // Sync: patch auth store user with fresh basic info so the header
      // name display reflects the latest saved values without a re-login.
      const { user } = useAuthStore.getState();
      if (user) {
        useAuthStore.setState({
          user: {
            ...user,
            first_name: profile.first_name,
            last_name: profile.last_name,
            phone: profile.phone,
            email: profile.email,
          },
        });
      }
      return profile;
    },
    enabled: !!accessToken,
    staleTime: 2 * 60 * 1000, // 2 min — profile changes are infrequent
  });
}

// ---------------------------------------------------------------------------
// Mutation — update basic info
// ---------------------------------------------------------------------------

/** useUpdateBasicInfo — PATCH /api/profile/basic. */
export function useUpdateBasicInfo() {
  const queryClient = useQueryClient();

  return useMutation<ProfileOut, unknown, ProfileBasicUpdate>({
    mutationFn: updateBasicInfo,
    onSuccess: (updated) => {
      // Update cache with fresh data from backend.
      queryClient.setQueryData<ProfileOut>(profileKeys.me(), updated);

      // Sync auth store so the header name reflects the new values immediately.
      const { user } = useAuthStore.getState();
      if (user) {
        useAuthStore.setState({
          user: {
            ...user,
            first_name: updated.first_name,
            last_name: updated.last_name,
            phone: updated.phone,
            email: updated.email,
          },
        });
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation — change password
// ---------------------------------------------------------------------------

/** useChangePassword — POST /api/profile/change-password. */
export function useChangePassword() {
  return useMutation<ProfileMessage, unknown, PasswordChangeRequest>({
    mutationFn: changePassword,
  });
}

// ---------------------------------------------------------------------------
// Mutation — request email change
// ---------------------------------------------------------------------------

/** useRequestEmailChange — POST /api/profile/change-email/request. */
export function useRequestEmailChange() {
  return useMutation<ProfileMessage, unknown, EmailChangeRequestBody>({
    mutationFn: requestEmailChange,
  });
}

// ---------------------------------------------------------------------------
// Mutation — confirm email change (PUBLIC, no auth required)
// ---------------------------------------------------------------------------

/** useConfirmEmailChange — POST /api/profile/change-email/confirm.
 *  On success, invalidates the profile query so fresh data is fetched
 *  if the user is still signed in (unlikely but safe).
 */
export function useConfirmEmailChange() {
  const queryClient = useQueryClient();

  return useMutation<ProfileMessage, unknown, EmailChangeConfirm>({
    mutationFn: confirmEmailChange,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: profileKeys.all });
    },
  });
}
