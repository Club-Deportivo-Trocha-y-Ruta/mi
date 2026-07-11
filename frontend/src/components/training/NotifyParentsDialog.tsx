import { useEffect, useState } from "react";
import { Loader2, Mail, MailX, X } from "lucide-react";

import type { AthleteEntry, ChangeEntry } from "@/lib/sessionDiff";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const btnPrimaryStyle: React.CSSProperties = {
  boxShadow:
    "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.16) 0px 1px 1.9px 0px inset, rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
};

const btnSecondaryStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

export type NotifyVariant = "create" | "update" | "cancel" | "attendance";

export interface NotifyParentsDialogProps {
  open: boolean;
  variant: NotifyVariant;
  /** Número de familias que recibirían el email (informativo). */
  parentCount?: number;
  /** Variante `update`: lista de cambios calculados. */
  changes?: ChangeEntry[];
  /** Variante `attendance`: atletas añadidos a la convocatoria. */
  addedAthletes?: AthleteEntry[];
  /** Variante `attendance`: atletas removidos (informativo, no se notifica). */
  removedAthletes?: AthleteEntry[];
  isPending?: boolean;
  errorMessage?: string | null;
  /** "Enviar notificación". Recibe `reason` opcional solo en variante `cancel`. */
  onSend: (reason?: string) => void;
  /** "No enviar" — guardar el cambio pero sin email. */
  onSkip: () => void;
  /** "Cancelar" — cerrar diálogo sin guardar. */
  onCancel: () => void;
}

function variantCopy(variant: NotifyVariant, parentCount: number): {
  title: string;
  subject: string;
  intro: string;
} {
  const families = parentCount === 1 ? "1 familia" : `${parentCount} familias`;
  switch (variant) {
    case "create":
      return {
        title: "¿Enviar invitación a los padres?",
        subject: "Nueva sesión de entrenamiento",
        intro:
          parentCount > 0
            ? `Se notificará a ${families} sobre la nueva sesión.`
            : "Se enviará un email a los padres de los atletas convocados.",
      };
    case "update":
      return {
        title: "¿Enviar aviso de los cambios?",
        subject: "Sesión actualizada",
        intro:
          parentCount > 0
            ? `Se notificará a ${families} sobre los cambios aplicados.`
            : "Los padres convocados recibirán un email con los cambios.",
      };
    case "cancel":
      return {
        title: "¿Avisar a los padres de la cancelación?",
        subject: "Sesión cancelada",
        intro:
          parentCount > 0
            ? `Se notificará a ${families} que la sesión fue cancelada.`
            : "Los padres convocados recibirán un email de cancelación.",
      };
    case "attendance":
      return {
        title: "¿Notificar a los nuevos convocados?",
        subject: "Cambio en la lista de atletas",
        intro:
          "Solo los padres de los atletas recién añadidos recibirán el email.",
      };
  }
}

export function NotifyParentsDialog({
  open,
  variant,
  parentCount = 0,
  changes = [],
  addedAthletes = [],
  removedAthletes = [],
  isPending = false,
  errorMessage,
  onSend,
  onSkip,
  onCancel,
}: NotifyParentsDialogProps) {
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!open) setReason("");
  }, [open]);

  const copy = variantCopy(variant, parentCount);
  const sendDisabled =
    isPending ||
    (variant === "update" && changes.length === 0) ||
    (variant === "attendance" && addedAthletes.length === 0);

  function handleSend() {
    if (variant === "cancel") onSend(reason.trim() || undefined);
    else onSend();
  }

  function handleOpenChange(nextOpen: boolean) {
    // Cubre Escape y clic fuera del diálogo (Radix llama a onDismiss en
    // ambos casos). isPending bloquea el cierre mientras la acción está en
    // vuelo — mismo patrón que ConfirmDialog/ConfirmModal.
    if (!nextOpen && !isPending) onCancel();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent role="alertdialog" hideClose className="max-w-lg">
        <DialogHeader className="flex-row items-start justify-between gap-3 pr-6">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50">
              <Mail className="h-4 w-4 text-blue-600" aria-hidden="true" />
            </div>
            <div>
              <DialogTitle>{copy.title}</DialogTitle>
              <p className="mt-0.5 text-sm text-mid-gray">{copy.subject}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg p-1.5 text-mid-gray transition-colors hover:bg-light-gray disabled:opacity-50"
            aria-label="Cerrar diálogo"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <DialogDescription className="text-charcoal">
            {copy.intro}
          </DialogDescription>

          {variant === "update" && (
            <div
              className="rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3"
              role="note"
            >
              {changes.length === 0 ? (
                <p className="text-sm text-mid-gray">
                  No detectamos cambios relevantes que valga la pena comunicar.
                </p>
              ) : (
                <>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                    Cambios detectados
                  </p>
                  <ul className="space-y-1.5 text-sm text-charcoal">
                    {changes.map((c) => (
                      <li key={c.field} className="flex flex-wrap gap-x-2">
                        <span className="font-medium">{c.fieldLabel}:</span>
                        <span className="text-mid-gray line-through">
                          {c.oldValue}
                        </span>
                        <span aria-hidden="true">→</span>
                        <span>{c.newValue}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}

          {variant === "attendance" && (
            <div className="space-y-3">
              {addedAthletes.length > 0 && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-800">
                    Atletas añadidos
                  </p>
                  <ul className="space-y-0.5 text-sm text-charcoal">
                    {addedAthletes.map((a) => (
                      <li key={a.id}>+ {a.name}</li>
                    ))}
                  </ul>
                </div>
              )}
              {removedAthletes.length > 0 && (
                <div className="rounded-xl border border-[rgba(34,42,53,0.08)] bg-light-gray/40 px-4 py-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-mid-gray">
                    Atletas retirados (no se notifican)
                  </p>
                  <ul className="space-y-0.5 text-sm text-mid-gray">
                    {removedAthletes.map((a) => (
                      <li key={a.id}>− {a.name}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {variant === "cancel" && (
            <div>
              <label
                htmlFor="cancel-reason"
                className="block text-sm font-medium text-charcoal"
              >
                Motivo (opcional)
              </label>
              <textarea
                id="cancel-reason"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
                placeholder="Ej: Lluvia intensa, cierre de la pista..."
                disabled={isPending}
                className="mt-1 w-full resize-none rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
              />
              <p className="mt-1 text-xs text-mid-gray">
                Se incluirá en el email enviado a los padres.
              </p>
            </div>
          )}

          {errorMessage && (
            <p className="text-sm text-red-600" role="alert" aria-live="assertive">
              {errorMessage}
            </p>
          )}
        </DialogBody>

        <DialogFooter className="flex-wrap">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
            style={btnSecondaryStyle}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onSkip}
            disabled={isPending}
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-80 disabled:opacity-50"
            style={btnSecondaryStyle}
          >
            <MailX className="h-4 w-4" aria-hidden="true" />
            No enviar
          </button>
          <button
            type="button"
            onClick={handleSend}
            disabled={sendDisabled}
            className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            style={btnPrimaryStyle}
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Mail className="h-4 w-4" aria-hidden="true" />
            )}
            {isPending ? "Guardando…" : "Enviar notificación"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
