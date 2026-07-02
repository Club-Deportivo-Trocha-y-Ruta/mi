/**
 * ExerciseCard — tarjeta compacta para el catálogo de Fuerza y Acondicionamiento
 * (feature 021 / T016).
 *
 * Muestra:
 *   - Nombre del ejercicio (enlace a la ruta de detalle)
 *   - Chip de equipo requerido
 *   - Chip de categoría de movimiento
 *   - Chips de franja de edad
 *   - Duración y repeticiones sugeridas
 *   - Resumen corto (1-2 líneas truncadas)
 *
 * Mirror de `components/technique/ExerciseCard.tsx` (feature 018): enlace
 * explícito sobre el nombre (no toda la tarjeta clickable), área de clic
 * mínima 48×48 px (WCAG).
 */
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

// ---------------------------------------------------------------------------
// Local shapes — mirror ExerciseOut (contracts/strength-api.md).
// Canonical types land in `@/types/strength.types` (owned by T015); these
// stay compatible so a future import swap is a no-op.
// ---------------------------------------------------------------------------

export type StrengthEquipmentKind = "sin_equipo" | "equipo_gym";

export type StrengthMovementCategory =
  | "empuje_superior"
  | "traccion_superior"
  | "inferior_bilateral"
  | "inferior_unilateral"
  | "core_estabilidad";

export type StrengthAgeBand = "10-12" | "13-15";

export interface StrengthExerciseListItem {
  id: number;
  slug: string;
  name: string;
  summary: string;
  equipment: StrengthEquipmentKind;
  equipment_detail?: string | null;
  movement_category: StrengthMovementCategory;
  age_bands: StrengthAgeBand[];
  suggested_duration_min: number;
  suggested_reps: string;
  is_seeded: boolean;
  is_hidden: boolean;
}

// ---------------------------------------------------------------------------
// Label maps (español neutro)
// ---------------------------------------------------------------------------

export const EQUIPMENT_LABEL: Record<StrengthEquipmentKind, string> = {
  sin_equipo: "Sin equipo",
  equipo_gym: "Equipo de gimnasio",
};

export const MOVEMENT_CATEGORY_LABEL: Record<StrengthMovementCategory, string> = {
  empuje_superior: "Empuje superior",
  traccion_superior: "Tracción superior",
  inferior_bilateral: "Inferior bilateral",
  inferior_unilateral: "Inferior unilateral",
  core_estabilidad: "Core y estabilidad",
};

export const STRENGTH_AGE_BAND_LABEL: Record<StrengthAgeBand, string> = {
  "10-12": "10–12",
  "13-15": "13–15",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ExerciseCardProps {
  exercise: StrengthExerciseListItem;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExerciseCard({ exercise }: ExerciseCardProps) {
  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-2 py-4">
        {/* Name + equipment chip row */}
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/strength/exercises/${exercise.id}`}
            className="min-h-12 flex items-center text-sm font-semibold text-slate-900 leading-snug hover:text-primary focus-visible:outline-none focus-visible:underline"
          >
            {exercise.name}
          </Link>
          <Badge
            variant={exercise.equipment === "sin_equipo" ? "success" : "info"}
            className="shrink-0 text-[11px]"
          >
            {EQUIPMENT_LABEL[exercise.equipment]}
          </Badge>
        </div>

        {/* Summary */}
        {exercise.summary && (
          <p className="line-clamp-2 text-xs text-slate-500">
            {exercise.summary}
          </p>
        )}

        {/* Movement category */}
        <div>
          <Badge variant="outline" className="text-[11px]">
            {MOVEMENT_CATEGORY_LABEL[exercise.movement_category]}
          </Badge>
        </div>

        {/* Age-band chips */}
        {exercise.age_bands.length > 0 && (
          <div className="flex flex-wrap gap-1" aria-label="Franjas de edad">
            {exercise.age_bands.map((band) => (
              <Badge key={band} variant="secondary" className="text-[11px]">
                {STRENGTH_AGE_BAND_LABEL[band]} años
              </Badge>
            ))}
          </div>
        )}

        {/* Duration / reps indicator row */}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1 text-[11px] text-slate-500">
          <span>{exercise.suggested_duration_min} min</span>
          <span aria-hidden="true">·</span>
          <span>{exercise.suggested_reps}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default ExerciseCard;
