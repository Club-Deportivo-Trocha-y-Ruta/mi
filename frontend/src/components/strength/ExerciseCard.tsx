/**
 * ExerciseCard — envoltorio config-driven del catálogo de Fuerza y
 * Acondicionamiento sobre `LibraryEntityCard` compartido (feature 033 / T042).
 *
 * Antes una tarjeta completa (feature 021 / T016, mirror de
 * `components/technique/ExerciseCard.tsx`); ahora solo mapea un
 * `StrengthExerciseListItem` a las props de `LibraryEntityCard` — badge de
 * equipo en `cornerContent`, categoría de movimiento + franjas de edad en
 * `chipGroups`, duración/repeticiones en `footer`. El shell (enlace de
 * 48×48 px sobre el nombre, layout de tarjeta) vive en el componente
 * compartido.
 *
 * Sigue exportando los tipos y label maps (`StrengthExerciseListItem`,
 * `StrengthEquipmentKind`, `StrengthMovementCategory`, `StrengthAgeBand`,
 * `EQUIPMENT_LABEL`, `MOVEMENT_CATEGORY_LABEL`, `STRENGTH_AGE_BAND_LABEL`)
 * — consumidos por `FilterBar.tsx`, `BlockAssembler.tsx`,
 * `AgeBandGuardrailDialog.tsx`, `StrengthBlockPicker.tsx` y
 * `routes/strength/ExerciseDetailPage.tsx`.
 */
import { LibraryEntityCard } from "@/components/shared/LibraryEntityCard";
import { Badge } from "@/components/ui/badge";

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
    <LibraryEntityCard
      href={`/strength/exercises/${exercise.id}`}
      title={exercise.name}
      summary={exercise.summary}
      cornerContent={
        <Badge variant={exercise.equipment === "sin_equipo" ? "success" : "info"} className="text-[11px]">
          {EQUIPMENT_LABEL[exercise.equipment]}
        </Badge>
      }
      chipGroups={[
        {
          ariaLabel: "Categoría de movimiento",
          chips: [
            {
              key: exercise.movement_category,
              label: MOVEMENT_CATEGORY_LABEL[exercise.movement_category],
            },
          ],
          renderChip: (chip) => (
            <Badge key={chip.key} variant="outline" className="text-[11px]">
              {chip.label}
            </Badge>
          ),
        },
        {
          ariaLabel: "Franjas de edad",
          chips: exercise.age_bands.map((band) => ({
            key: band,
            label: `${STRENGTH_AGE_BAND_LABEL[band]} años`,
          })),
          renderChip: (chip) => (
            <Badge key={chip.key} variant="secondary" className="text-[11px]">
              {chip.label}
            </Badge>
          ),
        },
      ]}
      footer={
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-mid-gray">
          <span>{exercise.suggested_duration_min} min</span>
          <span aria-hidden="true">·</span>
          <span>{exercise.suggested_reps}</span>
        </div>
      }
    />
  );
}

export default ExerciseCard;
