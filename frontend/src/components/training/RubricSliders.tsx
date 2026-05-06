import type { Control } from "react-hook-form";
import { Controller } from "react-hook-form";

import type { AttendanceFormValues } from "./AttendanceTable";

const RPE_FACES = ["😴", "😌", "🙂", "😊", "😐", "🫤", "😮‍💨", "😤", "😰", "😩", "🥵"];
const RPE_LABELS = [
  "Reposo",
  "Muy suave",
  "Suave",
  "Moderado",
  "Algo difícil",
  "Difícil",
  "Muy difícil",
  "Muy muy difícil",
  "Extremo",
  "Máximo casi",
  "Máximo",
];

const RUBRIC_LABELS: Record<number, string> = {
  1: "Muy bajo",
  2: "Bajo",
  3: "Regular",
  4: "Bueno",
  5: "Excelente",
};

interface RubricSlidersProps {
  control: Control<AttendanceFormValues>;
  disabled?: boolean;
  feedbackLength: number;
}

function RubricSlider({
  label,
  name,
  control,
  disabled,
}: {
  label: string;
  name: "rubric_effort" | "rubric_attitude" | "rubric_technique";
  control: Control<AttendanceFormValues>;
  disabled?: boolean;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => {
        const val = field.value ?? 3;
        return (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-charcoal">{label}</label>
              <span className="text-xs text-mid-gray">
                {val} — {RUBRIC_LABELS[val]}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={val}
              disabled={disabled}
              aria-label={label}
              aria-valuenow={val}
              aria-valuemin={1}
              aria-valuemax={5}
              onChange={(e) => field.onChange(Number(e.target.value))}
              className="h-1.5 w-full cursor-pointer accent-charcoal disabled:cursor-not-allowed disabled:opacity-40"
            />
            <div className="flex justify-between text-[10px] text-light-gray-dark">
              <span>1</span>
              <span>2</span>
              <span>3</span>
              <span>4</span>
              <span>5</span>
            </div>
          </div>
        );
      }}
    />
  );
}

export function RubricSliders({ control, disabled, feedbackLength }: RubricSlidersProps) {
  return (
    <div className="space-y-3">
      <Controller
        name="rpe_omni"
        control={control}
        render={({ field }) => {
          const val = field.value ?? 5;
          return (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-charcoal">RPE OMNI</label>
                <span className="text-xs text-mid-gray">
                  {val} — {RPE_LABELS[val]}
                </span>
              </div>
              <div className="flex justify-between text-base">
                {RPE_FACES.map((face, i) => (
                  <span
                    key={i}
                    className={`transition-opacity ${i === val ? "opacity-100" : "opacity-30"}`}
                    aria-hidden="true"
                  >
                    {face}
                  </span>
                ))}
              </div>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                value={val}
                disabled={disabled}
                aria-label="RPE OMNI 0-10"
                aria-valuenow={val}
                aria-valuemin={0}
                aria-valuemax={10}
                onChange={(e) => field.onChange(Number(e.target.value))}
                className="h-1.5 w-full cursor-pointer accent-charcoal disabled:cursor-not-allowed disabled:opacity-40"
              />
              <div className="flex justify-between text-[10px] text-mid-gray">
                <span>0</span>
                <span>5</span>
                <span>10</span>
              </div>
            </div>
          );
        }}
      />

      <RubricSlider label="Esfuerzo" name="rubric_effort" control={control} disabled={disabled} />
      <RubricSlider label="Actitud" name="rubric_attitude" control={control} disabled={disabled} />
      <RubricSlider label="Técnica" name="rubric_technique" control={control} disabled={disabled} />

      <Controller
        name="individual_feedback"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-charcoal">Comentario</label>
              <span className="text-[10px] text-mid-gray">{feedbackLength}/500</span>
            </div>
            <textarea
              {...field}
              value={field.value ?? ""}
              disabled={disabled}
              rows={2}
              maxLength={500}
              placeholder="Observaciones del coach…"
              aria-label="Comentario del coach"
              className="w-full resize-none rounded-lg px-2.5 py-2 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            />
          </div>
        )}
      />
    </div>
  );
}
