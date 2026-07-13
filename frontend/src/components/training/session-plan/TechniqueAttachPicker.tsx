/**
 * TechniqueAttachPicker — adjunta ejercicios de técnica a una sesión de
 * entrenamiento ya existente (feature 032, US1, T015).
 *
 * Vive dentro de la sección Plan de una sesión (`PlanSection.tsx`, T021) —
 * a diferencia del extinto `SessionAssembler.tsx` (feature 018, removido por
 * 029), esta pieza NUNCA crea una sesión: la sesión ya existe y su id llega
 * por props. Filtra el catálogo (mismos filtros que `CatalogPage`), permite
 * seleccionar varios ejercicios a la vez y asignarles un segmento
 * (calentamiento / principal / vuelta a la calma) antes de adjuntarlos con un
 * solo envío — mirror conceptual de la sección por segmento de
 * `SessionAssembler.tsx`'s `SegmentSection`, sin los botones de reordenar:
 * el contrato del endpoint (`contracts/attach-technique-to-session.md`)
 * declara que `position` es solo orientativo — el servidor siempre agrega al
 * final de cada segmento, así que no hay orden que el cliente deba negociar.
 *
 * Estados idle/pending/error mirror `TemplatePicker.tsx`'s "Adjuntando…"
 * convention: el botón de envío se deshabilita y cambia de texto mientras la
 * mutación está pendiente; un error deja las selecciones intactas para poder
 * reintentar sin tener que volver a elegir todo (FR-009 — un reintento no
 * duplica filas, el servidor dedupea por (exercise_id, segment)).
 */
import * as React from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MixedAgeNotice } from "@/components/technique/MixedAgeNotice";
import { FilterBar } from "@/components/technique/FilterBar";
import { mapTechniqueError } from "@/api/technique";
import {
  useAttachTechniqueItems,
  useSessionExercises,
  useTechniqueCatalog,
} from "@/hooks/technique/useTechnique";
import { cn } from "@/lib/utils";
import type {
  AgeBand,
  CatalogFilters,
  Difficulty,
  ExerciseListItem,
  SessionSegment,
} from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Vocabulario controlado (español neutro)
// ---------------------------------------------------------------------------

const SEGMENT_LABEL: Record<SessionSegment, string> = {
  calentamiento: "Calentamiento",
  principal: "Principal",
  vuelta_calma: "Vuelta a la calma",
};

const SEGMENTS: SessionSegment[] = ["calentamiento", "principal", "vuelta_calma"];

const DEFAULT_SEGMENT: SessionSegment = "principal";

const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  facil: "Fácil",
  media: "Media",
  avanzada: "Avanzada",
};

const AGE_BAND_LABEL: Record<AgeBand, string> = {
  "7-9": "7–9",
  "10-12": "10–12",
  "13-15": "13–15",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TechniqueAttachPickerProps {
  /** Sesión de entrenamiento ya existente a la que se adjuntan ejercicios. */
  sessionId: number;
  className?: string;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function TechniqueAttachPicker({
  sessionId,
  className,
}: TechniqueAttachPickerProps): React.ReactElement {
  const [filters, setFilters] = React.useState<CatalogFilters>({});
  const [selections, setSelections] = React.useState<
    Map<number, SessionSegment>
  >(new Map());
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [mixesAgeBands, setMixesAgeBands] = React.useState(false);

  const catalog = useTechniqueCatalog(filters);
  const sessionExercises = useSessionExercises(sessionId);
  const attach = useAttachTechniqueItems(sessionId);

  const errorId = React.useId();

  const attachedIds = React.useMemo(
    () =>
      new Set(
        (sessionExercises.data ?? [])
          .filter((item) => !item.is_hidden)
          .map((item) => item.exercise_id),
      ),
    [sessionExercises.data],
  );

  function toggleSelection(exerciseId: number) {
    setSelections((prev) => {
      const next = new Map(prev);
      if (next.has(exerciseId)) {
        next.delete(exerciseId);
      } else {
        next.set(exerciseId, DEFAULT_SEGMENT);
      }
      return next;
    });
  }

  function changeSegment(exerciseId: number, segment: SessionSegment) {
    setSelections((prev) => {
      if (!prev.has(exerciseId)) return prev;
      const next = new Map(prev);
      next.set(exerciseId, segment);
      return next;
    });
  }

  function handleAttach() {
    if (selections.size === 0 || attach.isPending) return;
    setErrorMessage(null);
    const items = Array.from(selections.entries()).map(
      ([exercise_id, segment]) => ({ exercise_id, segment, position: 0 }),
    );
    attach.mutate(items, {
      onSuccess: (result) => {
        // Éxito: limpia las selecciones y muestra el aviso de franjas mixtas
        // si aplica. La lista de la sesión se refresca sola via invalidación
        // (useAttachTechniqueItems) — no hace falta setState manual aquí.
        setSelections(new Map());
        setMixesAgeBands(result.mixes_age_bands);
        toast.success(
          items.length === 1
            ? "Ejercicio de técnica adjuntado a la sesión."
            : "Ejercicios de técnica adjuntados a la sesión.",
        );
      },
      onError: (err) => {
        // Preserva las selecciones — el coach puede reintentar sin volver a
        // elegir (FR-009: un reintento idéntico no duplica filas server-side).
        setMixesAgeBands(false);
        const message = mapTechniqueError(err).message;
        setErrorMessage(message);
        toast.error(message);
      },
    });
  }

  return (
    <div className={cn("space-y-5", className)}>
      <AttachedExercisesList
        items={sessionExercises.data}
        isLoading={sessionExercises.isLoading}
      />

      <MixedAgeNotice mixes_age_bands={mixesAgeBands} />

      <FilterBar onChange={setFilters} />

      {errorMessage ? (
        <p
          id={errorId}
          role="alert"
          className="flex items-center gap-1.5 text-sm text-red-600"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      ) : null}

      <ExerciseSelectionGrid
        items={catalog.data?.items}
        isLoading={catalog.isLoading}
        isError={catalog.isError}
        hasActiveFilters={Object.keys(filters).length > 0}
        selections={selections}
        attachedIds={attachedIds}
        onToggle={toggleSelection}
        onSegmentChange={changeSegment}
      />

      <div className="flex items-center gap-3">
        <Button
          type="button"
          onClick={handleAttach}
          disabled={selections.size === 0 || attach.isPending}
          className="min-h-12 gap-2"
        >
          {attach.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : null}
          {attach.isPending
            ? "Adjuntando…"
            : `Adjuntar a la sesión${
                selections.size > 0 ? ` (${selections.size})` : ""
              }`}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lista de ejercicios ya adjuntos a la sesión — se refresca tras cada envío
// ---------------------------------------------------------------------------

interface AttachedExercisesListProps {
  items: ReturnType<typeof useSessionExercises>["data"];
  isLoading: boolean;
}

function AttachedExercisesList({
  items,
  isLoading,
}: AttachedExercisesListProps): React.ReactElement | null {
  const visible = (items ?? []).filter((item) => !item.is_hidden);

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Cargando técnica de la sesión…">
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (visible.length === 0) return null;

  return (
    <section
      aria-label="Ejercicios de técnica adjuntos a esta sesión"
      className="rounded-xl border border-slate-200 bg-white p-4"
    >
      <h3 className="mb-2 text-sm font-semibold text-slate-800">
        Ejercicios de técnica en esta sesión
      </h3>
      <ul className="space-y-1.5">
        {visible.map((item) => (
          <li
            key={`${item.exercise_id}-${item.segment}`}
            className="flex items-center gap-2 text-sm text-slate-700"
          >
            <Badge variant="secondary" className="text-[11px]">
              {SEGMENT_LABEL[item.segment]}
            </Badge>
            {item.name}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Grilla de selección múltiple con asignación de segmento por ítem
// ---------------------------------------------------------------------------

interface ExerciseSelectionGridProps {
  items: ExerciseListItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
  hasActiveFilters: boolean;
  selections: Map<number, SessionSegment>;
  attachedIds: Set<number>;
  onToggle: (exerciseId: number) => void;
  onSegmentChange: (exerciseId: number, segment: SessionSegment) => void;
}

function ExerciseSelectionGrid({
  items,
  isLoading,
  isError,
  hasActiveFilters,
  selections,
  attachedIds,
  onToggle,
  onSegmentChange,
}: ExerciseSelectionGridProps): React.ReactElement {
  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando catálogo de ejercicios…"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        No se pudo cargar el catálogo. Intenta de nuevo.
      </p>
    );
  }

  if (!items || items.length === 0) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        {hasActiveFilters
          ? "Sin resultados para estos filtros."
          : "El catálogo está vacío."}
      </p>
    );
  }

  return (
    <div
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      aria-label={`Selección de ejercicios: ${items.length} disponibles`}
    >
      {items.map((exercise) => (
        <SelectableExerciseCard
          key={exercise.id}
          exercise={exercise}
          selected={selections.has(exercise.id)}
          segment={selections.get(exercise.id) ?? DEFAULT_SEGMENT}
          alreadyAttached={attachedIds.has(exercise.id)}
          onToggle={() => onToggle(exercise.id)}
          onSegmentChange={(segment) => onSegmentChange(exercise.id, segment)}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tarjeta seleccionable — checkbox + selector de segmento inline
// ---------------------------------------------------------------------------

interface SelectableExerciseCardProps {
  exercise: ExerciseListItem;
  selected: boolean;
  segment: SessionSegment;
  alreadyAttached: boolean;
  onToggle: () => void;
  onSegmentChange: (segment: SessionSegment) => void;
}

function SelectableExerciseCard({
  exercise,
  selected,
  segment,
  alreadyAttached,
  onToggle,
  onSegmentChange,
}: SelectableExerciseCardProps): React.ReactElement {
  const checkboxId = `attach-select-${exercise.id}`;
  const segmentId = `attach-segment-${exercise.id}`;

  return (
    <Card
      className={cn(
        "flex h-full flex-col",
        selected && "border-primary ring-1 ring-primary",
      )}
    >
      <CardContent className="flex flex-1 flex-col gap-2 py-4">
        <div className="flex items-center gap-2">
          <input
            id={checkboxId}
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="h-12 w-12 shrink-0 rounded border-slate-300 text-primary focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <label
            htmlFor={checkboxId}
            className="min-h-12 flex flex-1 items-center text-sm font-semibold leading-snug text-slate-900"
          >
            {exercise.name}
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant={
              exercise.difficulty === "avanzada"
                ? "destructive"
                : exercise.difficulty === "media"
                  ? "warning"
                  : "success"
            }
            className="text-[11px]"
          >
            {DIFFICULTY_LABEL[exercise.difficulty]}
          </Badge>
          {exercise.age_bands.map((band) => (
            <Badge key={band} variant="info" className="text-[11px]">
              {AGE_BAND_LABEL[band]} años
            </Badge>
          ))}
          {alreadyAttached && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
              <Check className="h-3 w-3" aria-hidden="true" />
              Ya en la sesión
            </span>
          )}
        </div>

        {selected && (
          <div className="mt-1">
            <label
              htmlFor={segmentId}
              className="mb-1 block text-xs font-medium text-slate-700"
            >
              Segmento
            </label>
            <select
              id={segmentId}
              value={segment}
              onChange={(e) =>
                onSegmentChange(e.target.value as SessionSegment)
              }
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {SEGMENTS.map((s) => (
                <option key={s} value={s}>
                  {SEGMENT_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default TechniqueAttachPicker;
