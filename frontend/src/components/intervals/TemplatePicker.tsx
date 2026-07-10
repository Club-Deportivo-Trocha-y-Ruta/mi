/**
 * TemplatePicker — biblioteca navegable de templates de intervalos (feature 026,
 * US4). Permite explorar y filtrar templates por las tres etiquetas (categoría
 * de edad / fase de mesociclo / proximidad a competencia) y, opcionalmente,
 * adjuntar (clonar) un template a una sesión.
 *
 * Modos de uso:
 *   - Biblioteca (sin `trainingSessionId`): solo navegación + filtrado. Es el
 *     modo que consume `routes/intervals/TemplateLibraryPage.tsx`.
 *   - Adjunto (con `trainingSessionId`): cada template muestra un botón
 *     "Adjuntar a la sesión". El adjunto es copy-on-attach — clona los bloques
 *     en una nueva estructura de la sesión (no queda ningún vínculo).
 *
 * Compuerta por edad (reusa `AgeGateDialog`): el backend revalida al adjuntar
 * contra la banda del template. Si responde 422:
 *   - `age_gate_confirmation_required` → diálogo modo "confirmation"; al
 *     confirmar se reenvía el adjunto con `age_gate_confirmed: true`.
 *   - `age_gate_z3_blocked` → diálogo modo "blocked" (sin anulación).
 *
 * RBAC: todo `/api/intervals` es coach/admin; el backend responde 403 a
 * padres/atletas. Este componente se renderiza solo dentro de vistas de coach.
 *
 * Privacidad (Ley 1581): los templates no contienen datos de atletas ni GPS.
 */
import * as React from "react";
import { AlertCircle, Loader2, Plus } from "lucide-react";

import {
  extractAgeGateError,
  extractIntervalValidationError,
  mapIntervalError,
} from "@/api/intervals";
import { AgeGateDialog, type AgeGateMode } from "@/components/intervals/AgeGateDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttachTemplate, useTemplates } from "@/hooks/intervals/useIntervals";
import { cn } from "@/lib/utils";
import type {
  IntervalAgeBand,
  IntervalStructureOut,
  IntervalTemplateFilters,
  IntervalTemplateOut,
} from "@/types/intervals.types";

// ---------------------------------------------------------------------------
// Etiquetas y vocabulario controlado (español neutro — Colombia)
// ---------------------------------------------------------------------------

const AGE_BAND_LABEL: Record<IntervalAgeBand, string> = {
  "10-12": "10 a 12 años",
  "13-15": "13 a 15 años",
};

const AGE_BAND_OPTIONS: ReadonlyArray<{ value: IntervalAgeBand; label: string }> = [
  { value: "10-12", label: AGE_BAND_LABEL["10-12"] },
  { value: "13-15", label: AGE_BAND_LABEL["13-15"] },
];

/**
 * Vocabulario controlado en frontend (data-model.md §3): la fase de mesociclo se
 * persiste como string libre en el backend para poder evolucionar sin migración,
 * pero la UI ofrece un set curado. Al mostrar, se cae al valor crudo si no está
 * en el mapa (compatibilidad hacia adelante).
 */
const MESOCYCLE_PHASE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "base", label: "Base" },
  { value: "construccion", label: "Construcción" },
  { value: "especifico", label: "Específico" },
  { value: "taper", label: "Afinamiento (taper)" },
  { value: "transicion", label: "Transición" },
];

const COMPETITION_PROXIMITY_OPTIONS: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "general", label: "General" },
  { value: "pre-competencia", label: "Pre-competencia" },
  { value: "semana-carrera", label: "Semana de carrera" },
];

function labelFor(
  options: ReadonlyArray<{ value: string; label: string }>,
  value: string,
): string {
  return options.find((o) => o.value === value)?.label ?? value;
}

/** Segundos → "X min" (redondeado al minuto). Duración total planeada. */
function formatDurationMin(seconds: number): string {
  const minutes = Math.max(0, Math.round(seconds / 60));
  return `${minutes} min`;
}

// ---------------------------------------------------------------------------
// Estado de filtros (local — no se codifica en la URL, igual que strength)
// ---------------------------------------------------------------------------

interface FilterFormValues {
  age_band: string;
  mesocycle_phase: string;
  competition_proximity: string;
  include_archived: boolean;
}

const EMPTY_FILTERS: FilterFormValues = {
  age_band: "",
  mesocycle_phase: "",
  competition_proximity: "",
  include_archived: false,
};

function toApiFilters(values: FilterFormValues): IntervalTemplateFilters {
  const filters: IntervalTemplateFilters = {};
  if (values.age_band) filters.age_band = values.age_band as IntervalAgeBand;
  if (values.mesocycle_phase) filters.mesocycle_phase = values.mesocycle_phase;
  if (values.competition_proximity)
    filters.competition_proximity = values.competition_proximity;
  if (values.include_archived) filters.include_archived = true;
  return filters;
}

// ---------------------------------------------------------------------------
// Estado del diálogo de compuerta por edad
// ---------------------------------------------------------------------------

interface AgeGateState {
  open: boolean;
  mode: AgeGateMode;
  templateId: number;
  targetAgeBand: IntervalAgeBand;
  message?: string;
  positions?: number[];
}

const AGE_GATE_CLOSED: AgeGateState = {
  open: false,
  mode: "confirmation",
  templateId: 0,
  targetAgeBand: "13-15",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TemplatePickerProps {
  /**
   * Sesión a la que se adjuntan los templates. Si se omite, el picker funciona
   * en modo solo-navegación (sin botones de adjuntar) — es como lo usa la
   * biblioteca `/intervals/templates`.
   */
  trainingSessionId?: number;
  /** Llamado con la estructura recién creada tras un adjunto exitoso. */
  onAttached?: (structure: IntervalStructureOut) => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function TemplatePicker({
  trainingSessionId,
  onAttached,
  className,
}: TemplatePickerProps): React.ReactElement {
  const [filters, setFilters] = React.useState<FilterFormValues>(EMPTY_FILTERS);
  const [ageGate, setAgeGate] = React.useState<AgeGateState>(AGE_GATE_CLOSED);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const apiFilters = React.useMemo(() => toApiFilters(filters), [filters]);
  const { data, isLoading, isFetching, isError, error } = useTemplates(apiFilters);
  const attach = useAttachTemplate();

  const canAttach = trainingSessionId != null && trainingSessionId > 0;
  const errorId = React.useId();

  const activeCount = [
    filters.age_band,
    filters.mesocycle_phase,
    filters.competition_proximity,
    filters.include_archived ? "1" : "",
  ].filter(Boolean).length;

  const handleFilterChange = React.useCallback(
    <K extends keyof FilterFormValues>(key: K, value: FilterFormValues[K]) => {
      setFilters((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const handleClear = React.useCallback(() => {
    setFilters(EMPTY_FILTERS);
  }, []);

  /**
   * Ejecuta el adjunto. Se reutiliza para el intento inicial (confirmed=false)
   * y para el reintento tras confirmar la compuerta por edad (confirmed=true).
   */
  const runAttach = React.useCallback(
    (template: IntervalTemplateOut, ageGateConfirmed: boolean) => {
      if (!canAttach || trainingSessionId == null) return;
      setErrorMessage(null);
      attach.mutate(
        {
          templateId: template.id,
          input: {
            training_session_id: trainingSessionId,
            age_gate_confirmed: ageGateConfirmed,
          },
        },
        {
          onSuccess: (structure) => {
            setAgeGate(AGE_GATE_CLOSED);
            onAttached?.(structure);
          },
          onError: (err) => {
            // Compuerta confirmable (FR-007) → abre diálogo modo "confirmation".
            const gate = extractAgeGateError(err);
            if (gate) {
              setAgeGate({
                open: true,
                mode: "confirmation",
                templateId: template.id,
                targetAgeBand: template.target_age_band,
                message: gate.message,
              });
              return;
            }
            // Bloqueo duro Z3+ (FR-006) → diálogo modo "blocked".
            const validation = extractIntervalValidationError(err);
            if (validation?.code === "age_gate_z3_blocked") {
              setAgeGate({
                open: true,
                mode: "blocked",
                templateId: template.id,
                targetAgeBand: template.target_age_band,
                message: validation.message,
                positions: validation.positions,
              });
              return;
            }
            // Cualquier otro error (409 estructura existente, 403, red, etc.).
            setAgeGate(AGE_GATE_CLOSED);
            setErrorMessage(mapIntervalError(err).message);
          },
        },
      );
    },
    [attach, canAttach, onAttached, trainingSessionId],
  );

  const handleConfirmAgeGate = React.useCallback(() => {
    const template = data?.items.find((t) => t.id === ageGate.templateId);
    if (template) runAttach(template, true);
  }, [ageGate.templateId, data?.items, runAttach]);

  const attachingTemplateId =
    attach.isPending && attach.variables ? attach.variables.templateId : null;

  return (
    <div className={cn("space-y-5", className)}>
      {/* --- Filtros --- */}
      <section
        aria-label="Filtros de la biblioteca de intervalos"
        className="rounded-xl border border-slate-200 bg-white p-4"
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* Categoría de edad */}
          <div>
            <label
              htmlFor="tpl-filter-age"
              className="mb-1 block text-xs font-medium text-slate-700"
            >
              Categoría de edad
            </label>
            <select
              id="tpl-filter-age"
              value={filters.age_band}
              onChange={(e) => handleFilterChange("age_band", e.target.value)}
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Todas las categorías</option>
              {AGE_BAND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* Fase de mesociclo */}
          <div>
            <label
              htmlFor="tpl-filter-phase"
              className="mb-1 block text-xs font-medium text-slate-700"
            >
              Fase de mesociclo
            </label>
            <select
              id="tpl-filter-phase"
              value={filters.mesocycle_phase}
              onChange={(e) =>
                handleFilterChange("mesocycle_phase", e.target.value)
              }
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Todas las fases</option>
              {MESOCYCLE_PHASE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* Proximidad a competencia */}
          <div>
            <label
              htmlFor="tpl-filter-proximity"
              className="mb-1 block text-xs font-medium text-slate-700"
            >
              Proximidad a competencia
            </label>
            <select
              id="tpl-filter-proximity"
              value={filters.competition_proximity}
              onChange={(e) =>
                handleFilterChange("competition_proximity", e.target.value)
              }
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Todas las proximidades</option>
              {COMPETITION_PROXIMITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700">
            <input
              type="checkbox"
              checked={filters.include_archived}
              onChange={(e) =>
                handleFilterChange("include_archived", e.target.checked)
              }
              className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-2 focus:ring-primary"
            />
            Incluir archivados
          </label>

          {activeCount > 0 && (
            <>
              <button
                type="button"
                onClick={handleClear}
                className="min-h-9 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-slate-400 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary"
              >
                Limpiar filtros
              </button>
              <Badge variant="secondary" className="text-xs">
                {activeCount}{" "}
                {activeCount === 1 ? "filtro activo" : "filtros activos"}
              </Badge>
            </>
          )}
        </div>
      </section>

      {/* --- Error de adjunto (global) --- */}
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

      {/* --- Resultados --- */}
      <TemplateResults
        items={data?.items}
        total={data?.total}
        isLoading={isLoading}
        isFetching={isFetching}
        isError={isError}
        error={error}
        hasActiveFilters={activeCount > 0}
        canAttach={canAttach}
        attachingTemplateId={attachingTemplateId}
        onAttach={(template) => runAttach(template, false)}
      />

      {/* --- Compuerta por edad --- */}
      <AgeGateDialog
        open={ageGate.open}
        onOpenChange={(open) =>
          setAgeGate((prev) => ({ ...prev, open }))
        }
        mode={ageGate.mode}
        targetAgeBand={ageGate.targetAgeBand}
        message={ageGate.message}
        positions={ageGate.positions}
        onConfirm={handleConfirmAgeGate}
        isPending={attach.isPending}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Resultados — estados loading / error / empty / grid
// ---------------------------------------------------------------------------

interface TemplateResultsProps {
  items: IntervalTemplateOut[] | undefined;
  total: number | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  hasActiveFilters: boolean;
  canAttach: boolean;
  attachingTemplateId: number | null;
  onAttach: (template: IntervalTemplateOut) => void;
}

function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    if (
      msg.includes("timeout") ||
      msg.includes("network") ||
      msg.includes("503") ||
      msg.includes("502")
    ) {
      return "El servidor está iniciando, puede tomar hasta 60 segundos. Intentá de nuevo en un momento.";
    }
  }
  return "No se pudo cargar la biblioteca de templates. Intentá de nuevo.";
}

function CardSkeleton(): React.ReactElement {
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-ring-soft">
      <Skeleton className="mb-2 h-4 w-3/4" />
      <div className="mb-3 flex gap-1.5">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

function TemplateResults({
  items,
  total,
  isLoading,
  isFetching,
  isError,
  error,
  hasActiveFilters,
  canAttach,
  attachingTemplateId,
  onAttach,
}: TemplateResultsProps): React.ReactElement {
  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando biblioteca de templates de intervalos…"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-6 text-center"
      >
        <p className="text-sm font-medium text-red-800">
          {resolveErrorMessage(error)}
        </p>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
        {hasActiveFilters ? (
          <>
            <p className="text-sm font-medium text-slate-700">
              Sin templates para estos filtros
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Ajustá o limpiá los filtros para ver más templates.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-slate-700">
              La biblioteca está vacía
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Aún no hay templates de intervalos guardados en el club.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-xs text-slate-400">
        {total !== undefined
          ? `${total} ${total === 1 ? "template" : "templates"}`
          : ""}
        {isFetching && !isLoading ? " · Actualizando…" : ""}
      </p>

      <div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        aria-label={`Biblioteca: ${items.length} templates`}
      >
        {items.map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            canAttach={canAttach}
            isAttaching={attachingTemplateId === template.id}
            attachDisabled={
              attachingTemplateId != null &&
              attachingTemplateId !== template.id
            }
            onAttach={() => onAttach(template)}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tarjeta de template
// ---------------------------------------------------------------------------

interface TemplateCardProps {
  template: IntervalTemplateOut;
  canAttach: boolean;
  isAttaching: boolean;
  attachDisabled: boolean;
  onAttach: () => void;
}

function TemplateCard({
  template,
  canAttach,
  isAttaching,
  attachDisabled,
  onAttach,
}: TemplateCardProps): React.ReactElement {
  const blockCount = template.blocks.length;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{template.name}</CardTitle>
          {template.is_archived && (
            <Badge variant="outline" className="shrink-0 text-xs">
              Archivado
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-3 pb-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary" className="text-xs">
            {AGE_BAND_LABEL[template.target_age_band]}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {labelFor(MESOCYCLE_PHASE_OPTIONS, template.mesocycle_phase)}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {labelFor(
              COMPETITION_PROXIMITY_OPTIONS,
              template.competition_proximity,
            )}
          </Badge>
        </div>

        <p className="text-xs text-slate-500">
          {blockCount} {blockCount === 1 ? "bloque" : "bloques"} ·{" "}
          {formatDurationMin(template.total_planned_duration_s)}
        </p>
      </CardContent>

      {canAttach && (
        <CardFooter className="pt-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onAttach}
            disabled={isAttaching || attachDisabled}
            className="w-full"
          >
            {isAttaching ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            {isAttaching ? "Adjuntando…" : "Adjuntar a la sesión"}
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}

export default TemplatePicker;
