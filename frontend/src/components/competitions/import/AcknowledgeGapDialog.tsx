/**
 * AcknowledgeGapDialog — reconoce una categoría con completitud inconsistente
 * sin corregirla (feature 044, US1).
 *
 * El motivo viene del catálogo CERRADO `GET /imports/acknowledge-reasons`
 * (`useAcknowledgeReasons`) — nunca texto libre: un acta de menores invita a
 * escribir nombres en un campo abierto (mismo criterio que
 * `RevisionReasonCode` y `CancelEventDialog`). Al confirmar,
 * `completeness.status` pasa a `acknowledged` y el coach puede seguir.
 *
 * Usa `Dialog` (no `AlertDialog`) con `role="alertdialog"` explícito — un
 * `Select` de Radix dentro de un `AlertDialog` real cuelga jsdom en tests
 * (ver el docstring de `CancelEventDialog.tsx`).
 */
import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAcknowledgeCategory, useAcknowledgeReasons } from "@/hooks/ai/useRaceImports";
import {
  acknowledgeGapSchema,
  type AcknowledgeGapFormValues,
} from "@/schemas/raceImportCorrections";
import type { CategoryCompleteness } from "@/types/raceImports.types";

export interface AcknowledgeGapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parseId: string;
  categoryHeader: string;
  onAcknowledged: (completeness: CategoryCompleteness) => void;
}

export function AcknowledgeGapDialog({
  open,
  onOpenChange,
  parseId,
  categoryHeader,
  onAcknowledged,
}: AcknowledgeGapDialogProps) {
  const reasonsQuery = useAcknowledgeReasons();
  const acknowledgeMutation = useAcknowledgeCategory();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<AcknowledgeGapFormValues>({
    resolver: zodResolver(acknowledgeGapSchema),
    defaultValues: { reason: undefined },
  });

  useEffect(() => {
    if (open) {
      reset({ reason: undefined });
      setServerError(null);
    }
  }, [open, reset]);

  const onSubmit = (values: AcknowledgeGapFormValues) => {
    setServerError(null);
    acknowledgeMutation.mutate(
      { parseId, body: { category_header: categoryHeader, reason: values.reason } },
      {
        onSuccess: (response) => {
          onAcknowledged(response.completeness);
          onOpenChange(false);
        },
        onError: () => {
          setServerError(
            "No se pudo guardar el reconocimiento. Verifica la conexión e intenta de nuevo.",
          );
        },
      },
    );
  };

  const isPending = acknowledgeMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !isPending && onOpenChange(next)}>
      <DialogContent role="alertdialog" data-testid="acknowledge-gap-dialog">
        <DialogHeader>
          <DialogTitle>Reconocer categoría</DialogTitle>
          <DialogDescription>
            {categoryHeader} — indica por qué el hueco en los puestos viene del
            acta oficial, no de un error de lectura.
          </DialogDescription>
        </DialogHeader>

        <DialogBody>
          <form
            id="acknowledge-gap-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
          >
            <div className="space-y-1">
              <label
                htmlFor="ag-reason"
                className="block text-xs font-medium text-mid-gray"
              >
                Motivo
              </label>
              <Controller
                name="reason"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? ""}
                    onValueChange={(value) => field.onChange(value)}
                  >
                    <SelectTrigger
                      id="ag-reason"
                      data-testid="ag-reason-select"
                      disabled={reasonsQuery.isLoading}
                      aria-invalid={errors.reason ? true : undefined}
                      aria-describedby={errors.reason ? "ag-reason-error" : undefined}
                    >
                      <SelectValue placeholder="Selecciona un motivo…" />
                    </SelectTrigger>
                    <SelectContent>
                      {(reasonsQuery.data?.options ?? []).map((option) => (
                        <SelectItem key={option.code} value={option.code}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {errors.reason && (
                <p id="ag-reason-error" className="text-xs text-red-600" role="alert">
                  {errors.reason.message}
                </p>
              )}
            </div>

            {serverError && (
              <div
                role="alert"
                aria-live="polite"
                className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              >
                <XCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span>{serverError}</span>
              </div>
            )}
          </form>
        </DialogBody>

        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
            className="rounded-lg px-4 py-2 text-sm font-medium text-mid-gray hover:text-charcoal disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="acknowledge-gap-form"
            disabled={isPending}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <CheckCircle2 size={14} aria-hidden="true" />
            )}
            Reconocer
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
