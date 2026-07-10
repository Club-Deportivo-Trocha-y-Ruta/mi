import { lazy, Suspense, useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowRight, ExternalLink, Loader2, Upload } from "lucide-react";

import {
  useCancelTrainingSession,
  useExecuteTrainingSession,
  useSessionAttendance,
  useTrainingSession,
  useUploadRouteFile,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import {
  useDeleteSessionMedia,
  useSessionMedia,
  useUploadSessionMedia,
} from "@/api/sessionMedia";
import { extractIntervalValidationError, mapIntervalError } from "@/api/intervals";
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { AttendanceTable } from "@/components/training/AttendanceTable";
import { MediaUploadZone } from "@/components/training/MediaUploadZone";
import { NotifyParentsDialog } from "@/components/training/NotifyParentsDialog";
import { Skeleton } from "@/components/ui/skeleton";
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
import { InstructivoDownloadButton } from "@/components/intervals/InstructivoDownloadButton";
import { INTERVAL_AGE_BAND_LABEL } from "@/components/intervals/AgeGateDialog";
import { BLOCK_TYPE_LABEL, HR_ZONE_LABEL } from "@/components/intervals/BlockRow";
import type { StructureEditorSubmitInput } from "@/components/intervals/StructureEditor";
import type { SessionMedia } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";
import type {
  IntervalBlockInput,
  IntervalStructureOut,
  IntervalTemplateSaveInput,
} from "@/types/intervals.types";
import { useDetachBlock, useSessionBlocks } from "@/hooks/strength/useStrength";
import {
  useDeleteStructure,
  useSaveStructure,
  useSaveTemplate,
  useSessionMatch,
  useSessionStructure,
} from "@/hooks/intervals/useIntervals";
import { useSessionActivities } from "@/hooks/activities/useSessionActivities";
import { useUnlinkedActivitiesNearDate } from "@/hooks/activities/useUnlinkedActivitiesNearDate";

const StructureEditor = lazy(() =>
  import("@/components/intervals/StructureEditor").then((m) => ({
    default: m.StructureEditor,
  })),
);

const TemplatePicker = lazy(() =>
  import("@/components/intervals/TemplatePicker").then((m) => ({
    default: m.TemplatePicker,
  })),
);

const RouteViewer = lazy(() =>
  import("@/components/training/RouteViewer").then((m) => ({ default: m.RouteViewer })),
);

// Wave 5 perf: MediaGallery se importa lazy también en coach. Si quedara
// estático aquí, el `lazy()` del parent no produce chunk separado
// (Vite emite INEFFECTIVE_DYNAMIC_IMPORT) — el módulo entra al main bundle
// y el parent paga ese peso al cargar /parents/training/sessions/:id
// aunque su lazy import sugiera lo contrario.
const MediaGallery = lazy(() =>
  import("@/components/training/MediaGallery").then((m) => ({ default: m.MediaGallery })),
);

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
}

/**
 * Agrupa actividades por `athlete_id` en un `Map` para lookups puntuales
 * por fila de asistencia (reemplaza `groupActivitiesByAthlete`, que
 * devolvía un array pensado para iterar una sección propia — ya no existe,
 * ver session-detail-redesign.md §3.1).
 */
function groupActivitiesByAthleteId(activities: ActivityOut[]): Map<number, ActivityOut[]> {
  const groups = new Map<number, ActivityOut[]>();
  for (const activity of activities) {
    const existing = groups.get(activity.athlete_id);
    if (existing) {
      existing.push(activity);
    } else {
      groups.set(activity.athlete_id, [activity]);
    }
  }
  return groups;
}

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const sectionHeading = "text-sm font-semibold uppercase tracking-wide text-mid-gray mb-3";

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3" style={cardStyle}>
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-light-gray" style={{ width: `${70 - i * 15}%` }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Estructura de intervalos (feature 026) — helpers
// ---------------------------------------------------------------------------

/** Segundos → "m:ss" (misma regla de formato que `StructureEditor`). */
function formatDurationMmSs(totalSeconds: number): string {
  const safe = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Vocabulario controlado (mismo set curado que `TemplatePicker`, data-model.md
 * §3): se persiste como string libre en el backend, la UI ofrece un set curado.
 */
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

/** Bloques de una `IntervalStructureOut` → payload de bloques (sin `id`) para un template. */
function toTemplateBlocks(
  blocks: IntervalStructureOut["blocks"],
): IntervalBlockInput[] {
  return blocks.map((block) => ({
    position: block.position,
    block_type: block.block_type,
    duration_s: block.duration_s,
    target_zone: block.target_zone,
    target_cadence_rpm: block.target_cadence_rpm,
    repeat_group: block.repeat_group,
    repeat_count: block.repeat_count,
  }));
}

/**
 * Enlace a la comparación plan-vs-real de una actividad enlazada (US2). Solo se
 * renderiza cuando el cálculo ya terminó (`status === "computed"`) — mientras
 * está `computing`/`failed`/`no_activity` no muestra nada (el detalle vive en
 * `ActivityMatchPage`, no acá).
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

/**
 * Diálogo "Guardar como plantilla" (T033, acción integrada acá porque
 * `StructureEditor.tsx` no es propiedad de este archivo — no se reescribe).
 * Clona la estructura actual (banda + bloques aplanados, sin `id`) en un nuevo
 * template del club; editar/borrar la sesión después no afecta al template.
 */
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
  const [name, setName] = useState("");
  const [mesocyclePhase, setMesocyclePhase] = useState("base");
  const [competitionProximity, setCompetitionProximity] = useState("general");
  const [nameError, setNameError] = useState<string | null>(null);

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

export function SessionDetailPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const navigate = useNavigate();

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [coachNotes, setCoachNotes] = useState<string | null>(null);
  const [notesSaving, setNotesSaving] = useState(false);
  const notesDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Estructura de intervalos (feature 026, US1/US2/US3/US4)
  const [structureMode, setStructureMode] = useState<"view" | "create" | "edit">(
    "view",
  );
  const [saveStructureError, setSaveStructureError] = useState<string | null>(
    null,
  );
  const [showDeleteStructureModal, setShowDeleteStructureModal] =
    useState(false);
  const [showSaveTemplateModal, setShowSaveTemplateModal] = useState(false);

  const sessionQuery = useTrainingSession(sessionId);
  const attendanceQuery = useSessionAttendance(sessionId, !!sessionId);
  const executeMutation = useExecuteTrainingSession();
  const cancelMutation = useCancelTrainingSession();
  const uploadMutation = useUploadRouteFile(sessionId);
  const updateMutation = useUpdateTrainingSession();
  const mediaQuery = useSessionMedia(sessionId, !!sessionId);
  const mediaUploadMutation = useUploadSessionMedia(sessionId);
  const mediaDeleteMutation = useDeleteSessionMedia(sessionId);
  const strengthBlocksQuery = useSessionBlocks(sessionId, !!sessionId);
  const detachBlockMutation = useDetachBlock();
  const sessionActivitiesQuery = useSessionActivities(sessionId, !!sessionId);
  const structureQuery = useSessionStructure(sessionId, !!sessionId);
  const saveStructureMutation = useSaveStructure();
  const deleteStructureMutation = useDeleteStructure();
  const saveTemplateMutation = useSaveTemplate();
  // Referencia `sessionQuery.data` directo (no `session`, definido más abajo
  // después de los early-return de loading/error) para respetar las reglas
  // de hooks — este hook se llama siempre, en el mismo orden, sin importar
  // en qué estado esté la carga de la sesión.
  const unlinkedActivitiesQuery = useUnlinkedActivitiesNearDate(
    sessionQuery.data?.scheduled_date,
    sessionQuery.data?.status !== "cancelled",
  );

  const session = sessionQuery.data;

  const handleNotesChange = useCallback(
    (val: string) => {
      setCoachNotes(val);
      if (notesDebounce.current) clearTimeout(notesDebounce.current);
      notesDebounce.current = setTimeout(() => {
        setNotesSaving(true);
        updateMutation.mutate(
          { id: sessionId, payload: { coach_notes: val } },
          { onSettled: () => setNotesSaving(false) },
        );
      }, 800);
    },
    [sessionId, updateMutation],
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      uploadMutation.mutate(file);
      e.target.value = "";
    },
    [uploadMutation],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) uploadMutation.mutate(file);
    },
    [uploadMutation],
  );

  const handleCancelConfirm = useCallback(
    (notify: boolean, reason?: string) => {
      cancelMutation.mutate(
        { id: sessionId, notify, reason },
        {
          onSuccess: () => {
            setShowCancelModal(false);
            navigate("/training/sessions");
          },
        },
      );
    },
    [cancelMutation, sessionId, navigate],
  );

  /**
   * Envío del `StructureEditor` (create/edit unificados). Si rechaza con un
   * 422 que NO sea una compuerta por edad, guarda el mensaje genérico acá; en
   * cualquier caso vuelve a lanzar para que `StructureEditor` inspeccione el
   * error y abra `AgeGateDialog` cuando corresponda (el componente no se
   * reescribe, solo se le entrega la promesa que puede rechazar).
   */
  const handleStructureSubmit = useCallback(
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

  const handleDeleteStructure = useCallback(() => {
    if (!structureQuery.data) return;
    deleteStructureMutation.mutate(
      { structureId: structureQuery.data.id, trainingSessionId: sessionId },
      { onSuccess: () => setShowDeleteStructureModal(false) },
    );
  }, [deleteStructureMutation, sessionId, structureQuery.data]);

  const handleSaveAsTemplate = useCallback(
    (input: IntervalTemplateSaveInput) => {
      saveTemplateMutation.mutate(
        { input },
        { onSuccess: () => setShowSaveTemplateModal(false) },
      );
    },
    [saveTemplateMutation],
  );

  if (sessionQuery.isLoading) {
    return (
      <section className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </section>
    );
  }

  if (sessionQuery.isError || !session) {
    return (
      <section className="space-y-4">
        <div className="rounded-xl bg-white p-8 text-center" style={cardStyle}>
          <p className="text-base font-medium text-charcoal">Sesión no encontrada</p>
          <p className="mt-1 text-sm text-mid-gray">
            La sesión solicitada no existe o no tienes permiso para verla.
          </p>
          <Link
            to="/training/sessions"
            className="mt-4 inline-block text-sm font-medium text-charcoal underline hover:opacity-70"
          >
            Volver a sesiones
          </Link>
        </div>
      </section>
    );
  }

  const isPlanned = session.status === "planned";
  const isCancelled = session.status === "cancelled";
  const notesValue = coachNotes !== null ? coachNotes : (session.coach_notes ?? "");
  const attendances = attendanceQuery.data ?? [];

  const linkedActivitiesByAthleteId = groupActivitiesByAthleteId(
    sessionActivitiesQuery.data?.items ?? [],
  );
  // Solo interesan actividades sin enlazar de atletas convocados a ESTA
  // sesión (session-detail-redesign.md §3.4) — una actividad de un atleta
  // que ni siquiera fue convocado no es asunto de esta página.
  const attendeeAthleteIds = new Set(attendances.map((a) => a.athlete_id));
  const unlinkedActivitiesByAthleteId = groupActivitiesByAthleteId(
    (unlinkedActivitiesQuery.data?.items ?? []).filter((activity) =>
      attendeeAthleteIds.has(activity.athlete_id),
    ),
  );

  return (
    <section className="space-y-5">
      {/* Header */}
      <div
        className="rounded-xl bg-white px-5 py-4"
        style={cardStyle}
        data-testid="session-detail-header"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="text-xl text-charcoal"
                style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
              >
                {session.technical_focus}
              </h1>
              <SessionStatusBadge status={session.status} />
            </div>
            <p className="mt-1 text-sm text-mid-gray">
              {formatDate(session.scheduled_date)} · {formatTime(session.scheduled_start_time)} · {session.duration_min} min · {session.location}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {isPlanned && (
              <>
                <Link
                  to={`/training/sessions/${session.id}/edit`}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  Editar
                </Link>
                <button
                  type="button"
                  onClick={() => setShowCancelModal(true)}
                  className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700 transition-opacity hover:opacity-70"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  data-testid="cancel-session-button"
                >
                  Cancelar sesión
                </button>
                <button
                  type="button"
                  onClick={() => executeMutation.mutate(sessionId)}
                  disabled={executeMutation.isPending}
                  className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  data-testid="execute-session-button"
                >
                  {executeMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  )}
                  Marcar ejecutada
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Detalles */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
        <h2 className={sectionHeading}>Detalles</h2>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-mid-gray">Descripción</dt>
            <dd className="mt-0.5 text-sm text-charcoal whitespace-pre-line">{session.description}</dd>
          </div>
          <div>
            <dt className="text-xs text-mid-gray">Notas del entrenador</dt>
            <dd className="mt-0.5">
              <div className="relative">
                <textarea
                  value={notesValue}
                  onChange={(e) => handleNotesChange(e.target.value)}
                  disabled={isCancelled}
                  rows={3}
                  maxLength={2000}
                  placeholder="Notas post-sesión…"
                  aria-label="Notas del entrenador"
                  className="w-full resize-none rounded-lg px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                />
                <span
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className={`absolute right-2 bottom-2 text-xs text-mid-gray${notesSaving ? "" : " invisible"}`}
                >
                  Guardando…
                </span>
              </div>
            </dd>
          </div>
        </dl>
      </div>

      {/* Recorrido */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
        <h2 className={sectionHeading}>Recorrido</h2>

        {session.route_text && (
          <div>
            <p className="text-xs text-mid-gray mb-1">Descripción del recorrido</p>
            <p className="text-sm text-charcoal whitespace-pre-line">{session.route_text}</p>
          </div>
        )}

        {session.strava_url && (
          <a
            href={session.strava_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            <ExternalLink size={14} aria-hidden="true" />
            Ver actividad en Strava
          </a>
        )}

        {session.route_file_path && (
          <Suspense
            fallback={
              <div className="h-64 animate-pulse rounded-xl bg-light-gray" />
            }
          >
            <RouteViewer routeFilePath={session.route_file_path} />
          </Suspense>
        )}

        {!isCancelled && (
          <div
            role="button"
            tabIndex={0}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            aria-label="Soltar archivo .gpx aquí o presionar Enter para seleccionar"
            className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-light-gray px-4 py-8 transition-colors hover:border-mid-gray"
            data-testid="route-upload-dropzone"
          >
            {uploadMutation.isPending ? (
              <Loader2 className="h-6 w-6 animate-spin text-mid-gray" aria-hidden="true" />
            ) : (
              <>
                <Upload size={20} className="text-mid-gray" aria-hidden="true" />
                <p className="mt-2 text-sm text-mid-gray">
                  Arrastra un archivo .gpx o .fit aquí, o{" "}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="font-medium text-charcoal underline hover:opacity-70"
                  >
                    selecciónalo
                  </button>
                </p>
                <p className="mt-1 text-xs text-mid-gray">Máx. 5 MB</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".gpx,.fit"
              className="hidden"
              onChange={handleFileChange}
              data-testid="route-file-input"
              aria-label="Subir archivo de recorrido"
            />
          </div>
        )}

        {uploadMutation.isError && (
          <p className="text-sm text-red-600" role="alert">
            Error al subir el archivo. Verifica el formato y tamaño.
          </p>
        )}
      </div>

      {/* Asistencia */}
      <div className="rounded-xl bg-white px-5 py-4" style={cardStyle}>
        <div className="flex items-center justify-between mb-3">
          <h2 className={sectionHeading} style={{ marginBottom: 0 }}>
            Asistencia ({attendances.length})
          </h2>
          {attendanceQuery.isLoading && (
            <Loader2 size={16} className="animate-spin text-mid-gray" aria-hidden="true" />
          )}
        </div>

        {attendanceQuery.isError && (
          <p className="text-sm text-red-600" role="alert">
            No se pudo cargar la lista de asistencia.
          </p>
        )}

        {sessionActivitiesQuery.isError && (
          <p className="text-sm text-red-600" role="alert">
            No se pudieron cargar las actividades Strava vinculadas.
          </p>
        )}

        {!attendanceQuery.isLoading && !attendanceQuery.isError && (
          <AttendanceTable
            sessionId={sessionId}
            attendances={attendances}
            disabled={isCancelled}
            linkedActivitiesByAthleteId={linkedActivitiesByAthleteId}
            unlinkedActivitiesByAthleteId={unlinkedActivitiesByAthleteId}
            activitiesLoading={sessionActivitiesQuery.isLoading || unlinkedActivitiesQuery.isLoading}
            canLink={!isCancelled}
          />
        )}
      </div>

      {/* Bloques de fuerza (feature 021, FR-012/FR-013) */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
        <div className="flex items-center justify-between">
          <h2 className={sectionHeading} style={{ marginBottom: 0 }}>
            Bloques de fuerza
          </h2>
          <Link
            to="/strength/blocks/new"
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
                className="rounded-lg px-4 py-3"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
      </div>

      {/* Estructura de intervalos (feature 026) */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
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
            <Suspense
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
            </Suspense>
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
                  className="flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm text-charcoal"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  <span className="font-medium">
                    {BLOCK_TYPE_LABEL[block.block_type]}
                  </span>
                  <span className="text-mid-gray">
                    {formatDurationMmSs(block.duration_s)}
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
              sessionDate={session.scheduled_date}
            />

            {(sessionActivitiesQuery.data?.items.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-3">
                {sessionActivitiesQuery.data?.items.map((activity) => (
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
                    className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                  >
                    Crear estructura
                  </button>
                </div>
                <div>
                  <p className="mb-2 text-xs text-mid-gray">
                    O elegí un template desde la biblioteca del club:
                  </p>
                  <Suspense
                    fallback={
                      <div className="h-24 animate-pulse rounded-xl bg-light-gray" />
                    }
                  >
                    <TemplatePicker
                      trainingSessionId={sessionId}
                      onAttached={() => setStructureMode("view")}
                    />
                  </Suspense>
                </div>
              </>
            )}
          </>
        )}
      </div>

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

      {/* Fotos y videos */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
        <h2 className={sectionHeading}>Fotos y videos</h2>

        {!isCancelled && (
          <MediaUploadZone
            athletes={attendances.map((a) => ({
              id: a.athlete_id,
              label: a.athlete_name ?? `Atleta #${a.athlete_id}`,
            }))}
            onUpload={(payload) => mediaUploadMutation.mutateAsync(payload)}
            isUploading={mediaUploadMutation.isPending}
            uploadError={
              mediaUploadMutation.isError
                ? "No se pudo subir la media. Verifica el formato, tamaño y permisos."
                : null
            }
          />
        )}

        {mediaQuery.isLoading ? (
          <div className="h-24 animate-pulse rounded-lg bg-light-gray" />
        ) : (
          <Suspense
            fallback={
              <div role="status" aria-busy="true" aria-label="Cargando fotos y videos">
                <Skeleton className="h-24 rounded-lg" />
              </div>
            }
          >
            <MediaGallery
              media={(mediaQuery.data ?? []) as SessionMedia[]}
              onDelete={(mediaId) => mediaDeleteMutation.mutate(mediaId)}
              isDeleting={mediaDeleteMutation.isPending}
            />
          </Suspense>
        )}
      </div>

      <NotifyParentsDialog
        open={showCancelModal}
        variant="cancel"
        parentCount={attendances.length}
        isPending={cancelMutation.isPending}
        errorMessage={
          cancelMutation.isError
            ? "No se pudo cancelar la sesión. Intenta de nuevo."
            : null
        }
        onSend={(reason) => handleCancelConfirm(true, reason)}
        onSkip={() => handleCancelConfirm(false)}
        onCancel={() => setShowCancelModal(false)}
      />
    </section>
  );
}
