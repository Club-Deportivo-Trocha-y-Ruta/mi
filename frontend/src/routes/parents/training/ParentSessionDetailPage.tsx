import { lazy, Suspense } from "react";
import { Link, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";

import { ReadOnlyAttendanceRow } from "@/components/parents/ReadOnlyAttendanceRow";
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { MediaGallery } from "@/components/training/MediaGallery";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useSessionAttendance, useTrainingSession } from "@/api/trainingSessions";
import { useSessionMedia } from "@/api/sessionMedia";
import type { SessionMediaParent } from "@/types/trainingSession.types";

const RouteViewer = lazy(() =>
  import("@/components/training/RouteViewer").then((m) => ({ default: m.RouteViewer })),
);

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const sectionHeading = "text-sm font-semibold text-mid-gray mb-3";

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
}

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3" style={cardStyle}>
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-light-gray" style={{ width: `${70 - i * 15}%` }} />
      ))}
    </div>
  );
}

export function ParentSessionDetailPage() {
  const { id } = useParams();
  const sessionId = Number(id);

  const sessionQuery = useTrainingSession(sessionId);
  const attendanceQuery = useSessionAttendance(sessionId, !!sessionId);
  const athletesQuery = useMyAthletes();
  const mediaQuery = useSessionMedia(sessionId, !!sessionId);

  const session = sessionQuery.data;
  const myAthletes = athletesQuery.data ?? [];
  const myAthleteIds = myAthletes.map((a) => a.athlete_id);
  const athleteNameById = new Map(
    myAthletes.map((a) => [a.athlete_id, `${a.athlete_first_name} ${a.athlete_last_name}`]),
  );

  // Defensive filter: only attendance rows belonging to parent's own athletes.
  // Even if the backend leaks other rows, we never render them.
  const allAttendance = attendanceQuery.data ?? [];
  const myAttendance = allAttendance.filter((a) => myAthleteIds.includes(a.athlete_id));

  if (sessionQuery.isLoading || athletesQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-4 w-24 animate-pulse rounded bg-light-gray" />
        <SkeletonCard />
        <SkeletonCard />
      </section>
    );
  }

  if (sessionQuery.isError || !session) {
    return (
      <section className="space-y-4">
        <Link
          to="/parents/training/sessions"
          className="flex items-center gap-1 text-sm font-medium text-mid-gray hover:text-charcoal"
        >
          <span>←</span>
          <span>Entrenamientos</span>
        </Link>
        <div className="rounded-xl bg-white p-8 text-center" style={cardStyle}>
          <p className="text-base font-medium text-charcoal">Sesión no encontrada</p>
          <p className="mt-1 text-sm text-mid-gray">
            La sesión no existe o no tienes acceso a ella.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      {/* Breadcrumb */}
      <Link
        to="/parents/training/sessions"
        className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray hover:text-charcoal"
      >
        <span>←</span>
        <span>Entrenamientos</span>
      </Link>

      {/* Header */}
      <div className="rounded-xl bg-white px-5 py-4" style={cardStyle} data-testid="session-header">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h1
            className="text-xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            {session.technical_focus}
          </h1>
          <SessionStatusBadge status={session.status} />
        </div>
        <p className="text-sm text-mid-gray">
          {formatDate(session.scheduled_date)} · {formatTime(session.scheduled_start_time)} · {session.duration_min} min · {session.location}
        </p>
      </div>

      {/* Detalles generales */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-3" style={cardStyle}>
        <h2 className={sectionHeading}>Detalles</h2>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-mid-gray">Descripción</dt>
            <dd className="mt-0.5 text-sm text-charcoal whitespace-pre-line">
              {session.description}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-mid-gray">Lugar</dt>
            <dd className="mt-0.5 text-sm text-charcoal">{session.location}</dd>
          </div>
        </dl>
      </div>

      {/* Recorrido */}
      {(session.route_text || session.strava_url || session.route_file_path) && (
        <div className="rounded-xl bg-white px-5 py-4 space-y-3" style={cardStyle}>
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
              fallback={<div className="h-64 animate-pulse rounded-xl bg-light-gray" />}
            >
              <RouteViewer routeFilePath={session.route_file_path} />
            </Suspense>
          )}
        </div>
      )}

      {/* Fotos y videos donde aparece tu atleta */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-3" style={cardStyle}>
        <h2 className={sectionHeading}>Fotos y videos</h2>
        {mediaQuery.isLoading ? (
          <div className="h-24 animate-pulse rounded-lg bg-light-gray" />
        ) : (
          <MediaGallery
            media={(mediaQuery.data ?? []) as SessionMediaParent[]}
            readOnly
          />
        )}
      </div>

      {/* Asistencia de mi atleta */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-mid-gray px-1">
          Asistencia de tu atleta
        </h2>

        {attendanceQuery.isLoading && (
          <div className="h-20 animate-pulse rounded-xl bg-light-gray" />
        )}

        {attendanceQuery.isError && (
          <p className="text-sm text-red-600 px-1" role="alert">
            No se pudo cargar la asistencia.
          </p>
        )}

        {!attendanceQuery.isLoading && !attendanceQuery.isError && myAttendance.length === 0 && (
          <div className="rounded-xl bg-white px-5 py-5" style={cardStyle}>
            <p className="text-sm text-mid-gray">
              Tu atleta no figura como convocado en esta sesión.
            </p>
          </div>
        )}

        {!attendanceQuery.isLoading &&
          !attendanceQuery.isError &&
          myAttendance.map((attendance) => (
            <ReadOnlyAttendanceRow
              key={attendance.id}
              attendance={attendance}
              athleteName={athleteNameById.get(attendance.athlete_id) ?? "Atleta"}
            />
          ))}
      </div>
    </section>
  );
}
