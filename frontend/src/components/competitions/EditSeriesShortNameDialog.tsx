/**
 * EditSeriesShortNameDialog — diálogo pequeño para que el coach fije el
 * nombre corto de una copa (`race_series.short_name`), usado en chips y
 * etiquetas compactas (ej. "Let's GO" en vez de "Copa Let's Go
 * Interdepartamental XCO").
 *
 * Hotfix multicopa — identidad de válida (2026-09-16). Disparado desde la
 * fila "Serie" de `InfoTab` — solo aplica a válidas de copa (no campeonato).
 *
 * Patrón: `Dialog` + React Hook Form + Zod, mismo estilo de
 * `CancelEventDialog` (calendar). Campo vacío → limpia `short_name` (vuelve
 * a usar el nombre completo en los chips).
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

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
  editSeriesShortNameSchema,
  type EditSeriesShortNameFormValues,
} from "@/schemas/raceSeries.schema";
import {
  getRaceSeriesErrorMessage,
  useUpdateRaceSeries,
} from "@/hooks/race/useRaceSeries";

export interface EditSeriesShortNameDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seriesId: number;
  /** Nombre completo de la serie — mostrado como referencia en el diálogo. */
  seriesName: string;
  /** Valor actual de `short_name`. `null`/`undefined` → campo vacío. */
  currentShortName?: string | null;
}

export function EditSeriesShortNameDialog({
  open,
  onOpenChange,
  seriesId,
  seriesName,
  currentShortName,
}: EditSeriesShortNameDialogProps) {
  const updateSeries = useUpdateRaceSeries();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EditSeriesShortNameFormValues>({
    resolver: zodResolver(editSeriesShortNameSchema),
    defaultValues: { short_name: currentShortName ?? "" },
  });

  // Resincroniza el form cada vez que el diálogo se abre (el valor actual
  // puede haber cambiado desde la última apertura).
  React.useEffect(() => {
    if (open) {
      reset({ short_name: currentShortName ?? "" });
    }
  }, [open, currentShortName, reset]);

  function onSubmit(values: EditSeriesShortNameFormValues) {
    // Campo vacío → limpia short_name (vuelve a usar el nombre completo).
    const trimmed = values.short_name?.trim() ?? "";
    const short_name = trimmed.length > 0 ? trimmed : null;
    updateSeries.mutate(
      { id: seriesId, body: { short_name } },
      {
        onSuccess: () => {
          toast.success("Nombre corto actualizado.");
          onOpenChange(false);
        },
        onError: (err) => {
          toast.error(getRaceSeriesErrorMessage(err));
        },
      },
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !updateSeries.isPending) onOpenChange(false);
      }}
    >
      <DialogContent data-testid="edit-series-short-name-dialog">
        <DialogHeader>
          <DialogTitle>Nombre corto de la copa</DialogTitle>
          <DialogDescription>
            <span className="font-medium text-charcoal">{seriesName}</span>
            <br />
            Se usa en chips y etiquetas donde el espacio es limitado (ej.
            &quot;Let&apos;s GO&quot;). Déjalo vacío para usar el nombre
            completo.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            void handleSubmit(onSubmit)(e);
          }}
          noValidate
        >
          <DialogBody className="space-y-2">
            <label
              htmlFor="series-short-name-input"
              className="block text-xs font-medium text-mid-gray"
            >
              Nombre corto{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="series-short-name-input"
              type="text"
              placeholder="Ej: Let's GO"
              {...register("short_name")}
              className="w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 min-h-12 shadow-ring"
              aria-invalid={!!errors.short_name}
              aria-describedby={
                errors.short_name ? "series-short-name-error" : undefined
              }
            />
            {errors.short_name && (
              <p id="series-short-name-error" className="text-xs text-red-600" role="alert">
                {errors.short_name.message}
              </p>
            )}
          </DialogBody>

          <DialogFooter>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={updateSeries.isPending}
              className="min-h-12 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-80 disabled:opacity-50 shadow-ring"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={updateSeries.isPending}
              data-testid="edit-series-short-name-submit"
              className="flex min-h-12 items-center justify-center gap-2 rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {updateSeries.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Guardar
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
