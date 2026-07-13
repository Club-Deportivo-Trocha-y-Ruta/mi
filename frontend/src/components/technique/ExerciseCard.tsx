/**
 * ExerciseCard — tarjeta compacta para el catálogo de ejercicios (US1 / T014).
 *
 * Muestra:
 *   - Nombre del ejercicio (enlace a la ruta de detalle)
 *   - Badge de dificultad (verde / ámbar / rojo)
 *   - Chips de franja de edad
 *   - Chips de habilidades
 *   - Indicadores gymkhana y sin material
 *   - Resumen corto (1 línea truncado)
 *
 * WCAG: área de clic mínima 48×48 px (min-h-12 + p padding); uso de Link
 * desde react-router (no <a href>). La tarjeta entera NO es clickable como un
 * solo elemento; el enlace es explícito sobre el nombre, manteniendo la
 * semántica correcta para lectores de pantalla.
 */
import { Link } from "react-router-dom";
import { CalendarPlus, Loader2, Pencil } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { ExerciseListItem, Difficulty, AgeBand } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Label maps
// ---------------------------------------------------------------------------

const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  facil: "Fácil",
  media: "Media",
  avanzada: "Avanzada",
};

const DIFFICULTY_VARIANT: Record<
  Difficulty,
  "success" | "warning" | "destructive"
> = {
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

export function ExerciseCard({
  exercise,
  onEdit,
  onAttach,
  isAttaching = false,
}: ExerciseCardProps) {
  const hasSinMaterial = exercise.materials.some((m) => m.is_none);

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-2 py-4">
        {/* Name + difficulty + edit affordance row */}
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/technique/exercises/${exercise.id}`}
            className="min-h-12 flex items-center text-sm font-semibold text-slate-900 leading-snug hover:text-primary focus-visible:outline-none focus-visible:underline"
          >
            {exercise.name}
          </Link>
          <div className="flex shrink-0 items-center gap-1">
            <Badge variant={DIFFICULTY_VARIANT[exercise.difficulty]}>
              {DIFFICULTY_LABEL[exercise.difficulty]}
            </Badge>
            {onAttach && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-slate-400 hover:text-slate-700"
                onClick={() => onAttach(exercise)}
                disabled={isAttaching}
                aria-label={`Adjuntar ${exercise.name} a una sesión`}
              >
                {isAttaching ? (
                  <Loader2
                    size={14}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <CalendarPlus size={14} aria-hidden="true" />
                )}
              </Button>
            )}
            {onEdit && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-slate-400 hover:text-slate-700"
                onClick={() => onEdit(exercise)}
                aria-label={`Editar ejercicio ${exercise.name}`}
              >
                <Pencil size={14} aria-hidden="true" />
              </Button>
            )}
          </div>
        </div>

        {/* Summary */}
        {exercise.summary && (
          <p className="line-clamp-2 text-xs text-slate-500">
            {exercise.summary}
          </p>
        )}

        {/* Age-band chips */}
        {exercise.age_bands.length > 0 && (
          <div className="flex flex-wrap gap-1" aria-label="Franjas de edad">
            {exercise.age_bands.map((band) => (
              <Badge key={band} variant="info" className="text-[11px]">
                {AGE_BAND_LABEL[band]} años
              </Badge>
            ))}
          </div>
        )}

        {/* Skill chips */}
        {exercise.skills.length > 0 && (
          <div className="flex flex-wrap gap-1" aria-label="Habilidades">
            {exercise.skills.map((skill) => (
              <Badge key={skill.slug} variant="outline" className="text-[11px]">
                {skill.name}
              </Badge>
            ))}
          </div>
        )}

        {/* Indicators row */}
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
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
      </CardContent>
    </Card>
  );
}

export default ExerciseCard;
