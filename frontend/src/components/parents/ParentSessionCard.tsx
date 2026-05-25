import { memo, useId, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronUp, Info } from "lucide-react";

import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { getAttendancePresentationWithExcuse } from "@/lib/attendanceStatus";
import { rubricToLabel, RUBRIC_TONE, showsRubricToParent } from "@/lib/parentMetrics";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  KidAttendance,
  TrainingSession,
} from "@/types/trainingSession.types";

interface ParentSessionCardProps {
  session: TrainingSession;
  kidAttendance?: KidAttendance | null;
  athleteAgeDecimal?: number | null;
}

const COMMENT_PREVIEW_CHARS = 90;

// Wave 5: microcopy pedagógico aplicado a cada label de rúbrica.
// El padre típico interpreta "Esfuerzo: Iniciando" como nota baja. El tooltip
// reencuadra: en LTAD 10-15 los marcadores cualitativos no son calificación;
// dependen de sueño/escuela/brote de crecimiento, no de "talento".
const RUBRIC_TOOLTIPS: Record<"effort" | "attitude" | "technique", string> = {
  effort:
    "A los 10-15 años el esfuerzo varía con sueño, escuela, crecimiento. Una sesión 'Iniciando' no es regresión.",
  attitude:
    "Disposición y compromiso del entrenamiento. Se ve mejor a lo largo del mes que en una sola sesión.",
  technique:
    "Habilidad sobre la bici. Progresa con repetición, no con presión.",
};

const RPE_TOOLTIP =
  "Escala interna del entrenador (1-10). No es nota: mide qué tan duro lo sintió tu atleta ese día.";

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

function ParentSessionCardImpl({
  session,
  kidAttendance,
  athleteAgeDecimal,
}: ParentSessionCardProps) {
  const titleId = useId();
  const status = kidAttendance?.status ?? null;
  const excuseReasonRaw = kidAttendance?.excuse_reason?.trim() || null;
  // Wave 5: cuando hay excuse_reason, "ausente" se presenta como "No asistió —
  // justificado" con tono azul (no rojo). Ver `getAttendancePresentationWithExcuse`.
  const attendanceBadge = status
    ? getAttendancePresentationWithExcuse(status, excuseReasonRaw)
    : null;

  const hasRubric =
    !!kidAttendance &&
    (kidAttendance.rubric_effort != null ||
      kidAttendance.rubric_attitude != null ||
      kidAttendance.rubric_technique != null ||
      kidAttendance.rpe_omni != null);

  const showRubric = showsRubricToParent(athleteAgeDecimal) && hasRubric;

  const feedback = kidAttendance?.individual_feedback?.trim() || null;
  const isExecuted = session.status === "executed";
  const hasInlineFooter = !!attendanceBadge || showRubric || !!feedback || !!excuseReasonRaw;

  return (
    <article
      className="overflow-hidden rounded-xl bg-white shadow-ring-soft"
      data-testid="parent-session-card"
      aria-labelledby={titleId}
    >
      <Link
        to={`/parents/training/sessions/${session.id}`}
        className="flex flex-col rounded-t-xl transition-colors hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
        aria-label={`Ver sesión: ${session.technical_focus} del ${formatDate(session.scheduled_date)}`}
      >
        <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
          <div className="min-w-0 flex-1">
            <h3
              id={titleId}
              className="truncate text-base font-medium text-charcoal"
            >
              {session.technical_focus}
            </h3>
            <p className="mt-0.5 text-sm text-mid-gray">
              {formatDate(session.scheduled_date)} · {formatTime(session.scheduled_start_time)}
            </p>
            <p className="mt-0.5 truncate text-sm text-mid-gray">{session.location}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <SessionStatusBadge status={session.status} />
            {attendanceBadge && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${attendanceBadge.tone}`}
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
          data-testid="parent-session-inline"
        >
          {/* Excuse reason (ausente / justificado / lesionado) */}
          {excuseReasonRaw && (
            <p className="text-sm text-mid-gray" data-testid="inline-excuse">
              <span className="font-medium text-charcoal">Motivo:</span> {excuseReasonRaw}
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

// Wave 5 perf: el componente recibe props como objetos (`session`, `kidAttendance`).
// TanStack Query devuelve referencias estables mientras el cache no se invalide
// y `staleTime: 5min` está activo a nivel global, por lo que `memo` evita
// re-renders innecesarios cuando el padre cambia mes y la lista de cards
// vuelve a renderizarse. El comparador shallow default basta — todas las
// props son referencias o primitivas.
export const ParentSessionCard = memo(ParentSessionCardImpl);
ParentSessionCard.displayName = "ParentSessionCard";

function InfoIcon({ label }: { label: string }) {
  // Botón disparador del tooltip — separado del label para que el chip de la
  // rúbrica siga siendo "etiqueta" semánticamente y solo el ⓘ sea interactivo.
  return (
    <TooltipTrigger asChild>
      <button
        type="button"
        aria-label={label}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
      >
        <Info size={12} aria-hidden="true" />
      </button>
    </TooltipTrigger>
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
  const items: {
    key: "effort" | "attitude" | "technique";
    label: string;
    value: number | null;
    testId: string;
  }[] = [
    { key: "effort", label: "Esfuerzo", value: effort, testId: "inline-rubric-effort" },
    { key: "attitude", label: "Actitud", value: attitude, testId: "inline-rubric-attitude" },
    { key: "technique", label: "Técnica", value: technique, testId: "inline-rubric-technique" },
  ];

  return (
    <div data-testid="inline-rubric">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Lo que observó el entrenador
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {items.map((it) => {
          const label = rubricToLabel(it.value);
          if (!label) return null;
          return (
            <li
              key={it.key}
              data-testid={it.testId}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${RUBRIC_TONE[label]}`}
              aria-label={`${it.label}: ${label}`}
            >
              {it.label}: {label}
              <Tooltip>
                <InfoIcon label={`Más información sobre ${it.label}`} />
                <TooltipContent side="top">{RUBRIC_TOOLTIPS[it.key]}</TooltipContent>
              </Tooltip>
            </li>
          );
        })}
        {rpe != null && (
          <li
            data-testid="inline-rubric-rpe"
            className="inline-flex items-center rounded-full bg-light-gray px-2.5 py-0.5 text-xs font-medium text-charcoal"
            aria-label={`Esfuerzo percibido registrado por el entrenador: ${rpe} de 10`}
          >
            RPE {rpe}/10
            <Tooltip>
              <InfoIcon label="Más información sobre RPE" />
              <TooltipContent side="top">{RPE_TOOLTIP}</TooltipContent>
            </Tooltip>
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
  const disclaimerId = useId();
  const preview = isLong ? `${text.slice(0, COMMENT_PREVIEW_CHARS).trimEnd()}…` : text;

  return (
    <div className="rounded-lg bg-light-gray/60 px-3 py-2.5">
      {/* Wave 5 — disclaimer pedagógico ARRIBA del comentario.
          Razón: el coach reportó que padres leen la rúbrica y reaccionan en
          caliente con el atleta. Poner el disclaimer al pie lo lee demasiado
          tarde — al inicio, condiciona el marco mental antes de leer la nota. */}
      <p
        id={disclaimerId}
        role="note"
        aria-label="Recomendación pedagógica"
        className="mb-2 text-[11px] leading-snug text-text-disclaimer"
      >
        Esta nota es para acompañarte como familia. Si vas a conversarlo con tu
        atleta, espera al día siguiente y enfócate en lo que disfrutó, no en
        la rúbrica.
      </p>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Nota del entrenador
      </p>
      <p
        id={collapsedId}
        aria-describedby={disclaimerId}
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
          className="mt-1 inline-flex min-h-11 items-center gap-1 -mx-2 px-2 rounded text-xs font-medium text-charcoal transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
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
    </div>
  );
}
