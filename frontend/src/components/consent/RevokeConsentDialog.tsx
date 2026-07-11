/**
 * RevokeConsentDialog — Diálogo de confirmación para revocar consentimiento parental.
 *
 * Diseñado como AlertDialog bloqueante con doble confirmación visual (texto rojo
 * + botón destructivo) para reducir revocaciones accidentales. La revocación
 * impide al club gestionar al atleta, por lo que el tono debe ser claro pero
 * no alarmista — se informa la consecuencia sin presionar al padre.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { useWithdrawConsent } from "@/hooks/consent";
import type { AthleteConsentStatus } from "@/types/consent";

// ---------------------------------------------------------------------------
// Estilos del design system (Cal.com)
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  background: "rgba(19, 19, 22, 0.65)",
  backdropFilter: "blur(2px)",
};

const btnPrimaryStyle: React.CSSProperties = {
  boxShadow:
    "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.16) 0px 1px 1.9px 0px inset, rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
};

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const revokeSchema = z.object({
  reason: z.string().optional(),
});

type RevokeFormData = z.infer<typeof revokeSchema>;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RevokeConsentDialogProps {
  athlete: AthleteConsentStatus;
  onClose: () => void;
  /** Callback adicional tras revocar exitosamente (ej: mostrar toast). */
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function RevokeConsentDialog({
  athlete,
  onClose,
  onSuccess,
}: RevokeConsentDialogProps) {
  const [serverError, setServerError] = useState<string | null>(null);

  const { mutate: withdraw, isPending } = useWithdrawConsent();

  const {
    register,
    handleSubmit,
  } = useForm<RevokeFormData>({
    resolver: zodResolver(revokeSchema),
    defaultValues: { reason: "" },
  });

  const onSubmit = handleSubmit((data) => {
    setServerError(null);

    withdraw(
      {
        athlete_id: athlete.athlete_id,
        reason: data.reason?.trim() || undefined,
      },
      {
        onSuccess: () => {
          onSuccess?.();
          onClose();
        },
        onError: () => {
          setServerError(
            "No fue posible revocar el consentimiento. Intenta de nuevo.",
          );
        },
      },
    );
  });

  return (
    /* Overlay bloqueante — la revocación es una acción grave que requiere
       confirmación explícita, no puede descartarse haciendo clic afuera. */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={overlayStyle}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="revoke-dialog-title"
      aria-describedby="revoke-dialog-desc"
    >
      <div className={cn("w-full max-w-md rounded-2xl bg-white", "shadow-card")}>
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-[rgba(34,42,53,0.08)]">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-50">
              <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
            </div>
            <div>
              <h2
                id="revoke-dialog-title"
                className="font-display text-base text-charcoal"
              >
                Revocar consentimiento
              </h2>
              <p className="mt-0.5 text-sm text-mid-gray">
                {athlete.athlete_name}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="rounded-lg p-1.5 text-mid-gray transition-colors hover:bg-light-gray disabled:opacity-50"
            aria-label="Cancelar revocación"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Cuerpo */}
        <form onSubmit={onSubmit}>
          <div className="px-6 py-5 space-y-4">
            {/* Advertencia de consecuencia */}
            <div
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-3"
              role="note"
            >
              <p className="text-sm font-medium text-red-700">
                Estás a punto de revocar tu consentimiento para{" "}
                <strong>{athlete.athlete_name}</strong>.
              </p>
              <p className="mt-1 text-sm text-red-600">
                Tras revocar, el club no podrá registrar nuevas mediciones ni
                gestionar los datos del atleta en la plataforma. Puedes renovar
                el consentimiento en cualquier momento.
              </p>
            </div>

            {/* Motivo opcional */}
            <div className="space-y-1.5">
              <label
                htmlFor="revoke-reason"
                className="block text-sm font-medium text-charcoal"
              >
                Motivo{" "}
                <span className="font-normal text-mid-gray">(opcional)</span>
              </label>
              <textarea
                id="revoke-reason"
                rows={3}
                placeholder="¿Hay algo que podamos mejorar?"
                className={cn(
                  "w-full resize-none rounded-lg px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray/60",
                  "border-0 bg-light-gray outline-none",
                  "focus:ring-2 focus:ring-charcoal/20",
                  "shadow-ring",
                )}
                {...register("reason")}
                aria-describedby="revoke-reason-hint"
              />
              <p id="revoke-reason-hint" className="text-xs text-mid-gray">
                Tu comentario ayuda al club a mejorar la experiencia.
              </p>
            </div>

            {/* Error del servidor */}
            {serverError && (
              <p className="text-sm text-red-600" role="alert" aria-live="assertive">
                {serverError}
              </p>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 px-6 pb-6">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className={cn(
                "rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50",
                "shadow-ring",
              )}
            >
              Cancelar
            </button>

            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={btnPrimaryStyle}
            >
              {isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isPending ? "Revocando…" : "Revocar consentimiento"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
