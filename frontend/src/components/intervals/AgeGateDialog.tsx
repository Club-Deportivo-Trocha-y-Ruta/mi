/**
 * AgeGateDialog — diálogo shadcn/ui mostrado cuando el backend responde 422
 * con un código de compuerta por edad al guardar/adjuntar una estructura de
 * intervalos (feature 026, T014).
 *
 * Cubre los dos códigos del contrato (contracts/api.md):
 *
 *   1. `age_gate_confirmation_required` (FR-007, modo "confirmation"):
 *      La estructura para la categoría 10-12 es válida (Z1–Z2) pero requiere
 *      confirmación explícita del entrenador. El diálogo muestra un CTA
 *      "Confirmar estructura" que reenvía la petición con
 *      `age_gate_confirmed: true`. El padre es responsable del reintento.
 *
 *   2. `age_gate_z3_blocked` (FR-006, modo "blocked"):
 *      Intensidad Z3+ no está permitida para la categoría 10-12. Es un bloqueo
 *      duro: se muestra una explicación bloqueante SIN CTA de anulación. El
 *      entrenador debe corregir las zonas de los bloques señalados. El único
 *      botón cierra el diálogo.
 *
 * Comportamiento (espeja `strength/AgeBandGuardrailDialog.tsx`):
 *   - Focus-trapped por Radix Dialog; Escape y el botón "X" cierran el diálogo
 *     (cierre explícito, Constitution III).
 *   - No cierra mientras un reintento está en curso.
 */
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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Franja de edad objetivo declarada por el entrenador (data-model.md). */
export type IntervalAgeBand = "10-12" | "13-15";

/** Etiqueta en español neutro (Colombia) para cada franja de edad. */
export const INTERVAL_AGE_BAND_LABEL: Record<IntervalAgeBand, string> = {
  "10-12": "10 a 12 años",
  "13-15": "13 a 15 años",
};

/** Modo del diálogo, derivado del código 422 del backend. */
export type AgeGateMode = "confirmation" | "blocked";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AgeGateDialogProps {
  /** Controla la visibilidad — el padre es dueño del estado open/close. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Qué código de compuerta disparó el diálogo:
   *   - "confirmation" → `age_gate_confirmation_required` (con CTA de confirmar)
   *   - "blocked"      → `age_gate_z3_blocked` (bloqueo duro, sin CTA de anulación)
   */
  mode: AgeGateMode;
  /** Franja de edad objetivo de la estructura. */
  targetAgeBand: IntervalAgeBand;
  /**
   * Mensaje del backend (`detail.message`). Si se omite, se usa un texto por
   * defecto según el modo. Siempre en español neutro.
   */
  message?: string;
  /**
   * Posiciones de los bloques afectados (`detail.positions`), usadas solo en
   * el modo "blocked" para indicar qué bloques corregir.
   */
  positions?: number[];
  /**
   * Solo en modo "confirmation": llamado al confirmar. El padre reenvía la
   * petición con `age_gate_confirmed: true`.
   */
  onConfirm?: () => void;
  /** true mientras el reintento con confirmación está en curso. */
  isPending?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgeGateDialog({
  open,
  onOpenChange,
  mode,
  targetAgeBand,
  message,
  positions,
  onConfirm,
  isPending = false,
}: AgeGateDialogProps) {
  const bandLabel = INTERVAL_AGE_BAND_LABEL[targetAgeBand];

  function handleOpenChange(nextOpen: boolean) {
    // Evita cerrar mientras el reintento de confirmación está en curso.
    if (isPending && !nextOpen) return;
    onOpenChange(nextOpen);
  }

  function handleClose() {
    handleOpenChange(false);
  }

  function handleConfirm() {
    onConfirm?.();
  }

  const isBlocked = mode === "blocked";

  const title = isBlocked
    ? "Intensidad no permitida para esta categoría"
    : "Confirmá la estructura para esta categoría";

  const defaultMessage = isBlocked
    ? `Intensidad Z3 o superior no está disponible para la categoría ${bandLabel}.`
    : `Esta estructura es para la categoría ${bandLabel}. Confirmá explícitamente antes de guardarla.`;

  const positionsLabel =
    positions && positions.length > 0
      ? positions.join(", ")
      : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-full max-w-lg" aria-label={title}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{message ?? defaultMessage}</DialogDescription>
        </DialogHeader>

        <DialogBody>
          {isBlocked ? (
            <div className="space-y-3 text-sm text-charcoal">
              <p>
                Para las edades de {bandLabel} el entrenamiento se mantiene en
                zonas suaves (Z1–Z2). Los bloques de alta intensidad no son
                apropiados para el desarrollo de este grupo, por eso no es
                posible guardar la estructura tal como está.
              </p>
              {positionsLabel && (
                <p>
                  Ajustá la zona de{" "}
                  {positions!.length === 1
                    ? "el bloque"
                    : "los bloques"}{" "}
                  <strong>{positionsLabel}</strong> a Z1 o Z2 para continuar.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-charcoal">
              Revisá que la estructura sea adecuada para la categoría{" "}
              {bandLabel}. Al confirmar, la estructura quedará marcada como
              revisada para este grupo de edad y se guardará.
            </p>
          )}
        </DialogBody>

        <DialogFooter>
          {isBlocked ? (
            <Button type="button" onClick={handleClose}>
              Entendido
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={isPending}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                onClick={handleConfirm}
                disabled={isPending}
              >
                Confirmar estructura
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AgeGateDialog;
