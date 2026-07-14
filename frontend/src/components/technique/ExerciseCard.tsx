/**
 * ExerciseCard — envoltorio config-driven del catálogo de técnica y gymkhana
 * sobre `LibraryEntityCard` compartido (feature 033 / T041).
 *
 * Antes una tarjeta completa (US1 / T014); ahora solo mapea un
 * `ExerciseListItem` a las props de `LibraryEntityCard` — badge de
 * dificultad + affordances de adjuntar/editar en `cornerContent`, chips de
 * franja de edad y habilidades en `chipGroups`, indicadores
 * gymkhana/juego/sin material en `footer`. El shell (enlace de 48×48 px
 * sobre el nombre, layout de tarjeta) vive en el componente compartido.
 */
import { CalendarPlus, Loader2, Pencil } from "lucide-react";

import { LibraryEntityCard } from "@/components/shared/LibraryEntityCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AgeBand, Difficulty, ExerciseListItem } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Label maps
// ---------------------------------------------------------------------------

const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  facil: "Fácil",
  media: "Media",
  avanzada: "Avanzada",
};

const DIFFICULTY_VARIANT: Record<Difficulty, "success" | "warning" | "destructive"> = {
  facil: "success",
  media: "warning",
  avanzada: "destructive",
};

const AGE_BAND_LABEL: Record<AgeBand, string> = {
  "7-9": "7–9",
  "10-12": "10–12",
  "13-15": "13–15",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ExerciseCardProps {
  exercise: ExerciseListItem;
  /**
   * When provided (coach/admin only), renders an edit icon-button on the card.
   * Absent for parent role — no curation affordance.
   */
  onEdit?: (exercise: ExerciseListItem) => void;
  /**
   * When provided (coach/admin only), renders a "adjuntar a una sesión"
   * affordance — the catalog-initiated attach entry point (feature 032,
   * T017, contracts/unified-attach-flow.md's entry point #2).
   */
  onAttach?: (exercise: ExerciseListItem) => void;
  /** True while this exercise's attach mutation is in flight (T017). */
  isAttaching?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExerciseCard({ exercise, onEdit, onAttach, isAttaching = false }: ExerciseCardProps) {
  const hasSinMaterial = exercise.materials.some((m) => m.is_none);

  return (
    <LibraryEntityCard
      href={`/technique/exercises/${exercise.id}`}
      title={exercise.name}
      summary={exercise.summary}
      cornerContent={
        <>
          <Badge variant={DIFFICULTY_VARIANT[exercise.difficulty]}>
            {DIFFICULTY_LABEL[exercise.difficulty]}
          </Badge>
          {onAttach && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-mid-gray hover:text-charcoal"
              onClick={() => onAttach(exercise)}
              disabled={isAttaching}
              aria-label={`Adjuntar ${exercise.name} a una sesión`}
            >
              {isAttaching ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <CalendarPlus size={14} aria-hidden="true" />
              )}
            </Button>
          )}
          {onEdit && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-mid-gray hover:text-charcoal"
              onClick={() => onEdit(exercise)}
              aria-label={`Editar ejercicio ${exercise.name}`}
            >
              <Pencil size={14} aria-hidden="true" />
            </Button>
          )}
        </>
      }
      chipGroups={[
        {
          ariaLabel: "Franjas de edad",
          chips: exercise.age_bands.map((band) => ({ key: band, label: `${AGE_BAND_LABEL[band]} años` })),
          renderChip: (chip) => (
            <Badge key={chip.key} variant="info" className="text-[11px]">
              {chip.label}
            </Badge>
          ),
        },
        {
          ariaLabel: "Habilidades",
          chips: exercise.skills.map((skill) => ({ key: skill.slug, label: skill.name })),
          renderChip: (chip) => (
            <Badge key={chip.key} variant="outline" className="text-[11px]">
              {chip.label}
            </Badge>
          ),
        },
      ]}
      footer={
        (exercise.is_gymkhana || exercise.is_game || hasSinMaterial) && (
          <div className="flex flex-wrap gap-1.5">
            {exercise.is_gymkhana && (
              <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-[11px] font-medium text-purple-800">
                Gymkhana
              </span>
            )}
            {exercise.is_game && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-medium text-blue-800">
                Juego
              </span>
            )}
            {hasSinMaterial && (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-800">
                Sin material
              </span>
            )}
          </div>
        )
      }
    />
  );
}

export default ExerciseCard;
