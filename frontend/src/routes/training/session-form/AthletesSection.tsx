/**
 * AthletesSection — Sección "Atletas convocados" del formulario de sesión.
 *
 * Wrapper de AthletesMultiSelect con label de sección. Extraída de
 * SessionFormPage en B5.
 */
import { Controller, type Control, type FieldErrors } from "react-hook-form";

import { AthletesMultiSelect } from "@/components/training/AthletesMultiSelect";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

export interface AthletesSectionProps {
  control: Control<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
}

export function AthletesSection({ control, errors }: AthletesSectionProps) {
  return (
    <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
      <h2 className="text-base font-semibold text-charcoal">Atletas convocados</h2>
      <Controller
        name="convocados_athlete_ids"
        control={control}
        render={({ field }) => (
          <AthletesMultiSelect
            value={field.value}
            onChange={field.onChange}
            error={errors.convocados_athlete_ids?.message}
          />
        )}
      />
    </div>
  );
}
