import { lazy, Suspense, useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ExternalLink, Loader2, Upload } from "lucide-react";

import {
  useCancelTrainingSession,
  useExecuteTrainingSession,
  useSessionAttendance,
  useTrainingSession,
  useUploadRouteFile,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { AttendanceTable } from "@/components/training/AttendanceTable";
import { ConfirmModal } from "@/components/common/ConfirmModal";

const RouteViewer = lazy(() =>
  import("@/components/training/RouteViewer").then((m) => ({ default: m.RouteViewer })),
);

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
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

export function SessionDetailPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const navigate = useNavigate();

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [coachNotes, setCoachNotes] = useState<string | null>(null);
  const [notesSaving, setNotesSaving] = useState(false);
  const notesDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sessionQuery = useTrainingSession(sessionId);
  const attendanceQuery = useSessionAttendance(sessionId, !!sessionId);
  const executeMutation = useExecuteTrainingSession();
  const cancelMutation = useCancelTrainingSession();
  const uploadMutation = useUploadRouteFile(sessionId);
  const updateMutation = useUpdateTrainingSession();

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

  const handleCancelConfirm = useCallback(() => {
    cancelMutation.mutate(sessionId, {
      onSuccess: () => {
        setShowCancelModal(false);
        navigate("/training/sessions");
      },
    });
  }, [cancelMutation, sessionId, navigate]);

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

        {!attendanceQuery.isLoading && !attendanceQuery.isError && (
          <AttendanceTable
            sessionId={sessionId}
            attendances={attendances}
            disabled={isCancelled}
          />
        )}
      </div>

      <ConfirmModal
        open={showCancelModal}
        title="Cancelar sesión"
        body="Esta acción marcará la sesión como cancelada. No podrás revertirla. ¿Deseas continuar?"
        confirmLabel="Sí, cancelar sesión"
        cancelLabel="Volver"
        confirmDanger
        isPending={cancelMutation.isPending}
        onCancel={() => setShowCancelModal(false)}
        onConfirm={handleCancelConfirm}
      />
    </section>
  );
}
