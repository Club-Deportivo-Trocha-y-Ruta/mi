/**
 * Helpers de presentación únicos para `AttendanceStatus`.
 *
 * Antes existían (al menos) tres definiciones duplicadas de etiquetas + tonos
 * para los cinco estados de asistencia:
 *   - `STATUS_LABELS` / `STATUS_COLORS` en `parents/ReadOnlyAttendanceRow.tsx`
 *   - `ATTENDANCE_CONFIG` en `parents/ParentSessionCard.tsx`
 *   - Re-implementaciones puntuales en banners y filas read-only.
 *
 * Este módulo centraliza la fuente de verdad para que la vista padre y la
 * vista entrenador hablen exactamente el mismo idioma visual.
 *
 * Las clases en `ATTENDANCE_TONE` mantienen ratio de contraste AA sobre fondo
 * blanco (text-{color}-800/900 sobre bg-{color}-100).
 */
import type { AttendanceStatus } from "@/types/trainingSession.types";

export type { AttendanceStatus };

export const ATTENDANCE_LABELS: Record<AttendanceStatus, string> = {
  presente: "Presente",
  tarde: "Tarde",
  ausente: "Ausente",
  justificado: "Justificado",
  lesionado: "Lesionado",
};

/**
 * Clases Tailwind para mostrar el estado como badge / chip. No incluyen
 * radio ni padding — el componente consumidor decide la forma (pill, square).
 */
export const ATTENDANCE_TONE: Record<AttendanceStatus, string> = {
  presente: "bg-green-100 text-green-800",
  tarde: "bg-amber-100 text-amber-800",
  ausente: "bg-red-100 text-red-700",
  justificado: "bg-blue-100 text-blue-800",
  lesionado: "bg-purple-100 text-purple-800",
};

/**
 * Helper combinado — útil para componentes que necesitan ambos.
 */
export function getAttendancePresentation(status: AttendanceStatus): {
  label: string;
  tone: string;
} {
  return {
    label: ATTENDANCE_LABELS[status],
    tone: ATTENDANCE_TONE[status],
  };
}
