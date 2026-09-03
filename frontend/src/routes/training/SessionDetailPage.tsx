import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ExternalLink, Loader2, Upload } from "lucide-react";

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
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { AttendanceTable } from "@/components/training/AttendanceTable";
import { MediaUploadZone } from "@/components/training/MediaUploadZone";
import { NotifyParentsDialog } from "@/components/training/NotifyParentsDialog";
import { PlanSection } from "@/components/training/session-plan/PlanSection";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/PageHeader";
import { isToday } from "@/lib/datetime";
import type { SessionMedia } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";
import { useSessionActivities } from "@/hooks/activities/useSessionActivities";
import { useUnlinkedActivitiesNearDate } from "@/hooks/activities/useUnlinkedActivitiesNearDate";

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

const sectionHeading = "text-sm font-semibold uppercase tracking-wide text-mid-gray mb-3";

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3 shadow-card">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-light-gray" style={{ width: `${70 - i * 15}%` }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sección activa (?section=) — feature 032, US2 (contracts/session-sections.md)
// ---------------------------------------------------------------------------

type Section = "resumen" | "asistencia" | "plan" | "media";

const VALID_SECTIONS: readonly Section[] = ["resumen", "asistencia", "plan", "media"];

/** Copia el patrón de `AthleteDetailPage.tsx`'s `parseTabParam` (`:87-90`). */
function parseSectionParam(raw: string | null): Section | null {
  if (raw && (VALID_SECTIONS as readonly string[]).includes(raw)) {
    return raw as Section;
  }
  return null;
}

/**
 * `asistencia` cuando la sesión es hoy en la zona horaria del club;
 * `resumen` en cualquier otro caso (contracts/session-sections.md, "Default
 * section rule").
 */
function defaultSection(scheduledDate: string | null | undefined): Section {
  return isToday(scheduledDate) ? "asistencia" : "resumen";
}

export function SessionDetailPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [coachNotes, setCoachNotes] = useState<string | null>(null);
  const [notesSaving, setNotesSaving] = useState(false);
  const notesDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Un ref por sección (no uno compartido): `@radix-ui/react-tabs` mantiene
  // los cuatro `TabsContent` montados en el DOM (oculta los inactivos vía
  // `hidden`, no los desmonta de inmediato — usa `Presence` internamente),
  // así que un único ref reasignado en cada render no garantiza apuntar al
  // heading de la sección realmente activa.
  const resumenHeadingRef = useRef<HTMLHeadingElement>(null);
  const asistenciaHeadingRef = useRef<HTMLHeadingElement>(null);
  const planHeadingRef = useRef<HTMLHeadingElement>(null);
  const mediaHeadingRef = useRef<HTMLHeadingElement>(null);

  const sessionQuery = useTrainingSession(sessionId);

  const sectionFromUrl = parseSectionParam(searchParams.get("section"));
  const [activeSection, setActiveSection] = useState<Section>(
    sectionFromUrl ?? defaultSection(sessionQuery.data?.scheduled_date),
  );
  // Si la sección ya vino resuelta por la URL al montar, la regla default
  // no debe pisarla una vez la sesión termine de cargar.
  const [hasResolvedDefault, setHasResolvedDefault] = useState(sectionFromUrl !== null);

  const attendanceQuery = useSessionAttendance(sessionId, !!sessionId);
  const executeMutation = useExecuteTrainingSession();
  const cancelMutation = useCancelTrainingSession();
  const uploadMutation = useUploadRouteFile(sessionId);
  const updateMutation = useUpdateTrainingSession();
  // T037 (perf, opcional): solo se piden datos de una sección cuando está
  // activa — antes de la sectorización estas queries corrían todas al
  // montar la página sin importar el scroll del coach.
  const mediaQuery = useSessionMedia(sessionId, !!sessionId && activeSection === "media");
  const mediaUploadMutation = useUploadSessionMedia(sessionId);
  const mediaDeleteMutation = useDeleteSessionMedia(sessionId);
  // Se usa tanto en Asistencia (agrupar por atleta convocado) como en Plan
  // (links de comparación plan-vs-real por actividad enlazada) — no se
  // puede acotar a una sola sección.
  const sessionActivitiesQuery = useSessionActivities(
    sessionId,
    !!sessionId && (activeSection === "asistencia" || activeSection === "plan"),
  );
  // Referencia `sessionQuery.data` directo (no `session`, definido más abajo
  // después de los early-return de loading/error) para respetar las reglas
  // de hooks — este hook se llama siempre, en el mismo orden, sin importar
  // en qué estado esté la carga de la sesión.
  const unlinkedActivitiesQuery = useUnlinkedActivitiesNearDate(
    sessionQuery.data?.scheduled_date,
    sessionQuery.data?.status !== "cancelled" && activeSection === "asistencia",
  );

  const session = sessionQuery.data;

  // Regla default (contracts/session-sections.md): una vez carga la sesión,
  // si no vino una sección explícita por `?section=`, resolvemos
  // asistencia/resumen según la fecha y la fijamos en la URL con `replace`
  // (no agrega una entrada de historial nueva — el coach no "navegó" a
  // propósito, fue una decisión automática).
  useEffect(() => {
    if (hasResolvedDefault || !session) return;
    const computed = defaultSection(session.scheduled_date);
    setActiveSection(computed);
    setHasResolvedDefault(true);
    const next = new URLSearchParams(searchParams);
    next.set("section", computed);
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasResolvedDefault, session]);

  // Reaccionar a cambios externos del query string (back/forward del navegador).
  useEffect(() => {
    const urlSection = parseSectionParam(searchParams.get("section"));
    if (urlSection && urlSection !== activeSection) {
      setActiveSection(urlSection);
      setHasResolvedDefault(true);
    }
    // No incluimos activeSection para no entrar en loop al setear desde
    // handleSectionChange.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Cambio de sección explícito (click del coach en un TabsTrigger): push de
  // una entrada de historial nueva (a diferencia del `replace` de la regla
  // default) para que "atrás" vuelva a la sección previamente vista en vez
  // de salir de la página (SC-006).
  const handleSectionChange = useCallback(
    (value: string) => {
      const nextSection = value as Section;
      setActiveSection(nextSection);
      setHasResolvedDefault(true);
      const next = new URLSearchParams(searchParams);
      next.set("section", nextSection);
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  // Foco en el encabezado de la sección activa al cambiar (convención de
  // Stepper, specs/028-frontend-design-foundation/contracts/shared-components.md).
  useEffect(() => {
    const refBySection: Record<Section, React.RefObject<HTMLHeadingElement | null>> = {
      resumen: resumenHeadingRef,
      asistencia: asistenciaHeadingRef,
      plan: planHeadingRef,
      media: mediaHeadingRef,
    };
    refBySection[activeSection].current?.focus();
  }, [activeSection]);

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
        <div className="rounded-xl bg-white p-8 text-center shadow-card">
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
        className="rounded-xl bg-white px-5 py-4 shadow-card"
        data-testid="session-detail-header"
      >
        <PageHeader
          title={session.technical_focus}
          subtitle={`${formatDate(session.scheduled_date)} · ${formatTime(session.scheduled_start_time)} · ${session.duration_min} min · ${session.location}`}
          actions={
            <>
              <SessionStatusBadge status={session.status} />
              {isPlanned && (
                <>
                  <Link
                    to={`/training/sessions/${session.id}/edit`}
                    className="rounded-lg px-3 py-2 text-sm font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70"
                  >
                    Editar
                  </Link>
                  <button
                    type="button"
                    onClick={() => setShowCancelModal(true)}
                    className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700 shadow-ring transition-opacity hover:opacity-70"
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
            </>
          }
        />
      </div>

      <Tabs value={activeSection} onValueChange={handleSectionChange}>
        <TabsList aria-label="Secciones de la sesión">
          <TabsTrigger value="resumen" data-testid="session-section-tab-resumen">
            Resumen
          </TabsTrigger>
          <TabsTrigger value="asistencia" data-testid="session-section-tab-asistencia">
            Asistencia
          </TabsTrigger>
          <TabsTrigger value="plan" data-testid="session-section-tab-plan">
            Plan
          </TabsTrigger>
          <TabsTrigger value="media" data-testid="session-section-tab-media">
            Media
          </TabsTrigger>
        </TabsList>

        {/* Resumen: Detalles + Recorrido */}
        <TabsContent value="resumen" className="space-y-5" data-testid="session-section-resumen">
          <h2 ref={resumenHeadingRef} tabIndex={-1} className="sr-only">
            Resumen
          </h2>

          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            <h3 className={sectionHeading}>Detalles</h3>
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
                      className="w-full resize-none rounded-lg px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray shadow-ring outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
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

          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            <h3 className={sectionHeading}>Recorrido</h3>

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
              <>
                {/*
                  Sin `role="button"`/`tabIndex` en el contenedor: el botón
                  "selecciónalo" ya da acceso por teclado al selector de
                  archivo, así que envolver el div como control interactivo
                  duplicaría el rol y anidaría un `<button>` (y el
                  `<input type="file">`) dentro de otro control interactivo
                  — axe's "nested-interactive". El `<input>` oculto vive
                  fuera del div por la misma razón.
                */}
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
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
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".gpx,.fit"
                  className="hidden"
                  onChange={handleFileChange}
                  data-testid="route-file-input"
                  aria-label="Subir archivo de recorrido"
                />
              </>
            )}

            {uploadMutation.isError && (
              <p className="text-sm text-red-600" role="alert">
                Error al subir el archivo. Verifica el formato y tamaño.
              </p>
            )}
          </div>
        </TabsContent>

        {/* Asistencia */}
        <TabsContent value="asistencia" data-testid="session-section-asistencia">
          <div className="rounded-xl bg-white px-5 py-4 shadow-card">
            <div className="flex items-center justify-between mb-3">
              <h2
                ref={asistenciaHeadingRef}
                tabIndex={-1}
                className={sectionHeading}
                style={{ marginBottom: 0 }}
              >
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
        </TabsContent>

        {/* Plan (feature 032): estructura de intervalos */}
        <TabsContent value="plan" data-testid="session-section-plan">
          <h2 ref={planHeadingRef} tabIndex={-1} className="sr-only">
            Plan
          </h2>
          <PlanSection
            sessionId={sessionId}
            sessionDate={session.scheduled_date}
            isCancelled={isCancelled}
            activities={sessionActivitiesQuery.data?.items ?? []}
          />
        </TabsContent>

        {/* Fotos y videos */}
        <TabsContent value="media" data-testid="session-section-media">
          <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
            <h2 ref={mediaHeadingRef} tabIndex={-1} className={sectionHeading}>
              Fotos y videos
            </h2>

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
        </TabsContent>
      </Tabs>

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
