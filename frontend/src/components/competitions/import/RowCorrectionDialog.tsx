/**
 * RowCorrectionDialog — agrega, edita o elimina una fila de una categoría
 * parseada antes de confirmar la importación (feature 044, US1).
 *
 * El coach elige la operación (Agregar / Editar / Eliminar) y el puesto que
 * ubica la fila destino (research R-05: el `ordinal` identifica la fila
 * actual en edit/remove, o la posición que se agrega en add). Guardar
 * dispara `POST /imports/{parse_id}/corrections`, que recalcula la
 * completitud de la categoría — la respuesta se propaga a `onCorrected`
 * para que el llamador (`CategoryMappingTable`) actualice su estado local.
 *
 * Privacidad: nombre/ciudad/club de un corredor viajan en el body — nunca
 * se loggean ni entran a un mensaje de error (mismo criterio que
 * `completeness.CorrectionError`, que solo lleva un código y un ordinal).
 */
import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
} from "@/components/ui/dialog";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAddRowCorrection } from "@/hooks/ai/useRaceImports";
import { cn } from "@/lib/utils";
import {
  rowCorrectionSchema,
  type RowCorrectionFormValues,
} from "@/schemas/raceImportCorrections";
import type {
  CategoryCompleteness,
  ParsedResultsRow,
  RowCorrectionOp,
} from "@/types/raceImports.types";

const OP_LABELS: Record<RowCorrectionOp, string> = {
  add: "Agregar",
  edit: "Editar",
  remove: "Eliminar",
};

export interface RowCorrectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parseId: string;
  /** Header impreso de la categoría destino (`ParsedCategory.header_raw`). */
  categoryHeader: string;
  /** Operación sugerida por el hueco detectado (falta → add, repetido → edit). */
  initialOp?: RowCorrectionOp;
  /** Puesto sugerido — precarga el campo a partir de la pista de completitud. */
  initialOrdinal?: number | null;
  /** Fila existente a precargar (edit) — omitido para add/remove. */
  initialRow?: ParsedResultsRow | null;
  /** Se dispara al confirmar con éxito, con la completitud recalculada. */
  onCorrected: (completeness: CategoryCompleteness) => void;
}

export function RowCorrectionDialog({
  open,
  onOpenChange,
  parseId,
  categoryHeader,
  initialOp = "add",
  initialOrdinal = null,
  initialRow = null,
  onCorrected,
}: RowCorrectionDialogProps) {
  const correctionMutation = useAddRowCorrection();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<RowCorrectionFormValues>({
    resolver: zodResolver(rowCorrectionSchema),
    defaultValues: buildDefaults(initialOp, initialOrdinal, initialRow),
  });

  useEffect(() => {
    if (open) {
      reset(buildDefaults(initialOp, initialOrdinal, initialRow));
      setServerError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialOp, initialOrdinal, initialRow]);

  const op = watch("op");
  const isRemove = op === "remove";

  const onSubmit = (values: RowCorrectionFormValues) => {
    setServerError(null);
    correctionMutation.mutate(
      {
        parseId,
        body: {
          op: values.op,
          category_header: categoryHeader,
          ordinal: values.ordinal,
          row: isRemove
            ? null
            : {
                // El puesto ES la posición de la fila — no exponemos un campo
                // "posición" separado del ordinal (research R-05 §_build_row).
                position: values.ordinal,
                bib: values.bib?.trim() ?? "",
                name: values.name?.trim() ?? "",
                city: values.city?.trim() ?? "",
                club: values.club?.trim() ?? "",
                time_raw: values.time_raw?.trim() ?? "",
                points:
                  values.points === undefined || values.points === ""
                    ? 0
                    : Number(values.points),
              },
        },
      },
      {
        onSuccess: (response) => {
          onCorrected(response.completeness);
          onOpenChange(false);
        },
        onError: () => {
          setServerError(
            "No se pudo guardar la corrección. Verifica la conexión e intenta de nuevo.",
          );
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Corregir fila</DialogTitle>
          <DialogDescription>{categoryHeader}</DialogDescription>
        </DialogHeader>

        <DialogBody>
          <form
            id="row-correction-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
          >
            <div className="space-y-2">
              <span className="block text-xs font-medium text-mid-gray">
                Operación
              </span>
              <Controller
                name="op"
                control={control}
                render={({ field }) => (
                  <ToggleGroup
                    type="single"
                    value={field.value}
                    onValueChange={(v) => {
                      if (v) field.onChange(v as RowCorrectionOp);
                    }}
                    className="flex flex-wrap gap-2"
                    aria-label="Operación sobre la fila"
                  >
                    {(["add", "edit", "remove"] as const).map((value) => (
                      <ToggleGroupItem
                        key={value}
                        value={value}
                        aria-label={OP_LABELS[value]}
                        className="min-h-[48px] min-w-[88px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-2 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-surface"
                      >
                        {OP_LABELS[value]}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                )}
              />
            </div>

            <div className="space-y-1">
              <label
                htmlFor="rc-ordinal"
                className="block text-xs font-medium text-mid-gray"
              >
                Puesto
              </label>
              <input
                id="rc-ordinal"
                type="number"
                inputMode="numeric"
                min={1}
                {...register("ordinal", { valueAsNumber: true })}
                className={cn(
                  "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                  "min-h-[48px] shadow-ring",
                )}
                aria-invalid={errors.ordinal ? true : undefined}
                aria-describedby={errors.ordinal ? "rc-ordinal-error" : undefined}
              />
              {errors.ordinal && (
                <p id="rc-ordinal-error" className="text-xs text-red-600" role="alert">
                  {errors.ordinal.message}
                </p>
              )}
            </div>

            {isRemove ? (
              <div
                className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                role="note"
              >
                <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span>
                  Esta fila se quita de la categoría solo en esta importación.
                  Puedes deshacerlo agregándola de nuevo antes de confirmar.
                </span>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1 sm:col-span-2">
                  <label htmlFor="rc-name" className="block text-xs font-medium text-mid-gray">
                    Nombre
                  </label>
                  <input
                    id="rc-name"
                    type="text"
                    maxLength={200}
                    {...register("name")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.name ? true : undefined}
                    aria-describedby={errors.name ? "rc-name-error" : undefined}
                  />
                  {errors.name && (
                    <p id="rc-name-error" className="text-xs text-red-600" role="alert">
                      {errors.name.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label htmlFor="rc-bib" className="block text-xs font-medium text-mid-gray">
                    Dorsal
                  </label>
                  <input
                    id="rc-bib"
                    type="text"
                    maxLength={20}
                    {...register("bib")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.bib ? true : undefined}
                  />
                  {errors.bib && (
                    <p className="text-xs text-red-600" role="alert">
                      {errors.bib.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label htmlFor="rc-time" className="block text-xs font-medium text-mid-gray">
                    Tiempo (como aparece en el acta)
                  </label>
                  <input
                    id="rc-time"
                    type="text"
                    maxLength={20}
                    placeholder="ej: 00:45:12"
                    {...register("time_raw")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.time_raw ? true : undefined}
                  />
                  {errors.time_raw && (
                    <p className="text-xs text-red-600" role="alert">
                      {errors.time_raw.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label htmlFor="rc-city" className="block text-xs font-medium text-mid-gray">
                    Ciudad
                  </label>
                  <input
                    id="rc-city"
                    type="text"
                    maxLength={120}
                    {...register("city")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.city ? true : undefined}
                  />
                  {errors.city && (
                    <p className="text-xs text-red-600" role="alert">
                      {errors.city.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label htmlFor="rc-club" className="block text-xs font-medium text-mid-gray">
                    Club
                  </label>
                  <input
                    id="rc-club"
                    type="text"
                    maxLength={200}
                    {...register("club")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.club ? true : undefined}
                  />
                  {errors.club && (
                    <p className="text-xs text-red-600" role="alert">
                      {errors.club.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label htmlFor="rc-points" className="block text-xs font-medium text-mid-gray">
                    Puntos
                  </label>
                  <input
                    id="rc-points"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    {...register("points")}
                    className={cn(
                      "w-full rounded-lg bg-surface-raised px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px] shadow-ring",
                    )}
                    aria-invalid={errors.points ? true : undefined}
                  />
                  {errors.points && (
                    <p className="text-xs text-red-600" role="alert">
                      {errors.points.message}
                    </p>
                  )}
                </div>
              </div>
            )}

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
            disabled={correctionMutation.isPending}
            className="rounded-lg px-4 py-2 text-sm font-medium text-mid-gray hover:text-charcoal disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="row-correction-form"
            disabled={correctionMutation.isPending}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {correctionMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <CheckCircle2 size={14} aria-hidden="true" />
            )}
            Guardar
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function buildDefaults(
  op: RowCorrectionOp,
  ordinal: number | null,
  row: ParsedResultsRow | null,
): RowCorrectionFormValues {
  return {
    op,
    ordinal: ordinal ?? row?.position ?? 1,
    bib: row?.bib ?? "",
    name: row?.name ?? "",
    city: row?.city ?? "",
    club: row?.club ?? "",
    time_raw: row?.time_raw ?? "",
    points: row?.points ?? 0,
  };
}
