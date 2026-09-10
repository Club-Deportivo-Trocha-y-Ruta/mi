/**
 * StaffStateDialog — confirmación de desactivar/reactivar una cuenta de
 * personal (feature 041 — gobernanza multi-coach, US3).
 * contracts/staff-admin.md §10.
 *
 * Sobre `ConfirmDialog` (`components/shared/ConfirmDialog.tsx`), usando su
 * slot `children` para el Select de motivo — a diferencia de
 * `ArchiveAthleteDialog`/`RestoreAthleteDialog`, que reimplementan
 * `AlertDialog` a mano porque fueron escritos antes de que `ConfirmDialog`
 * ganara ese slot.
 */
import * as React from "react";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuditReasonCodes } from "@/hooks/useAuditReasonCodes";

export const REACTIVATION_REASON_CODE = "account_reactivation";

export interface StaffStateDialogProps {
  open: boolean;
  action: "deactivate" | "reactivate" | null;
  staffFullName: string;
  isPending?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: (reasonCode: string) => void;
}

export function StaffStateDialog({
  open,
  action,
  staffFullName,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: StaffStateDialogProps) {
  const isDeactivate = action === "deactivate";
  const [reasonCode, setReasonCode] = React.useState("");
  const [validationError, setValidationError] = React.useState(false);
  const reasonCodesQuery = useAuditReasonCodes("account", open && isDeactivate);

  React.useEffect(() => {
    if (!open) {
      setReasonCode("");
      setValidationError(false);
    }
  }, [open]);

  const reasonOptions = (reasonCodesQuery.data?.items ?? []).filter(
    (option) => option.code !== REACTIVATION_REASON_CODE,
  );

  function handleConfirm() {
    if (isDeactivate) {
      if (!reasonCode) {
        setValidationError(true);
        return;
      }
      onConfirm(reasonCode);
      return;
    }
    onConfirm(REACTIVATION_REASON_CODE);
  }

  return (
    <ConfirmDialog
      open={open}
      title={
        isDeactivate ? "¿Desactivar esta cuenta?" : "¿Reactivar esta cuenta?"
      }
      description={
        isDeactivate
          ? `La persona no podrá volver a iniciar sesión. Su nombre seguirá visible en el historial de lo que hizo.${
              staffFullName ? ` (${staffFullName})` : ""
            }`
          : "La persona podrá iniciar sesión de nuevo con su contraseña actual."
      }
      tone={isDeactivate ? "danger" : "default"}
      confirmLabel={isDeactivate ? "Desactivar" : "Reactivar"}
      isPending={isPending}
      errorMessage={errorMessage}
      onConfirm={handleConfirm}
      onCancel={onCancel}
    >
      <div data-testid="staff-state-dialog">
        {isDeactivate && (
          <div className="space-y-1">
            <label htmlFor="staff-reason-select" className="text-xs font-medium text-mid-gray">
              Motivo
            </label>
            <Select
              value={reasonCode}
              onValueChange={(value) => {
                setReasonCode(value);
                setValidationError(false);
              }}
            >
              <SelectTrigger id="staff-reason-select" data-testid="staff-reason-select">
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
                Debes indicar el motivo de la desactivación
              </p>
            )}
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}
