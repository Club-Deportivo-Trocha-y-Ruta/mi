/**
 * useMarkNewsletterRead — marca una bitácora como leída por el padre
 * (feature 038, `POST /{newsletterId}/read`, idempotente en el backend).
 *
 * data-model.md §6: dispara una sola vez por `newsletterId` por sesión de
 * navegador, vía `sessionStorage["bitacora-read:<id>"]` — evita golpear el
 * endpoint en cada render/remount de la página del padre.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { markNewsletterRead } from "@/api/parentNewsletters";
import { useAuthStore } from "@/store/auth.store";

function sessionKey(newsletterId: number): string {
  return `bitacora-read:${newsletterId}`;
}

/** Expuesto para que la UI decida si vale la pena disparar el mutate(). */
export function wasNewsletterMarkedReadThisSession(newsletterId: number): boolean {
  try {
    return sessionStorage.getItem(sessionKey(newsletterId)) === "1";
  } catch {
    return false;
  }
}

export function useMarkNewsletterRead(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useMutation({
    mutationFn: async () => {
      if (wasNewsletterMarkedReadThisSession(newsletterId)) {
        return;
      }
      await markNewsletterRead(athleteId, newsletterId);
      try {
        sessionStorage.setItem(sessionKey(newsletterId), "1");
      } catch {
        // sessionStorage puede no estar disponible (modo privado); no es
        // crítico, el backend ya es idempotente si se reintenta.
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["parent-newsletter", userId, athleteId, newsletterId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["parent-newsletters", userId, athleteId],
      });
      void queryClient.invalidateQueries({ queryKey: ["my-athletes", userId] });
    },
  });
}
