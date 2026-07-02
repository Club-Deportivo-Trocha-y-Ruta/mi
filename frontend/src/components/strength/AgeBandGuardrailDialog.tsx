/**
 * AgeBandGuardrailDialog — diálogo shadcn/ui mostrado cuando el backend
 * responde 422 `AGE_BAND_GUARDRAIL` al agregar un ejercicio a un bloque
 * cuya franja de edad objetivo no coincide con las franjas del ejercicio
 * (FR-011, US3, T030).
 *
 * Comportamiento:
 *   - Explica en español por qué el ejercicio no es apto para la franja
 *     de edad del bloque.
 *   - Ofrece un campo opcional de nota de anulación (`override_note`).
 *   - "Cancelar" cierra sin persistir la entrada (el bloque queda sin cambios).
 *   - "Confirmar anulación" reenvía la entrada con `is_age_override: true`
 *     y la nota capturada — el padre es responsable de reintentar la petición.
 *   - Focus-trapped por Radix Dialog; Escape y el botón "X" cierran el diálogo
 *     (Constitution III).
 *
 * Mirror de `ExerciseFormDialog.tsx` (feature 018) para el uso del API de
 * Dialog de shadcn/ui.
 */
import { useState } from "react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { STRENGTH_AGE_BAND_LABEL, type StrengthAgeBand } from "./ExerciseCard";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AgeBandGuardrailDialogProps {
  /** Controla la visibilidad del diálogo — el padre es dueño del estado open/close. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Nombre del ejercicio que disparó el guardrail. */
  exerciseName: string;
  /** Franjas de edad admitidas por el ejercicio. */
  exerciseAgeBands: StrengthAgeBand[];
  /** Franja de edad objetivo del bloque. */
  targetAgeBand: StrengthAgeBand;
  /**
   * Llamado al confirmar la anulación, con la nota opcional capturada.
   * El padre es responsable de reintentar el guardado con
   * `is_age_override: true` y `override_note`.
   */
  onConfirmOverride: (overrideNote: string | null) => void;
  /** true mientras el reintento con anulación está en curso. */
  isPending?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgeBandGuardrailDialog({
  open,
  onOpenChange,
  exerciseName,
  exerciseAgeBands,
  targetAgeBand,
  onConfirmOverride,
  isPending = false,
}: AgeBandGuardrailDialogProps) {
  const [overrideNote, setOverrideNote] = useState("");

  const exerciseBandsLabel = exerciseAgeBands
    .map((band) => STRENGTH_AGE_BAND_LABEL[band])
    .join(" y ");

  function handleOpenChange(nextOpen: boolean) {
    // Evita cerrar mientras el reintento está en curso
    if (isPending && !nextOpen) return;
    if (!nextOpen) setOverrideNote("");
    onOpenChange(nextOpen);
  }

  function handleCancel() {
    handleOpenChange(false);
  }

  function handleConfirm() {
    onConfirmOverride(overrideNote.trim() || null);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="w-full max-w-lg"
        aria-label="Ejercicio fuera de la franja de edad"
      >
        <DialogHeader>
          <DialogTitle>Ejercicio fuera de la franja de edad</DialogTitle>
          <DialogDescription>
            <strong>{exerciseName}</strong> está pensado para{" "}
            {exerciseBandsLabel} años, pero este bloque tiene como franja
            objetivo {STRENGTH_AGE_BAND_LABEL[targetAgeBand]} años. Agregarlo
            de todas formas puede no ser apropiado para el desarrollo motor
            de esta edad.
          </DialogDescription>
        </DialogHeader>

        <DialogBody>
          <p className="mb-3 text-sm text-charcoal">
            Puedes anular esta recomendación si consideras que el ejercicio
            es adecuado para este grupo en particular. Deja una nota opcional
            explicando el motivo (quedará registrada en el bloque).
          </p>

          <label
            htmlFor="age-band-override-note"
            className="mb-1 block text-sm font-medium text-charcoal"
          >
            Nota de anulación (opcional)
          </label>
          <Textarea
            id="age-band-override-note"
            value={overrideNote}
            onChange={(e) => setOverrideNote(e.target.value)}
            placeholder="Ej: atleta con buen dominio técnico, ejercicio adaptado con supervisión directa."
            rows={3}
            disabled={isPending}
          />
        </DialogBody>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={isPending}
          >
            Cancelar
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={isPending}>
            Confirmar anulación
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AgeBandGuardrailDialog;
