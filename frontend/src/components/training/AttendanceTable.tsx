import { useCallback, useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";

import { useUpdateAttendance } from "@/api/trainingSessions";
import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";
import { RubricSliders } from "./RubricSliders";

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

const REQUIRES_REASON: AttendanceStatus[] = ["ausente", "justificado", "lesionado"];
const ALLOWS_RUBRIC: AttendanceStatus[] = ["presente", "tarde"];

interface AttendanceRowProps {
  attendance: Attendance;
  sessionId: number;
  disabled?: boolean;
}

function AttendanceRow({ attendance, sessionId, disabled }: AttendanceRowProps) {
  const [savedIndicator, setSavedIndicator] = useState<"saved" | "error" | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rowRef = useRef<HTMLTableRowElement>(null);

  const mutation = useUpdateAttendance(sessionId);

  const { control, register, setValue } = useForm<AttendanceFormValues>({
    defaultValues: {
      status: attendance.status,
      excuse_reason: attendance.excuse_reason ?? null,
      rpe_omni: attendance.rpe_omni ?? 5,
      rubric_effort: attendance.rubric_effort ?? 3,
      rubric_attitude: attendance.rubric_attitude ?? 3,
      rubric_technique: attendance.rubric_technique ?? 3,
      individual_feedback: attendance.individual_feedback ?? null,
    },
  });

  const formValues = useWatch({ control });
  const currentStatus = formValues.status ?? attendance.status;
  const needsReason = REQUIRES_REASON.includes(currentStatus);
  const rubricEnabled = ALLOWS_RUBRIC.includes(currentStatus) && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";

  const doSave = useCallback(
    (values: AttendanceFormValues) => {
      const payload: AttendanceFormValues = { ...values };
      if (!ALLOWS_RUBRIC.includes(values.status)) {
        payload.rpe_omni = null;
        payload.rubric_effort = null;
        payload.rubric_attitude = null;
        payload.rubric_technique = null;
        payload.individual_feedback = null;
      }
      if (!REQUIRES_REASON.includes(values.status)) {
        payload.excuse_reason = null;
      }
      mutation.mutate(
        { athleteId: attendance.athlete_id, payload },
        {
          onSuccess: () => {
            setSavedIndicator("saved");
            setTimeout(() => setSavedIndicator(null), 1500);
          },
          onError: () => {
            setSavedIndicator("error");
          },
        },
      );
    },
    [attendance.athlete_id, mutation],
  );

  useEffect(() => {
    if (disabled) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSave(formValues as AttendanceFormValues);
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(formValues), disabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTableRowElement>) => {
      const tag = (e.target as HTMLElement).tagName.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
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
      className="group focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
      style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
      data-testid={`attendance-row-${attendance.athlete_id}`}
    >
      {/* Atleta */}
      <td className="px-3 py-2 text-sm font-medium text-charcoal">
        <div className="flex items-center gap-2">
          {athleteName}
          {savedIndicator === "saved" && (
            <CheckCircle2
              size={14}
              className="animate-fade-in text-green-600"
              aria-label="Guardado"
              data-testid="saved-indicator"
            />
          )}
          {savedIndicator === "error" && (
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
        </div>
      </td>

      {/* Estado */}
      <td className="px-3 py-2">
        <select
          {...register("status")}
          disabled={disabled}
          aria-label="Estado de asistencia"
          className="rounded-lg px-2 py-1.5 text-xs text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
        {needsReason ? (
          <input
            {...register("excuse_reason")}
            type="text"
            disabled={disabled}
            placeholder="Razón (requerida)"
            maxLength={300}
            aria-label="Razón de ausencia"
            aria-required="true"
            className="w-full min-w-[140px] rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          />
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

function AttendanceCard({ attendance, sessionId, disabled }: AttendanceRowProps) {
  const [savedIndicator, setSavedIndicator] = useState<"saved" | "error" | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const mutation = useUpdateAttendance(sessionId);

  const { control, register } = useForm<AttendanceFormValues>({
    defaultValues: {
      status: attendance.status,
      excuse_reason: attendance.excuse_reason ?? null,
      rpe_omni: attendance.rpe_omni ?? 5,
      rubric_effort: attendance.rubric_effort ?? 3,
      rubric_attitude: attendance.rubric_attitude ?? 3,
      rubric_technique: attendance.rubric_technique ?? 3,
      individual_feedback: attendance.individual_feedback ?? null,
    },
  });

  const formValues = useWatch({ control });
  const currentStatus = formValues.status ?? attendance.status;
  const needsReason = REQUIRES_REASON.includes(currentStatus);
  const rubricEnabled = ALLOWS_RUBRIC.includes(currentStatus) && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";

  const doSave = useCallback(
    (values: AttendanceFormValues) => {
      const payload: AttendanceFormValues = { ...values };
      if (!ALLOWS_RUBRIC.includes(values.status)) {
        payload.rpe_omni = null;
        payload.rubric_effort = null;
        payload.rubric_attitude = null;
        payload.rubric_technique = null;
        payload.individual_feedback = null;
      }
      if (!REQUIRES_REASON.includes(values.status)) {
        payload.excuse_reason = null;
      }
      mutation.mutate(
        { athleteId: attendance.athlete_id, payload },
        {
          onSuccess: () => {
            setSavedIndicator("saved");
            setTimeout(() => setSavedIndicator(null), 1500);
          },
          onError: () => setSavedIndicator("error"),
        },
      );
    },
    [attendance.athlete_id, mutation],
  );

  useEffect(() => {
    if (disabled) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSave(formValues as AttendanceFormValues);
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(formValues), disabled]);

  const athleteName = attendance.athlete_name ?? `Atleta #${attendance.athlete_id}`;

  return (
    <div
      className="rounded-xl bg-white p-4 space-y-3"
      style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-charcoal">{athleteName}</p>
        <div className="flex items-center gap-2">
          {savedIndicator === "saved" && (
            <CheckCircle2 size={14} className="text-green-600" aria-label="Guardado" />
          )}
          {savedIndicator === "error" && (
            <button
              type="button"
              onClick={() => doSave(formValues as AttendanceFormValues)}
              className="text-xs text-red-600 underline"
            >
              Error — reintentar
            </button>
          )}
          <select
            {...register("status")}
            disabled={disabled}
            aria-label="Estado de asistencia"
            className="rounded-lg px-2 py-1 text-xs text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            {Object.entries(STATUS_LABELS).map(([val, label]) => (
              <option key={val} value={val}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {needsReason && (
        <input
          {...register("excuse_reason")}
          type="text"
          disabled={disabled}
          placeholder="Razón (requerida)"
          maxLength={300}
          aria-label="Razón de ausencia"
          aria-required="true"
          className="w-full rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        />
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
}

export function AttendanceTable({ sessionId, attendances, disabled }: AttendanceTableProps) {
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
          />
        ))}
      </div>

      {/* Desktop: tabla */}
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full text-sm">
          <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
            <tr>
              <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Atleta
              </th>
              <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Estado
              </th>
              <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Razón
              </th>
              <th
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
              />
            ))}
          </tbody>
        </table>
        <p className="mt-1 px-3 pb-2 text-[10px] text-mid-gray">
          Atajo: P=Presente A=Ausente J=Justificado T=Tarde L=Lesionado
        </p>
      </div>
    </>
  );
}
