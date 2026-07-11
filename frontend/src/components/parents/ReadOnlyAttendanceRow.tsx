import { ATTENDANCE_LABELS, ATTENDANCE_TONE } from "@/lib/attendanceStatus";
import type { Attendance } from "@/types/trainingSession.types";

interface ReadOnlyAttendanceRowProps {
  attendance: Attendance;
  athleteName: string;
}

function StatMini({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-lg bg-light-gray px-3 py-2 text-center">
      <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">{label}</p>
      <p className="mt-0.5 text-base font-semibold text-charcoal">
        {value != null ? String(value) : "—"}
      </p>
    </div>
  );
}

export function ReadOnlyAttendanceRow({ attendance, athleteName }: ReadOnlyAttendanceRowProps) {
  const statusLabel = ATTENDANCE_LABELS[attendance.status] ?? attendance.status;
  const statusClass = ATTENDANCE_TONE[attendance.status] ?? "bg-light-gray text-charcoal";

  const hasRubric =
    attendance.rpe_omni != null ||
    attendance.rubric_effort != null ||
    attendance.rubric_attitude != null ||
    attendance.rubric_technique != null;

  return (
    <div
      className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card"
      data-athlete-id={attendance.athlete_id}
      aria-label={`Registro de asistencia de ${athleteName}`}
    >
      {/* Status row */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusClass}`}
          aria-label={`Estado: ${statusLabel}`}
        >
          {statusLabel}
        </span>

        {athleteName && (
          <span className="text-sm font-medium text-charcoal">{athleteName}</span>
        )}
      </div>

      {/* Razón (si ausente/justificado/lesionado) */}
      {attendance.excuse_reason && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-1">Razón</p>
          <p className="text-sm text-charcoal">{attendance.excuse_reason}</p>
        </div>
      )}

      {/* Rúbrica — solo si hay datos */}
      {hasRubric ? (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-2">
            Evaluación de la sesión
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatMini label="RPE" value={attendance.rpe_omni != null ? `${attendance.rpe_omni}/10` : null} />
            <StatMini label="Esfuerzo" value={attendance.rubric_effort != null ? `${attendance.rubric_effort}/5` : null} />
            <StatMini label="Actitud" value={attendance.rubric_attitude != null ? `${attendance.rubric_attitude}/5` : null} />
            <StatMini label="Técnica" value={attendance.rubric_technique != null ? `${attendance.rubric_technique}/5` : null} />
          </div>
        </div>
      ) : (
        <p className="text-xs text-mid-gray italic">
          Aún no se ha registrado evaluación para esta sesión.
        </p>
      )}

      {/* Comentario individual */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-1">
          Comentario del entrenador
        </p>
        {attendance.individual_feedback ? (
          <p className="text-sm text-charcoal whitespace-pre-line">
            {attendance.individual_feedback}
          </p>
        ) : (
          <div className="rounded-lg bg-light-gray px-3 py-2">
            <p className="text-sm text-mid-gray italic">Sin comentario aún.</p>
          </div>
        )}
      </div>
    </div>
  );
}
