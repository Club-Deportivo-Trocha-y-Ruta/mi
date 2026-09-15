/**
 * CourseTab — pestaña/panel de perfil de circuito de una válida (feature 043).
 *
 * Orquesta la vista completa del circuito: variantes + vueltas por categoría,
 * con estados de carga/error/vacío. Usado tanto como pestaña de página
 * completa (con encabezado propio) como panel embebido en el Import Wizard
 * (`compact`, sin encabezado — el wizard ya muestra "Circuito (opcional)").
 *
 * La descripción cualitativa (T041-T043) y el resumen visual con mapa +
 * perfil de elevación (`CourseSummary`, T058) son fases posteriores — se
 * dejan marcadas con placeholders para no bloquear esta tarea.
 */
import { useState } from "react";

import { CategorySetupTable } from "@/components/race/course/CategorySetupTable";
import { CourseDescriptionCard } from "@/components/race/course/CourseDescriptionCard";
import { VariantsCard } from "@/components/race/course/VariantsCard";
import { VariantUploadDialog } from "@/components/race/course/VariantUploadDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRaceCourse } from "@/hooks/race/useRaceCourse";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CourseTabProps {
  raceEventId: number;
  /**
   * Espaciado reducido y sin encabezado de página — usado dentro del panel
   * "Circuito (opcional)" del Import Wizard, que ya aporta su propio título.
   */
  compact?: boolean;
  /** Rol parent — se propaga a `VariantsCard`/`CategorySetupTable` para
   * ocultar acciones de edición. Nada llama esto todavía (fase posterior). */
  readOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Sub-componentes de estado
// ---------------------------------------------------------------------------

function CourseTabSkeleton({ compact }: { compact?: boolean }) {
  return (
    <div
      className={cn("space-y-2 rounded-xl bg-white p-4", !compact && "shadow-card")}
      role="status"
      aria-busy="true"
      aria-label="Cargando circuito…"
      data-testid="course-tab-loading"
    >
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

function CourseTabError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6 shadow-card"
      role="alert"
      data-testid="course-tab-error"
    >
      <p className="text-sm text-mid-gray">
        No se pudo cargar el circuito. Intenta de nuevo.
      </p>
      <Button variant="outline" size="lg" onClick={onRetry}>
        Reintentar
      </Button>
    </div>
  );
}

interface CourseTabEmptyProps {
  onAddVariant: () => void;
  /** Rol parent — oculta las acciones de edición (`ui-course.md` §2:
   * "coach/admin only"), dejando visibles el título y el texto explicativo. */
  readOnly?: boolean;
}

function CourseTabEmpty({ onAddVariant, readOnly }: CourseTabEmptyProps) {
  return (
    <div
      className="rounded-xl bg-white p-6 text-center shadow-card"
      role="status"
      data-testid="course-tab-empty"
    >
      <h2 className="text-sm font-semibold text-charcoal">
        Sin circuito registrado
      </h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-mid-gray">
        Registrar el circuito habilita distancia y velocidad en los
        resultados, y una tarjeta de reconocimiento de la pista para las
        familias.
      </p>
      {!readOnly && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <Button onClick={onAddVariant} data-testid="course-tab-add-variant-btn">
            Agregar variante
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CourseTab({ raceEventId, compact, readOnly }: CourseTabProps) {
  const { data, isLoading, isError, refetch } = useRaceCourse(raceEventId);
  const [emptyStateUploadOpen, setEmptyStateUploadOpen] = useState(false);

  return (
    <div
      className={cn(compact ? "space-y-3" : "space-y-4")}
      data-testid="course-tab"
    >
      {isLoading && <CourseTabSkeleton compact={compact} />}

      {isError && !isLoading && (
        <CourseTabError onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && data && !data.has_course_data && (
        <>
          <CourseTabEmpty
            onAddVariant={() => setEmptyStateUploadOpen(true)}
            readOnly={readOnly}
          />
          {!readOnly && (
            <VariantUploadDialog
              raceEventId={raceEventId}
              open={emptyStateUploadOpen}
              onOpenChange={setEmptyStateUploadOpen}
              defaultLabel="Circuito completo"
            />
          )}
        </>
      )}

      {!isLoading && !isError && data && data.has_course_data && (
        <>
          <VariantsCard
            raceEventId={raceEventId}
            variants={data.variants}
            readOnly={readOnly}
          />
          <CategorySetupTable
            raceEventId={raceEventId}
            setups={data.setups}
            suggestedSetups={data.suggested_setups}
            variants={data.variants}
          />
        </>
      )}

      {!isLoading && !isError && data && (
        <CourseDescriptionCard
          raceEventId={raceEventId}
          description={data.description}
          readOnly={readOnly}
        />
      )}
      {/* CourseSummary — T058 */}
    </div>
  );
}
