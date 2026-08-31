import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

interface StepReviewProps {
  values: TrainingSessionFormValues;
  athleteCount: number;
  routeFileName: string | null;
  notify: boolean;
  onNotifyChange: (next: boolean) => void;
}

export function StepReview({
  values,
  athleteCount,
  routeFileName,
  notify,
  onNotifyChange,
}: StepReviewProps) {
  const rows: { label: string; value: string }[] = [
    { label: "Fecha", value: values.scheduled_date || "—" },
    { label: "Hora", value: values.scheduled_start_time || "—" },
    { label: "Duración", value: `${values.duration_min} min` },
    { label: "Lugar", value: values.location || "—" },
    { label: "Foco técnico", value: values.technical_focus || "—" },
    { label: "Atletas convocados", value: String(athleteCount) },
    { label: "Archivo de recorrido", value: routeFileName ?? "Ninguno" },
  ];

  return (
    <div className="space-y-4" data-testid="session-step-review">
      <p className="text-sm text-mid-gray">
        Revisa el resumen antes de guardar la sesión.
      </p>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg bg-light-gray/40 p-4 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-3 text-sm">
            <dt className="text-mid-gray">{r.label}</dt>
            <dd className="text-right font-medium text-charcoal">{r.value}</dd>
          </div>
        ))}
      </dl>

      <label className="flex min-h-[48px] cursor-pointer items-center gap-3 rounded-lg bg-white px-3 py-2 shadow-ring">
        <input
          type="checkbox"
          checked={notify}
          onChange={(e) => onNotifyChange(e.target.checked)}
          className="h-5 w-5 rounded border-mid-gray text-charcoal"
          data-testid="notify-parents-checkbox"
        />
        <span className="text-sm text-charcoal">
          Notificar a las familias de los atletas convocados por correo.
        </span>
      </label>
    </div>
  );
}
