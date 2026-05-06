import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";

interface ReadOnlyAttendanceRowProps {
  attendance: Attendance;
}

const STATUS_LABELS: Record<AttendanceStatus, string> = {
  presente: "Presente",
  ausente: "Ausente",
  justificado: "Justificado",
  tarde: "Tarde",
  lesionado: "Lesionado",
};

const STATUS_COLORS: Record<AttendanceStatus, string> = {
  presente: "bg-green-100 text-green-800",
  tarde: "bg-amber-100 text-amber-800",
  ausente: "bg-red-100 text-red-700",
  justificado: "bg-blue-100 text-blue-800",
  lesionado: "bg-purple-100 text-purple-800",
};

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

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

export function ReadOnlyAttendanceRow({ attendance }: ReadOnlyAttendanceRowProps) {
  const statusLabel = STATUS_LABELS[attendance.status] ?? attendance.status;
  const statusClass = STATUS_COLORS[attendance.status] ?? "bg-light-gray text-charcoal";

  const hasRubric =
    attendance.rpe_omni != null ||
    attendance.rubric_effort != null ||
    attendance.rubric_attitude != null ||
    attendance.rubric_technique != null;

  return (
    <div
      className="rounded-xl bg-white px-5 py-4 space-y-4"
      style={cardStyle}
      data-athlete-id={attendance.athlete_id}
      aria-label={`Registro de asistencia de ${attendance.athlete_name ?? "atleta"}`}
    >
      {/* Status row */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusClass}`}
          aria-label={`Estado: ${statusLabel}`}
        >
          {statusLabel}
        </span>

        {attendance.athlete_name && (
          <span className="text-sm font-medium text-charcoal">{attendance.athlete_name}</span>
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
