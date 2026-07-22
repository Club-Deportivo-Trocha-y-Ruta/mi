/**
 * PlanSection — sección "Plan" de una sesión de entrenamiento (feature 032,
 * US1, T021/T022): un único lugar para técnica + fuerza + intervalos, en vez
 * de los dos bloques separados y apilados que existían antes en
 * `SessionDetailPage.tsx` ("Bloques de fuerza" y "Estructura de intervalos").
 *
 * Contenido:
 *   - Técnica: `TechniqueAttachPicker` (T015) — siempre inline, la sesión ya
 *     existe y nunca se crea una desde acá.
 *   - Fuerza: la lista de bloques ya adjuntos a esta sesión (con "Quitar de
 *     la sesión", relocada tal cual desde `SessionDetailPage.tsx`) +
 *     `StrengthBlockPicker` (T016) para adjuntar un bloque existente del club
 *     + el link "Armar bloque de fuerza" (T020) que ahora preselecciona esta
 *     sesión vía `?session_id=`.
 *   - Intervalos: bloque sin cambios de lógica, relocado tal cual desde
 *     `SessionDetailPage.tsx:855-1037` (StructureEditor/TemplatePicker,
 *     `AgeGateDialog` sigue disparándose exactamente igual — SC-007) + los
 *     `StructureMatchLink`s de plan-vs-real.
 *
 * Empty state combinado (FR-005, contracts/session-sections.md): mientras
 * NINGÚN tipo tiene contenido todavía, se muestra un solo `EmptyState` con
 * las tres acciones de adjuntar juntas, en vez de tres bloques vacíos por
 * separado. En cuanto un tipo tiene contenido (o el coach ya reveló uno),
 * cada tipo vacío restante muestra su propio prompt inline más chico en vez
 * del picker completo (mirror de la copia vacía que ya existía para fuerza,
 * "Sin bloques de fuerza adjuntos a esta sesión.").
 */
import * as React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ClipboardList,
  Dumbbell,
  ListTree,
  Plus,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { InstructivoDownloadButton } from "@/components/intervals/InstructivoDownloadButton";
import { INTERVAL_AGE_BAND_LABEL } from "@/components/intervals/AgeGateDialog";
import { BLOCK_TYPE_LABEL, HR_ZONE_LABEL } from "@/components/intervals/BlockRow";
import { extractIntervalValidationError, mapIntervalError } from "@/api/intervals";
import { useSessionExercises } from "@/hooks/technique/useTechnique";
import { useDetachBlock, useSessionBlocks } from "@/hooks/strength/useStrength";
import {
  useDeleteStructure,
  useSaveStructure,
  useSaveTemplate,
  useSessionMatch,
  useSessionStructure,
} from "@/hooks/intervals/useIntervals";
import { TechniqueAttachPicker } from "./TechniqueAttachPicker";
import { StrengthBlockPicker } from "./StrengthBlockPicker";
import type { StructureEditorSubmitInput } from "@/components/intervals/StructureEditor";
import type { ActivityOut } from "@/types/strava.types";
import type {
  IntervalBlockInput,
  IntervalStructureOut,
  IntervalTemplateSaveInput,
} from "@/types/intervals.types";

const StructureEditor = React.lazy(() =>
  import("@/components/intervals/StructureEditor").then((m) => ({
    default: m.StructureEditor,
  })),
);

const TemplatePicker = React.lazy(() =>
  import("@/components/intervals/TemplatePicker").then((m) => ({
    default: m.TemplatePicker,
  })),
);

const sectionHeading = "text-sm font-semibold uppercase tracking-wide text-mid-gray mb-3";

// ---------------------------------------------------------------------------
// Vocabulario controlado para "Guardar como plantilla" (mismo set que
// `TemplatePicker`, data-model.md §3) — relocado tal cual.
// ---------------------------------------------------------------------------

const MESOCYCLE_PHASE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "base", label: "Base" },
  { value: "construccion", label: "Construcción" },
  { value: "especifico", label: "Específico" },
  { value: "taper", label: "Afinamiento (taper)" },
  { value: "transicion", label: "Transición" },
];

const COMPETITION_PROXIMITY_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "general", label: "General" },
  { value: "pre-competencia", label: "Pre-competencia" },
  { value: "semana-carrera", label: "Semana de carrera" },
];

/** Segundos → "m:ss" (misma regla de formato que `StructureEditor`). */
function formatDurationMmSs(totalSeconds: number): string {
  const safe = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Bloques de una `IntervalStructureOut` → payload de bloques (sin `id`) para
 * un template. Se reutiliza tanto para "Guardar como plantilla" (US4) como
 * para hidratar el editor en modo edición — en ambos casos `duration_type`
 * (feature 034) se preserva verbatim, igual que el resto de los campos
 * (copy-on-attach / round-trip de edición no deben perder si un bloque es
 * libre u su duración fija).
 */
function toTemplateBlocks(
  blocks: IntervalStructureOut["blocks"],
): IntervalBlockInput[] {
  return blocks.map((block) => ({
    position: block.position,
    block_type: block.block_type,
    duration_type: block.duration_type,
    duration_s: block.duration_s,
    target_zone: block.target_zone,
    target_cadence_rpm: block.target_cadence_rpm,
    repeat_group: block.repeat_group,
    repeat_count: block.repeat_count,
  }));
}

/**
 * Enlace a la comparación plan-vs-real de una actividad enlazada. Solo se
 * renderiza cuando el cálculo ya terminó (`status === "computed"`) — mientras
 * está `computing`/`failed`/`no_activity` no muestra nada.
 */
function StructureMatchLink({
  sessionId,
  activityId,
  athleteLabel,
}: {
  sessionId: number;
  activityId: number;
  athleteLabel: string;
}) {
  const matchQuery = useSessionMatch(sessionId, activityId);
  if (matchQuery.data?.status !== "computed") return null;
  return (
    <Link
      to={`/training/sessions/${sessionId}/activity-match/${activityId}`}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
    >
      Ver comparación plan vs. real — {athleteLabel}
      <ArrowRight size={14} aria-hidden="true" />
    </Link>
  );
}

/** Diálogo "Guardar como plantilla" — relocado tal cual desde `SessionDetailPage.tsx`. */
function SaveStructureAsTemplateDialog({
  structure,
  isPending,
  errorMessage,
  onClose,
  onSave,
}: {
  structure: IntervalStructureOut;
  isPending: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSave: (input: IntervalTemplateSaveInput) => void;
}) {
  const [name, setName] = React.useState("");
  const [mesocyclePhase, setMesocyclePhase] = React.useState("base");
  const [competitionProximity, setCompetitionProximity] = React.useState("general");
  const [nameError, setNameError] = React.useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError("El nombre es obligatorio.");
      return;
    }
    setNameError(null);
    onSave({
      name: name.trim(),
      target_age_band: structure.target_age_band,
      mesocycle_phase: mesocyclePhase,
      competition_proximity: competitionProximity,
      blocks: toTemplateBlocks(structure.blocks),
    });
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !isPending) onClose();
      }}
    >
      <DialogContent className="w-full max-w-md" aria-label="Guardar como plantilla">
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Guardar como plantilla</DialogTitle>
            <DialogDescription>
              Se guarda una copia reutilizable de esta estructura en la
              biblioteca de templates del club. Editar o borrar esta sesión más
              adelante no afecta al template.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-3">
            <div>
              <label
                htmlFor="tpl-name"
                className="mb-1 block text-xs font-medium text-charcoal"
              >
                Nombre del template
              </label>
              <input
                id="tpl-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
                disabled={isPending}
                className="min-h-12 w-full rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
              />
              {nameError && (
                <p role="alert" className="mt-1 text-xs text-red-600">
                  {nameError}
                </p>
              )}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="tpl-phase"
                  className="mb-1 block text-xs font-medium text-charcoal"
                >
                  Fase de mesociclo
                </label>
                <select
                  id="tpl-phase"
                  value={mesocyclePhase}
                  onChange={(e) => setMesocyclePhase(e.target.value)}
                  disabled={isPending}
                  className="min-h-12 w-full rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
                >
                  {MESOCYCLE_PHASE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="tpl-proximity"
                  className="mb-1 block text-xs font-medium text-charcoal"
                >
                  Proximidad a competencia
                </label>
                <select
                  id="tpl-proximity"
                  value={competitionProximity}
                  onChange={(e) => setCompetitionProximity(e.target.value)}
                  disabled={isPending}
                  className="min-h-12 w-full rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
                >
                  {COMPETITION_PROXIMITY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {errorMessage && (
              <p role="alert" className="text-sm text-red-600">
                {errorMessage}
              </p>
            )}
          </DialogBody>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isPending}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Guardando…" : "Guardar plantilla"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PlanSectionProps {
  sessionId: number;
  /** Fecha de la sesión (`YYYY-MM-DD`), para `InstructivoDownloadButton`. */
  sessionDate: string;
  isCancelled: boolean;
  /** Actividades Strava ya enlazadas a esta sesión, para los links plan-vs-real. */
  activities: ActivityOut[];
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function PlanSection({
  sessionId,
  sessionDate,
  isCancelled,
  activities,
}: PlanSectionProps): React.ReactElement {
  const [revealedTechnique, setRevealedTechnique] = React.useState(false);
  const [revealedStrength, setRevealedStrength] = React.useState(false);

  // Estructura de intervalos (feature 026) — estado relocado tal cual.
  const [structureMode, setStructureMode] = React.useState<"view" | "create" | "edit">(
    "view",
  );
  const [saveStructureError, setSaveStructureError] = React.useState<string | null>(
    null,
  );
  const [showDeleteStructureModal, setShowDeleteStructureModal] =
    React.useState(false);
  const [showSaveTemplateModal, setShowSaveTemplateModal] = React.useState(false);

  const sessionExercisesQuery = useSessionExercises(sessionId);
  const strengthBlocksQuery = useSessionBlocks(sessionId, !!sessionId);
  const detachBlockMutation = useDetachBlock();
  const structureQuery = useSessionStructure(sessionId, !!sessionId);
  const saveStructureMutation = useSaveStructure();
  const deleteStructureMutation = useDeleteStructure();
  const saveTemplateMutation = useSaveTemplate();

  const handleStructureSubmit = React.useCallback(
    async (input: StructureEditorSubmitInput) => {
      setSaveStructureError(null);
      try {
        if (structureQuery.data) {
          const { training_session_id: _omit, ...updateInput } = input;
          await saveStructureMutation.mutateAsync({
            mode: "update",
            id: structureQuery.data.id,
            input: updateInput,
          });
        } else {
          await saveStructureMutation.mutateAsync({ mode: "create", input });
        }
        setStructureMode("view");
      } catch (err) {
        if (!extractIntervalValidationError(err)) {
          setSaveStructureError(mapIntervalError(err).message);
        }
        throw err;
      }
    },
    [structureQuery.data, saveStructureMutation],
  );

  const handleDeleteStructure = React.useCallback(() => {
    if (!structureQuery.data) return;
    deleteStructureMutation.mutate(
      { structureId: structureQuery.data.id, trainingSessionId: sessionId },
      { onSuccess: () => setShowDeleteStructureModal(false) },
    );
  }, [deleteStructureMutation, sessionId, structureQuery.data]);

  const handleSaveAsTemplate = React.useCallback(
    (input: IntervalTemplateSaveInput) => {
      saveTemplateMutation.mutate(
        { input },
        { onSuccess: () => setShowSaveTemplateModal(false) },
      );
    },
    [saveTemplateMutation],
  );

  const visibleTechniqueCount = (sessionExercisesQuery.data ?? []).filter(
    (item) => !item.is_hidden,
  ).length;
  const hasTechnique = visibleTechniqueCount > 0;
  const hasStrength = (strengthBlocksQuery.data?.items.length ?? 0) > 0;
  const hasIntervals = !!structureQuery.data;

  const stillLoading =
    sessionExercisesQuery.isLoading ||
    strengthBlocksQuery.isLoading ||
    structureQuery.isLoading;

  const showCombinedEmptyState =
    !stillLoading &&
    !hasTechnique &&
    !revealedTechnique &&
    !hasStrength &&
    !revealedStrength &&
    !hasIntervals &&
    structureMode === "view";

  const techniqueExpanded = hasTechnique || revealedTechnique;
  const strengthExpanded = hasStrength || revealedStrength;

  return (
    <div className="space-y-5">
      {showCombinedEmptyState ? (
        <EmptyState
          icon={ClipboardList}
          title="Esta sesión todavía no tiene contenido"
          description="Agregá ejercicios de técnica, un bloque de fuerza o una estructura de intervalos."
          action={
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button
                type="button"
                onClick={() => setRevealedTechnique(true)}
                className="min-h-12 gap-2"
              >
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                Agregar ejercicios de técnica
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setRevealedStrength(true)}
                className="min-h-12 gap-2"
              >
                <Dumbbell className="h-4 w-4" aria-hidden="true" />
                Agregar bloque de fuerza
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setStructureMode("create")}
                className="min-h-12 gap-2"
              >
                <ListTree className="h-4 w-4" aria-hidden="true" />
                Crear estructura de intervalos
              </Button>
            </div>
          }
        />
      ) : (
        <>
          {/* Técnica (feature 018 catálogo, feature 032 adjunto inline) */}
          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            <h2 className={sectionHeading}>Ejercicios de técnica</h2>
            {techniqueExpanded ? (
              <TechniqueAttachPicker sessionId={sessionId} />
            ) : (
              <>
                <p className="text-sm text-mid-gray">
                  Sin ejercicios de técnica en esta sesión.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setRevealedTechnique(true)}
                  className="min-h-12 gap-2"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Agregar ejercicios de técnica
                </Button>
              </>
            )}
          </div>

          {/* Bloques de fuerza (feature 021, FR-012/FR-013 + feature 032 adjunto) */}
          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            <div className="flex items-center justify-between">
              <h2 className={sectionHeading} style={{ marginBottom: 0 }}>
                Bloques de fuerza
              </h2>
              <Link
                to={`/strength/blocks/new?session_id=${sessionId}`}
                className="text-sm font-medium text-charcoal underline hover:opacity-70"
              >
                Armar bloque de fuerza
              </Link>
            </div>

            {strengthBlocksQuery.isLoading && (
              <div className="h-16 animate-pulse rounded-lg bg-light-gray" />
            )}

            {strengthBlocksQuery.isError && (
              <p className="text-sm text-red-600" role="alert">
                No se pudieron cargar los bloques de fuerza de esta sesión.
              </p>
            )}

            {!strengthBlocksQuery.isLoading &&
              !strengthBlocksQuery.isError &&
              (strengthBlocksQuery.data?.items.length ?? 0) === 0 && (
                <p className="text-sm text-mid-gray">
                  Sin bloques de fuerza adjuntos a esta sesión.
                </p>
              )}

            {(strengthBlocksQuery.data?.items.length ?? 0) > 0 && (
              <ul className="space-y-3" data-testid="session-strength-blocks">
                {strengthBlocksQuery.data?.items.map((block) => (
                  <li
                    key={block.id}
                    className="rounded-lg px-4 py-3 shadow-ring"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <Link
                          to={`/strength/blocks/${block.id}`}
                          className="text-sm font-semibold text-charcoal hover:underline"
                        >
                          {block.name}
                        </Link>
                        <p className="mt-0.5 text-xs text-mid-gray">
                          {block.target_age_band} años · {block.total_duration_min} min ·{" "}
                          {block.entries.length}{" "}
                          {block.entries.length === 1 ? "ejercicio" : "ejercicios"}
                        </p>
                      </div>
                      {!isCancelled && (
                        <button
                          type="button"
                          onClick={() =>
                            detachBlockMutation.mutate({
                              blockId: block.id,
                              trainingSessionId: sessionId,
                            })
                          }
                          disabled={detachBlockMutation.isPending}
                          className="text-xs font-medium text-red-700 transition-opacity hover:opacity-70 disabled:opacity-50"
                        >
                          Quitar de la sesión
                        </button>
                      )}
                    </div>
                    <ul className="mt-2 space-y-1">
                      {block.entries.map((entry) => (
                        <li key={entry.id} className="text-xs text-mid-gray">
                          {entry.exercise.name} — {entry.duration_min} min
                          {entry.reps ? ` · ${entry.reps}` : ""}
                          {entry.is_age_override && (
                            <span className="ml-1 text-amber-700">(excepción de edad)</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}

            {strengthExpanded ? (
              <div className="pt-1">
                <p className="mb-2 text-xs text-mid-gray">
                  O elegí un bloque existente de la biblioteca del club:
                </p>
                <StrengthBlockPicker trainingSessionId={sessionId} />
              </div>
            ) : (
              <Button
                type="button"
                variant="outline"
                onClick={() => setRevealedStrength(true)}
                className="min-h-12 gap-2"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Agregar bloque de fuerza
              </Button>
            )}
          </div>

          {/* Estructura de intervalos (feature 026) — sin cambios de lógica */}
          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            {structureQuery.isLoading ? (
              <>
                <h2 className={sectionHeading}>Estructura de intervalos</h2>
                <div className="h-16 animate-pulse rounded-lg bg-light-gray" />
              </>
            ) : structureMode === "create" || structureMode === "edit" ? (
              <>
                <div className="flex items-center justify-between">
                  <h2 className={sectionHeading} style={{ marginBottom: 0 }}>
                    {structureMode === "edit"
                      ? "Editar estructura de intervalos"
                      : "Crear estructura de intervalos"}
                  </h2>
                  <button
                    type="button"
                    onClick={() => {
                      setStructureMode("view");
                      setSaveStructureError(null);
                    }}
                    className="text-sm font-medium text-charcoal underline hover:opacity-70"
                  >
                    Cancelar
                  </button>
                </div>
                <React.Suspense
                  fallback={
                    <div className="h-64 animate-pulse rounded-xl bg-light-gray" />
                  }
                >
                  <StructureEditor
                    trainingSessionId={sessionId}
                    onSubmit={handleStructureSubmit}
                    isPending={saveStructureMutation.isPending}
                    errorMessage={saveStructureError}
                    defaultValues={
                      structureMode === "edit" && structureQuery.data
                        ? {
                            target_age_band: structureQuery.data.target_age_band,
                            blocks: toTemplateBlocks(structureQuery.data.blocks),
                          }
                        : undefined
                    }
                    submitLabel={
                      structureMode === "edit"
                        ? "Guardar cambios"
                        : "Crear estructura"
                    }
                  />
                </React.Suspense>
              </>
            ) : structureQuery.data ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className={sectionHeading} style={{ marginBottom: 0 }}>
                    Estructura de intervalos
                  </h2>
                  {!isCancelled && (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setStructureMode("edit")}
                        className="text-sm font-medium text-charcoal underline hover:opacity-70"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowSaveTemplateModal(true)}
                        className="text-sm font-medium text-charcoal underline hover:opacity-70"
                      >
                        Guardar como plantilla
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowDeleteStructureModal(true)}
                        className="text-sm font-medium text-red-700 underline hover:opacity-70"
                      >
                        Eliminar
                      </button>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-mid-gray">
                  <span>{INTERVAL_AGE_BAND_LABEL[structureQuery.data.target_age_band]}</span>
                  <span aria-hidden="true">·</span>
                  <span>
                    Duración total:{" "}
                    {formatDurationMmSs(structureQuery.data.total_planned_duration_s)} min
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>
                    {structureQuery.data.blocks.length}{" "}
                    {structureQuery.data.blocks.length === 1 ? "bloque" : "bloques"}
                  </span>
                </div>

                <ol className="space-y-1.5" aria-label="Bloques de la estructura">
                  {structureQuery.data.blocks.map((block) => (
                    <li
                      key={block.id}
                      className="flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm text-charcoal shadow-ring"
                    >
                      <span className="font-medium">
                        {BLOCK_TYPE_LABEL[block.block_type]}
                      </span>
                      <span className="text-mid-gray">
                        {block.duration_type === "open_lap"
                          ? "Libre — hasta botón de vuelta"
                          : formatDurationMmSs(block.duration_s ?? 0)}
                      </span>
                      <span className="text-mid-gray">
                        {HR_ZONE_LABEL[block.target_zone]}
                      </span>
                      <span className="text-mid-gray">
                        {block.target_cadence_rpm} rpm
                      </span>
                      {block.repeat_group != null && block.repeat_count != null && (
                        <Badge variant="secondary" className="text-xs">
                          ×{block.repeat_count}
                        </Badge>
                      )}
                    </li>
                  ))}
                </ol>

                <InstructivoDownloadButton
                  trainingSessionId={sessionId}
                  hasStructure
                  sessionDate={sessionDate}
                />

                {activities.length > 0 && (
                  <div className="flex flex-wrap gap-3">
                    {activities.map((activity) => (
                      <StructureMatchLink
                        key={activity.id}
                        sessionId={sessionId}
                        activityId={activity.id}
                        athleteLabel={activity.athlete_name}
                      />
                    ))}
                  </div>
                )}
              </>
            ) : (
              <>
                <h2 className={sectionHeading}>Estructura de intervalos</h2>
                <p className="text-sm text-mid-gray">
                  Esta sesión todavía no tiene una estructura de intervalos.
                </p>
                {!isCancelled && (
                  <>
                    <div>
                      <button
                        type="button"
                        onClick={() => setStructureMode("create")}
                        className="min-h-12 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                      >
                        Crear estructura
                      </button>
                    </div>
                    <div>
                      <p className="mb-2 text-xs text-mid-gray">
                        O elegí un template desde la biblioteca del club:
                      </p>
                      <React.Suspense
                        fallback={
                          <div className="h-24 animate-pulse rounded-xl bg-light-gray" />
                        }
                      >
                        <TemplatePicker
                          trainingSessionId={sessionId}
                          onAttached={() => setStructureMode("view")}
                        />
                      </React.Suspense>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </>
      )}

      {showDeleteStructureModal && structureQuery.data && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open && !deleteStructureMutation.isPending) {
              setShowDeleteStructureModal(false);
            }
          }}
        >
          <DialogContent
            className="w-full max-w-md"
            aria-label="Eliminar estructura de intervalos"
          >
            <DialogHeader>
              <DialogTitle>Eliminar estructura de intervalos</DialogTitle>
              <DialogDescription>
                Esta acción elimina la estructura y sus comparaciones plan vs.
                real. Las vueltas de Strava ya guardadas no se eliminan.
              </DialogDescription>
            </DialogHeader>
            {deleteStructureMutation.isError && (
              <DialogBody className="pt-0">
                <p role="alert" className="text-sm text-red-600">
                  No se pudo eliminar la estructura. Intentá de nuevo.
                </p>
              </DialogBody>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowDeleteStructureModal(false)}
                disabled={deleteStructureMutation.isPending}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                onClick={handleDeleteStructure}
                disabled={deleteStructureMutation.isPending}
                className="bg-red-600 text-white hover:bg-red-700"
              >
                {deleteStructureMutation.isPending
                  ? "Eliminando…"
                  : "Eliminar estructura"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {showSaveTemplateModal && structureQuery.data && (
        <SaveStructureAsTemplateDialog
          structure={structureQuery.data}
          isPending={saveTemplateMutation.isPending}
          errorMessage={
            saveTemplateMutation.isError
              ? mapIntervalError(saveTemplateMutation.error).message
              : null
          }
          onClose={() => setShowSaveTemplateModal(false)}
          onSave={handleSaveAsTemplate}
        />
      )}
    </div>
  );
}

export default PlanSection;
