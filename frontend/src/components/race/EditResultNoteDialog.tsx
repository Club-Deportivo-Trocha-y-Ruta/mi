/**
 * EditResultNoteDialog — Sheet lateral para agregar, editar o eliminar la nota
 * cualitativa del entrenador sobre un corredor del club en una válida.
 *
 * Usado desde ResultsTable (filas is_our_club, solo coach/admin).
 * Precarga el texto existente cuando ya hay una nota. Ofrece acción "Eliminar
 * nota" cuando la fila ya tiene coach_note.
 *
 * Flujo de estados:
 *  - Guardando: spinner en el botón, inputs deshabilitados.
 *  - Éxito: toast inline, cierra el sheet tras 1.2 s.
 *  - Error: toast inline con mensaje, sheet permanece abierto.
 *  - Error de eliminación: toast inline, sheet permanece abierto.
 *
 * Accesibilidad:
 *  - Focus trap + Escape dismiss vía Radix Dialog (Sheet).
 *  - 48×48px touch targets en botones de acción.
 *  - aria-invalid + role="alert" en mensajes de error.
 *  - focus-visible:ring en todos los controles interactivos.
 *
 * Privacidad: La nota es solo para coach/admin — el componente no se monta
 * nunca para rol padre (la restricción se aplica en ResultsTable).
 */
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2, Trash2, XCircle } from "lucide-react";
import { z } from "zod";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import {
  useSetResultCoachNote,
  useClearResultCoachNote,
} from "@/hooks/race/useRaceResults";
import { cn } from "@/lib/utils";
import type { RaceResultsFilters } from "@/types/raceResults.types";

// ---------------------------------------------------------------------------
// Zod schema
// ---------------------------------------------------------------------------

const editResultNoteSchema = z.object({
  note: z
    .string()
    .trim()
    .min(1, "La nota no puede estar vacía.")
    .max(500, "La nota no puede superar 500 caracteres."),
});

type EditResultNoteValues = z.infer<typeof editResultNoteSchema>;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditResultNoteDialogProps {
  /** PK de la fila race_results — requerida para los endpoints PUT/DELETE. */
  resultId: number;
  /** Nombre del corredor para el encabezado del sheet (coach/admin only). */
  displayName: string;
  /** Nota actual del entrenador. null cuando no hay nota. */
  currentNote: string | null;
  /** ID del race event — necesario para parchear la clave correcta del cache. */
  raceEventId: number;
  /** Filtros activos en ResultsTable — necesarios para invalidar la query key exacta. */
  filters?: RaceResultsFilters;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EditResultNoteDialog({
  resultId,
  displayName,
  currentNote,
  raceEventId,
  filters = {},
  open,
  onOpenChange,
}: EditResultNoteDialogProps) {
  const setNote = useSetResultCoachNote();
  const clearNote = useClearResultCoachNote();

  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const hasExistingNote = !!currentNote && currentNote.trim() !== "";

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<EditResultNoteValues>({
    resolver: zodResolver(editResultNoteSchema),
    defaultValues: { note: currentNote ?? "" },
  });

  // Character counter
  const noteValue = watch("note") ?? "";
  const charCount = noteValue.length;

  // Re-sync when the sheet opens with fresh data
  useEffect(() => {
    if (open) {
      reset({ note: currentNote ?? "" });
      setToast(null);
    }
  }, [open, currentNote, reset]);

  const isPending = setNote.isPending || clearNote.isPending;

  function onSubmit(values: EditResultNoteValues) {
    setToast(null);
    setNote.mutate(
      {
        resultId,
        coach_note: values.note.trim(),
        raceEventId,
        filters,
      },
      {
        onSuccess: () => {
          setToast({
            type: "success",
            message: "Nota guardada correctamente.",
          });
          setTimeout(() => onOpenChange(false), 1200);
        },
        onError: () => {
          setToast({
            type: "error",
            message:
              "No se pudo guardar la nota. Verifica la conexión e intenta de nuevo.",
          });
        },
      },
    );
  }

  function handleClearNote() {
    setToast(null);
    clearNote.mutate(
      { resultId, raceEventId, filters },
      {
        onSuccess: () => {
          setToast({
            type: "success",
            message: "Nota eliminada correctamente.",
          });
          setTimeout(() => onOpenChange(false), 1200);
        },
        onError: () => {
          setToast({
            type: "error",
            message:
              "No se pudo eliminar la nota. Verifica la conexión e intenta de nuevo.",
          });
        },
      },
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle>
            {hasExistingNote ? "Editar nota" : "Agregar nota"}
          </SheetTitle>
          <SheetDescription>
            {displayName} — observación cualitativa de la válida
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <form
            id="edit-result-note-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
          >
            {/* Textarea principal */}
            <div className="space-y-1">
              <label
                htmlFor="ern-note"
                className="block text-xs font-medium text-mid-gray"
              >
                Nota del entrenador
              </label>
              <textarea
                id="ern-note"
                rows={5}
                maxLength={500}
                placeholder="Cómo se sintió el corredor, qué pasó en la salida, una caída, mejora técnica, ánimo…"
                disabled={isPending}
                {...register("note")}
                className={cn(
                  "w-full resize-y rounded-lg bg-white px-3 py-2 text-sm outline-none",
                  "focus:ring-2 focus:ring-blue-500/40",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                  "shadow-ring",
                  errors.note && "ring-1 ring-red-400",
                )}
                style={{
                  minHeight: "120px",
                }}
                aria-invalid={errors.note ? true : undefined}
                aria-describedby={
                  errors.note ? "ern-note-error" : "ern-note-hint"
                }
              />

              {/* Contador de caracteres + mensaje de error */}
              <div className="flex items-start justify-between gap-2">
                {errors.note ? (
                  <p
                    id="ern-note-error"
                    className="text-xs text-red-600"
                    role="alert"
                  >
                    {errors.note.message}
                  </p>
                ) : (
                  <span
                    id="ern-note-hint"
                    className="text-xs text-mid-gray"
                    aria-live="polite"
                  >
                    Máximo 500 caracteres
                  </span>
                )}
                <span
                  className={cn(
                    "shrink-0 text-xs tabular-nums",
                    charCount >= 480
                      ? "text-amber-600"
                      : "text-mid-gray",
                    charCount >= 500 && "text-red-600",
                  )}
                  aria-live="polite"
                  aria-atomic="true"
                >
                  {charCount}/500
                </span>
              </div>
            </div>

            {/* Toast inline — éxito o error */}
            {toast && (
              <div
                role="status"
                aria-live="polite"
                className={cn(
                  "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
                  toast.type === "success"
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-900"
                    : "border border-red-200 bg-red-50 text-red-800",
                )}
              >
                {toast.type === "success" ? (
                  <CheckCircle2
                    size={16}
                    aria-hidden="true"
                    className="mt-0.5 shrink-0"
                  />
                ) : (
                  <XCircle
                    size={16}
                    aria-hidden="true"
                    className="mt-0.5 shrink-0"
                  />
                )}
                <span>{toast.message}</span>
              </div>
            )}
          </form>

          {/* Acción de eliminar — solo cuando ya hay nota */}
          {hasExistingNote && (
            <div className="mt-6 border-t border-[rgba(34,42,53,0.08)] pt-4">
              <p className="mb-3 text-xs text-mid-gray">
                Eliminar la nota actual de este corredor para esta válida.
              </p>
              <button
                type="button"
                onClick={handleClearNote}
                disabled={isPending}
                className={cn(
                  "inline-flex min-h-[48px] items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                  "border border-red-200 text-red-700 hover:bg-red-50",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50",
                )}
                aria-label={`Eliminar nota de ${displayName}`}
              >
                {clearNote.isPending ? (
                  <Loader2
                    size={14}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Trash2 size={14} aria-hidden="true" />
                )}
                Eliminar nota
              </button>
            </div>
          )}
        </SheetBody>

        <SheetFooter>
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
            form="edit-result-note-form"
            disabled={isPending}
            className={cn(
              "inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white",
              "transition-opacity hover:opacity-90 disabled:opacity-50",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal/50",
            )}
          >
            {setNote.isPending && (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            )}
            Guardar
          </button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
