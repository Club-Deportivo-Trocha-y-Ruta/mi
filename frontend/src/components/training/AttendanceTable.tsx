import { useCallback, useEffect, useRef } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";

import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";
import { ActivityEvidenceStrip } from "./ActivityEvidenceStrip";
import { RubricSliders } from "./RubricSliders";
import { useAttendanceForm, ALLOWS_RUBRIC } from "./useAttendanceForm";

export interface AttendanceFormValues {
  status: AttendanceStatus;
  excuse_reason: string | null;
  rpe_omni: number | null;
  rubric_effort: number | null;
  rubric_attitude: number | null;
  rubric_technique: number | null;
  individual_feedback: string | null;
}

const STATUS_LABELS: Record<AttendanceStatus, string> = {
  presente: "Presente",
  ausente: "Ausente",
  justificado: "Justificado",
  tarde: "Tarde",
  lesionado: "Lesionado",
};

const STATUS_KEY_MAP: Record<string, AttendanceStatus> = {
  p: "presente",
  a: "ausente",
  j: "justificado",
  t: "tarde",
  l: "lesionado",
};

interface AttendanceRowProps {
  attendance: Attendance;
  sessionId: number;
  disabled?: boolean;
  linkedActivities: ActivityOut[];
  unlinkedActivities: ActivityOut[];
  activitiesLoading: boolean;
  canLink: boolean;
}

function AttendanceRow({
  attendance,
  sessionId,
  disabled,
  linkedActivities,
  unlinkedActivities,
  activitiesLoading,
  canLink,
}: AttendanceRowProps) {
  const rowRef = useRef<HTMLTableRowElement>(null);
  const reasonInputRef = useRef<HTMLInputElement | null>(null);

  const {
    control,
    register,
    setValue,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
    needsReasonAlert,
  } = useAttendanceForm(attendance, sessionId, disabled);

  const currentStatus = (formValues.status ?? attendance.status) as AttendanceStatus;
  const rubricEnabled = allowsRubric && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";

  useEffect(() => {
    if (needsReasonAlert) reasonInputRef.current?.focus();
  }, [needsReasonAlert]);

  const reasonField = register("excuse_reason");

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTableRowElement>) => {
      const tag = (e.target as HTMLElement).tagName.toLowerCase();
      // "button" incluye el chevron/"Enlazar" del ActivityEvidenceStrip —
      // esos botones deben recibir Tab/Enter normalmente, no ser
      // interceptados por los atajos P/A/J/T/L de la fila.
      if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") return;
      const mapped = STATUS_KEY_MAP[e.key.toLowerCase()];
      if (mapped) setValue("status", mapped);
    },
    [setValue],
  );

  const athleteName =
    attendance.athlete_name ?? `Atleta #${attendance.athlete_id}`;

  return (
    <tr
      ref={rowRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-keyshortcuts="p a j t l"
      className="group focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
      style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
      data-testid={`attendance-row-${attendance.athlete_id}`}
    >
      {/* Atleta */}
      <td className="px-3 py-2 text-sm font-medium text-charcoal">
        <div className="flex items-center gap-2">
          {athleteName}
          <span role="status" aria-live="polite" aria-atomic="true">
            {savedIndicator === "saved" && (
              <CheckCircle2
                size={14}
                className="animate-fade-in text-green-600"
                aria-label="Guardado"
                data-testid="saved-indicator"
              />
            )}
            {savedIndicator === "error" && !needsReasonAlert && (
              <span
                className="flex items-center gap-1 text-xs text-red-600"
                title="Error al guardar"
              >
                <AlertCircle size={14} aria-hidden="true" />
                Error
                <button
                  type="button"
                  onClick={() => doSave(formValues as AttendanceFormValues)}
                  className="ml-1 underline hover:opacity-70"
                  data-testid="retry-button"
                >
                  <RefreshCw size={12} aria-label="Reintentar" />
                </button>
              </span>
            )}
            {needsReasonAlert && (
              <span
                className="flex items-center gap-1 text-xs text-amber-600"
                title="Falta razón"
                data-testid="needs-reason-alert"
              >
                <AlertTriangle size={14} aria-hidden="true" />
                Falta razón
              </span>
            )}
          </span>
        </div>
        <div className="mt-1.5">
          <ActivityEvidenceStrip
            athleteId={attendance.athlete_id}
            linkedActivities={linkedActivities}
            unlinkedActivities={unlinkedActivities}
            loading={activitiesLoading}
            canLink={canLink}
          />
        </div>
      </td>

      {/* Estado */}
      <td className="px-3 py-2">
        <select
          {...register("status")}
          disabled={disabled}
          aria-label="Estado de asistencia"
          className="rounded-lg px-2 py-1.5 text-xs text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
        >
          {Object.entries(STATUS_LABELS).map(([val, label]) => (
            <option key={val} value={val}>
              {label}
            </option>
          ))}
        </select>
      </td>

      {/* Razón */}
      <td className="px-3 py-2">
        {requiresReason ? (
          <div className="flex flex-col gap-1">
            <input
              {...reasonField}
              ref={(el) => {
                reasonField.ref(el);
                reasonInputRef.current = el;
              }}
              type="text"
              disabled={disabled}
              placeholder="Razón (requerida)"
              maxLength={300}
              aria-label="Razón de ausencia"
              aria-required="true"
              aria-invalid={needsReasonAlert}
              aria-describedby={needsReasonAlert ? `reason-help-${attendance.athlete_id}` : undefined}
              className="w-full min-w-[140px] rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
              style={
                needsReasonAlert
                  ? { boxShadow: "rgba(217, 119, 6, 0.5) 0px 0px 0px 2px" }
                  : undefined
              }
            />
            {needsReasonAlert && (
              <p
                id={`reason-help-${attendance.athlete_id}`}
                className="text-[10px] text-amber-700"
              >
                Escribe una razón para guardar este estado
              </p>
            )}
          </div>
        ) : (
          <span className="text-xs text-mid-gray">—</span>
        )}
      </td>

      {/* Rúbrica expandida en columna */}
      <td className="px-3 py-2" colSpan={5}>
        {rubricEnabled ? (
          <div className="max-w-sm">
            <RubricSliders
              control={control}
              disabled={!rubricEnabled}
              feedbackLength={feedbackVal?.length ?? 0}
            />
          </div>
        ) : (
          <span className="text-xs text-mid-gray">
            {ALLOWS_RUBRIC.includes(currentStatus)
              ? "—"
              : "Solo disponible si presente o tarde"}
          </span>
        )}
      </td>
    </tr>
  );
}

function AttendanceCard({
  attendance,
  sessionId,
  disabled,
  linkedActivities,
  unlinkedActivities,
  activitiesLoading,
  canLink,
}: AttendanceRowProps) {
  const reasonInputRef = useRef<HTMLInputElement | null>(null);
  const {
    control,
    register,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
    needsReasonAlert,
  } = useAttendanceForm(attendance, sessionId, disabled);

  const rubricEnabled = allowsRubric && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";
  const currentStatus = (formValues.status ?? attendance.status) as AttendanceStatus;

  useEffect(() => {
    if (needsReasonAlert) reasonInputRef.current?.focus();
  }, [needsReasonAlert]);

  const reasonField = register("excuse_reason");

  const athleteName = attendance.athlete_name ?? `Atleta #${attendance.athlete_id}`;

  return (
    <div className="rounded-xl bg-white p-4 space-y-3 shadow-ring">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-charcoal">{athleteName}</p>
        <div className="flex items-center gap-2">
          {savedIndicator === "saved" && (
            <CheckCircle2 size={14} className="text-green-600" aria-label="Guardado" />
          )}
          {savedIndicator === "error" && !needsReasonAlert && (
            <button
              type="button"
              onClick={() => doSave(formValues as AttendanceFormValues)}
              className="text-xs text-red-600 underline"
            >
              Error — reintentar
            </button>
          )}
          {needsReasonAlert && (
            <span
              className="flex items-center gap-1 text-xs text-amber-600"
              data-testid="needs-reason-alert"
            >
              <AlertTriangle size={12} aria-hidden="true" />
              Falta razón
            </span>
          )}
          <select
            {...register("status")}
            disabled={disabled}
            aria-label="Estado de asistencia"
            className="rounded-lg px-2 py-1 text-xs text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
          >
            {Object.entries(STATUS_LABELS).map(([val, label]) => (
              <option key={val} value={val}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ActivityEvidenceStrip
        athleteId={attendance.athlete_id}
        linkedActivities={linkedActivities}
        unlinkedActivities={unlinkedActivities}
        loading={activitiesLoading}
        canLink={canLink}
      />

      {requiresReason && (
        <div className="flex flex-col gap-1">
          <input
            {...reasonField}
            ref={(el) => {
              reasonField.ref(el);
              reasonInputRef.current = el;
            }}
            type="text"
            disabled={disabled}
            placeholder="Razón (requerida)"
            maxLength={300}
            aria-label="Razón de ausencia"
            aria-required="true"
            aria-invalid={needsReasonAlert}
            aria-describedby={needsReasonAlert ? `reason-help-card-${attendance.athlete_id}` : undefined}
            className="w-full rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
            style={
              needsReasonAlert
                ? { boxShadow: "rgba(217, 119, 6, 0.5) 0px 0px 0px 2px" }
                : undefined
            }
          />
          {needsReasonAlert && (
            <p
              id={`reason-help-card-${attendance.athlete_id}`}
              className="text-[10px] text-amber-700"
            >
              Escribe una razón para guardar este estado
            </p>
          )}
        </div>
      )}

      {rubricEnabled && (
        <RubricSliders
          control={control}
          disabled={!rubricEnabled}
          feedbackLength={feedbackVal?.length ?? 0}
        />
      )}

      {!rubricEnabled && (
        <p className="text-xs text-mid-gray">
          {ALLOWS_RUBRIC.includes(currentStatus)
            ? "—"
            : "Rúbrica disponible solo si presente o tarde"}
        </p>
      )}
    </div>
  );
}

interface AttendanceTableProps {
  sessionId: number;
  attendances: Attendance[];
  disabled?: boolean;
  linkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  unlinkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  activitiesLoading?: boolean;
  canLink?: boolean;
}

export function AttendanceTable({
  sessionId,
  attendances,
  disabled,
  linkedActivitiesByAthleteId,
  unlinkedActivitiesByAthleteId,
  activitiesLoading = false,
  canLink = false,
}: AttendanceTableProps) {
  if (attendances.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray">
        No hay atletas convocados en esta sesión.
      </p>
    );
  }

  return (
    <>
      {/* Mobile: cards */}
      <div className="flex flex-col gap-3 md:hidden">
        {attendances.map((a) => (
          <AttendanceCard
            key={a.athlete_id}
            attendance={a}
            sessionId={sessionId}
            disabled={disabled}
            linkedActivities={linkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
            unlinkedActivities={unlinkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
            activitiesLoading={activitiesLoading}
            canLink={canLink}
          />
        ))}
      </div>

      {/* Desktop: tabla */}
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full text-sm">
          <caption className="sr-only">Asistencia de atletas convocados</caption>
          <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
            <tr>
              <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Atleta
              </th>
              <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Estado
              </th>
              <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Razón
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray"
                colSpan={5}
              >
                Rúbrica / RPE / Comentario
              </th>
            </tr>
          </thead>
          <tbody>
            {attendances.map((a) => (
              <AttendanceRow
                key={a.athlete_id}
                attendance={a}
                sessionId={sessionId}
                disabled={disabled}
                linkedActivities={linkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                unlinkedActivities={unlinkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                activitiesLoading={activitiesLoading}
                canLink={canLink}
              />
            ))}
          </tbody>
        </table>
        <details className="px-3 py-1">
          <summary className="text-xs text-mid-gray cursor-pointer">Atajos de teclado</summary>
          <ul className="text-xs text-mid-gray mt-1 space-y-0.5">
            <li>P — Presente</li>
            <li>A — Ausente</li>
            <li>J — Justificado</li>
            <li>T — Tarde</li>
            <li>L — Lesionado</li>
          </ul>
        </details>
        <p className="mt-1 px-3 pb-2 text-[10px] text-mid-gray">
          Atajo: P=Presente A=Ausente J=Justificado T=Tarde L=Lesionado
        </p>
      </div>
    </>
  );
}
