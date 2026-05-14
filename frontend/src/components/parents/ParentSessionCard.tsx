import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronUp } from "lucide-react";

import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { rubricToLabel, RUBRIC_TONE, showsRubricToParent } from "@/lib/parentMetrics";
import type {
  AttendanceStatus,
  KidAttendance,
  TrainingSession,
} from "@/types/trainingSession.types";

interface ParentSessionCardProps {
  session: TrainingSession;
  kidAttendance?: KidAttendance | null;
  athleteAgeDecimal?: number | null;
}

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const ATTENDANCE_CONFIG: Record<
  AttendanceStatus,
  { label: string; className: string }
> = {
  presente: { label: "Presente", className: "bg-green-100 text-green-800" },
  tarde: { label: "Tarde", className: "bg-amber-100 text-amber-800" },
  ausente: { label: "Ausente", className: "bg-red-100 text-red-700" },
  justificado: { label: "Justificado", className: "bg-blue-100 text-blue-800" },
  lesionado: { label: "Lesionado", className: "bg-purple-100 text-purple-800" },
};

const COMMENT_PREVIEW_CHARS = 90;

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(date);
}

function formatTime(timeStr: string): string {
  return timeStr.slice(0, 5);
}

export function ParentSessionCard({
  session,
  kidAttendance,
  athleteAgeDecimal,
}: ParentSessionCardProps) {
  const status = kidAttendance?.status ?? null;
  const attendanceBadge = status ? ATTENDANCE_CONFIG[status] : null;

  const hasRubric =
    !!kidAttendance &&
    (kidAttendance.rubric_effort != null ||
      kidAttendance.rubric_attitude != null ||
      kidAttendance.rubric_technique != null ||
      kidAttendance.rpe_omni != null);

  const showRubric = showsRubricToParent(athleteAgeDecimal) && hasRubric;

  const feedback = kidAttendance?.individual_feedback?.trim() || null;
  const excuseReason = kidAttendance?.excuse_reason?.trim() || null;
  const isExecuted = session.status === "executed";
  const hasInlineFooter = !!attendanceBadge || showRubric || !!feedback || !!excuseReason;

  return (
    <article
      className="overflow-hidden rounded-xl bg-white"
      style={{ boxShadow: CARD_SHADOW }}
      data-testid="parent-session-card"
    >
      <Link
        to={`/parents/training/sessions/${session.id}`}
        className="flex flex-col rounded-t-xl transition-colors hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
        aria-label={`Ver sesión: ${session.technical_focus} del ${formatDate(session.scheduled_date)}`}
      >
        <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-medium text-charcoal">
              {session.technical_focus}
            </p>
            <p className="mt-0.5 text-sm text-mid-gray">
              {formatDate(session.scheduled_date)} · {formatTime(session.scheduled_start_time)}
            </p>
            <p className="mt-0.5 truncate text-sm text-mid-gray">{session.location}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <SessionStatusBadge status={session.status} />
            {attendanceBadge && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${attendanceBadge.className}`}
                aria-label={`Asistencia de tu atleta: ${attendanceBadge.label}`}
              >
                {attendanceBadge.label}
              </span>
            )}
          </div>
        </div>
      </Link>

      {isExecuted && hasInlineFooter && (
        <div
          className="space-y-3 px-4 pt-3 pb-3"
          style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
          data-testid="parent-session-inline"
        >
          {/* Excuse reason (ausente / justificado / lesionado) */}
          {excuseReason && (
            <p className="text-sm text-mid-gray" data-testid="inline-excuse">
              <span className="font-medium text-charcoal">Motivo:</span> {excuseReason}
            </p>
          )}

          {/* Rúbrica con etiquetas cualitativas — solo ≥13 */}
          {showRubric && kidAttendance && (
            <RubricInline
              effort={kidAttendance.rubric_effort ?? null}
              attitude={kidAttendance.rubric_attitude ?? null}
              technique={kidAttendance.rubric_technique ?? null}
              rpe={kidAttendance.rpe_omni ?? null}
            />
          )}

          {/* Comentario individual del entrenador */}
          {feedback && <CoachComment text={feedback} />}
        </div>
      )}

      <div
        className="flex items-center justify-end px-4 py-2"
        style={{ borderTop: hasInlineFooter ? "1px solid rgba(34, 42, 53, 0.06)" : undefined }}
      >
        <Link
          to={`/parents/training/sessions/${session.id}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-mid-gray transition-colors hover:text-charcoal"
          aria-label={`Ver detalle de la sesión ${session.technical_focus}`}
        >
          Ver detalle
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

function RubricInline({
  effort,
  attitude,
  technique,
  rpe,
}: {
  effort: number | null;
  attitude: number | null;
  technique: number | null;
  rpe: number | null;
}) {
  const items: { key: string; label: string; value: number | null; testId: string }[] = [
    { key: "effort", label: "Esfuerzo", value: effort, testId: "inline-rubric-effort" },
    { key: "attitude", label: "Actitud", value: attitude, testId: "inline-rubric-attitude" },
    { key: "technique", label: "Técnica", value: technique, testId: "inline-rubric-technique" },
  ];

  return (
    <div data-testid="inline-rubric">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Cómo le fue esta sesión
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {items.map((it) => {
          const label = rubricToLabel(it.value);
          if (!label) return null;
          return (
            <li
              key={it.key}
              data-testid={it.testId}
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${RUBRIC_TONE[label]}`}
              aria-label={`${it.label}: ${label}`}
            >
              {it.label}: {label}
            </li>
          );
        })}
        {rpe != null && (
          <li
            data-testid="inline-rubric-rpe"
            className="rounded-full bg-light-gray px-2.5 py-0.5 text-xs font-medium text-charcoal"
            aria-label={`Esfuerzo percibido registrado por el entrenador: ${rpe} de 10`}
          >
            RPE {rpe}/10
          </li>
        )}
      </ul>
    </div>
  );
}

function CoachComment({ text }: { text: string }) {
  const isLong = text.length > COMMENT_PREVIEW_CHARS;
  const [expanded, setExpanded] = useState(false);
  const collapsedId = useId();
  const preview = isLong ? `${text.slice(0, COMMENT_PREVIEW_CHARS).trimEnd()}…` : text;

  return (
    <div className="rounded-lg bg-light-gray/60 px-3 py-2.5">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Nota del entrenador
      </p>
      <p
        id={collapsedId}
        className="whitespace-pre-line text-sm text-charcoal"
        data-testid={expanded ? "inline-comment-full" : "inline-comment-preview"}
      >
        {expanded || !isLong ? text : preview}
      </p>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls={collapsedId}
          className="mt-1 inline-flex items-center gap-1 rounded text-xs font-medium text-charcoal transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
          data-testid="comment-expand-button"
        >
          {expanded ? (
            <>
              Ver menos <ChevronUp size={12} aria-hidden="true" />
            </>
          ) : (
            <>
              Ver más <ChevronDown size={12} aria-hidden="true" />
            </>
          )}
        </button>
      )}
      <p className="mt-2 text-[11px] leading-tight text-mid-gray">
        Esta nota es para ti, no para tu atleta. Evita comentarla con él/ella el mismo día —
        habla mejor al día siguiente si lo crees necesario.
      </p>
    </div>
  );
}
