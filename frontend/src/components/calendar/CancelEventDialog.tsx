/**
 * CancelEventDialog — diálogo de confirmación para cancelar un evento del
 * calendario (feature 041 — gobernanza multi-coach).
 * contracts/session-coaches.md §7.2.
 *
 * Usa las primitivas `Dialog` (no `AlertDialog`) con `role="alertdialog"`
 * explícito — mismo patrón que `NotifyParentsDialog` (`components/training/
 * NotifyParentsDialog.tsx:164`), que también combina un `Select` de Radix
 * con un diálogo modal de confirmación. Decisión T067: la primera versión de
 * este componente usaba `AlertDialogPrimitive` real; en jsdom, abrir el
 * `Select` dentro de un `AlertDialog` de Radix deja dos `FocusScope`
 * "trapped" compitiendo por el foco (el del `AlertDialog` y el del popup del
 * `Select`) y entra en un loop síncrono infinito que cuelga la suite —
 * mismo síntoma que el bug documentado en `EventDrawer.tsx` para
 * `Dialog`+`AlertDialog` anidados, pero aquí entre `AlertDialog` y `Select`.
 * `Dialog` normal no lo sufre (verificado: `NotifyParentsDialog.test.tsx`
 * abre su propio Select sin colgarse), así que se migra a esa primitiva y se
 * conserva la semántica de alertdialog vía el atributo `role`. El
 * comportamiento visible no cambia: enfoca "No, volver" al abrir y el error
 * se muestra inline sin cerrar el diálogo.
 *
 * El motivo viene del catálogo cerrado `GET /api/audit/reason-codes` vía
 * `useAuditReasonCodes("cancel")` — nunca un arreglo hardcodeado en el
 * cliente (contracts/session-coaches.md §7.4).
 */
import * as React from "react";
import { Loader2 } from "lucide-react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuditReasonCodes } from "@/hooks/useAuditReasonCodes";
import { cn } from "@/lib/utils";

export interface CancelEventDialogProps {
  open: boolean;
  eventTitle?: string;
  isPending?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: (reasonCode: string) => void;
}

export function CancelEventDialog({
  open,
  eventTitle,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: CancelEventDialogProps) {
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const [reasonCode, setReasonCode] = React.useState("");
  const [validationError, setValidationError] = React.useState(false);
  const reasonCodesQuery = useAuditReasonCodes("cancel", open);

  React.useEffect(() => {
    if (!open) {
      setReasonCode("");
      setValidationError(false);
    }
  }, [open]);

  const reasonOptions = reasonCodesQuery.data?.items ?? [];

  function handleConfirm() {
    if (!reasonCode) {
      setValidationError(true);
      return;
    }
    setValidationError(false);
    onConfirm(reasonCode);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !isPending) onCancel();
      }}
    >
      <DialogContent
        role="alertdialog"
        hideClose
        data-testid="cancel-event-dialog"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          cancelRef.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>Cancelar evento</DialogTitle>
          <DialogDescription>
            {eventTitle && (
              <>
                <span className="font-medium text-charcoal">{eventTitle}</span>
                <br />
              </>
            )}
            El evento pasará al estado &apos;cancelado&apos;. Los participantes serán
            notificados.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="space-y-1">
            <label
              htmlFor="cancel-event-reason-select"
              className="text-xs font-medium text-mid-gray"
            >
              Motivo de la cancelación
            </label>
            <Select
              value={reasonCode}
              onValueChange={(value) => {
                setReasonCode(value);
                setValidationError(false);
              }}
            >
              <SelectTrigger
                id="cancel-event-reason-select"
                data-testid="cancel-event-reason-select"
                disabled={reasonCodesQuery.isLoading}
              >
                <SelectValue placeholder="Selecciona un motivo" />
              </SelectTrigger>
              <SelectContent>
                {reasonOptions.map((option) => (
                  <SelectItem key={option.code} value={option.code}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {validationError && (
              <p role="alert" className="text-sm text-danger">
                Selecciona un motivo de cancelación.
              </p>
            )}
          </div>

          {errorMessage && (
            <p role="alert" className="text-sm text-danger">
              {errorMessage}
            </p>
          )}
        </DialogBody>

        <DialogFooter>
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="min-h-12 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-80 disabled:opacity-50 shadow-ring"
          >
            No, volver
          </button>
          <button
            type="button"
            data-testid="cancel-event-confirm-button"
            onClick={(event) => {
              event.preventDefault();
              handleConfirm();
            }}
            disabled={isPending}
            className={cn(
              "flex min-h-12 items-center justify-center gap-2 rounded-lg bg-danger px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50",
            )}
          >
            {isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Cancelar evento
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
