import { Controller } from "react-hook-form";
import type { Control, FieldErrors } from "react-hook-form";

import { AthletesMultiSelect } from "@/components/training/AthletesMultiSelect";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

interface StepAthletesProps {
  control: Control<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
}

export function StepAthletes({ control, errors }: StepAthletesProps) {
  return (
    <div className="space-y-2" data-testid="session-step-athletes">
      <p className="text-sm text-mid-gray">
        Selecciona los atletas convocados a esta sesión. Debes convocar al menos uno.
      </p>
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
