/**
 * ExerciseFormDialog — Dialog shadcn/ui que envuelve ExerciseForm para
 * crear o editar un ejercicio del catálogo (US5 / T046).
 *
 * Comportamiento:
 *   - Crea: llama useCreateExercise y cierra al éxito.
 *   - Edita: llama useUpdateExercise (requiere exerciseId) y cierra al éxito.
 *   - Focus-trapped por Radix Dialog; Escape cierra el diálogo.
 *   - Muestra error de API inline con copy en español.
 *   - La invalidación de caché (catálogo + detalle) la maneja el hook.
 *
 * Uso en modo creación:
 *   <ExerciseFormDialog open={open} onOpenChange={setOpen} />
 *
 * Uso en modo edición:
 *   <ExerciseFormDialog
 *     open={open}
 *     onOpenChange={setOpen}
 *     exerciseId={exercise.id}
 *     defaultValues={exercise}
 *   />
 */
import { useState } from "react";

import { mapTechniqueError } from "@/api/technique";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ExerciseForm } from "@/components/technique/ExerciseForm";
import {
  useCreateExercise,
  useUpdateExercise,
} from "@/hooks/technique/useTechnique";
import type { ExerciseCreateForm } from "@/schemas/technique.schemas";
import type { ExerciseDetail } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ExerciseFormDialogProps {
  /** Controls dialog visibility — caller owns the open/close state. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * When provided the dialog is in "edit" mode:
   *   - exerciseId targets the PUT endpoint.
   *   - defaultValues pre-fills the form fields.
   */
  exerciseId?: number;
  defaultValues?: Partial<ExerciseDetail>;
  /**
   * Optional callback fired after a successful create or edit.
   * The returned ExerciseDetail is passed so the caller can navigate
   * to the new exercise detail page if needed.
   */
  onSuccess?: (exercise: ExerciseDetail) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExerciseFormDialog({
  open,
  onOpenChange,
  exerciseId,
  defaultValues,
  onSuccess,
}: ExerciseFormDialogProps) {
  const isEdit = exerciseId !== undefined && exerciseId > 0;

  const [apiError, setApiError] = useState<string | null>(null);

  const createMutation = useCreateExercise();
  const updateMutation = useUpdateExercise();

  const isPending = createMutation.isPending || updateMutation.isPending;

  function handleSubmit(values: ExerciseCreateForm) {
    setApiError(null);

    // Normalise: empty strings for optional ASCII layout should become null
    const payload = {
      ...values,
      layout_ascii: values.layout_ascii?.trim() || null,
      layout_alt: values.layout_alt?.trim() || null,
    };

    if (isEdit) {
      updateMutation.mutate(
        { id: exerciseId, input: payload },
        {
          onSuccess: (data) => {
            onOpenChange(false);
            onSuccess?.(data);
          },
          onError: (err) => {
            setApiError(mapTechniqueError(err).message);
          },
        },
      );
    } else {
      createMutation.mutate(payload, {
        onSuccess: (data) => {
          onOpenChange(false);
          onSuccess?.(data);
        },
        onError: (err) => {
          setApiError(mapTechniqueError(err).message);
        },
      });
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    // Prevent closing while mutation is in flight
    if (isPending && !nextOpen) return;
    setApiError(null);
    onOpenChange(nextOpen);
  }

  const title = isEdit ? "Editar ejercicio" : "Nuevo ejercicio";
  const description = isEdit
    ? "Actualiza los datos del ejercicio. Los cambios no afectan sesiones ya guardadas."
    : "Agrega un ejercicio personalizado al catálogo del club.";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[90dvh] w-full max-w-2xl overflow-y-auto"
        aria-label={title}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <DialogBody>
          {/* API-level error banner (shown above the form fields) */}
          {apiError && (
            <div
              role="alert"
              className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {apiError}
            </div>
          )}

          <ExerciseForm
            defaultValues={defaultValues}
            onSubmit={handleSubmit}
            isPending={isPending}
            submitLabel={isEdit ? "Guardar cambios" : "Crear ejercicio"}
            onCancel={() => handleOpenChange(false)}
          />
        </DialogBody>

        {/* DialogFooter is intentionally empty: the form renders its own
            submit/cancel buttons inside DialogBody so they stay visually
            adjacent to the last field group on small screens. */}
        <DialogFooter className="hidden" aria-hidden="true" />
      </DialogContent>
    </Dialog>
  );
}

export default ExerciseFormDialog;
