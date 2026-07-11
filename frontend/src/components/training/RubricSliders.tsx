import type { Control } from "react-hook-form";
import { Controller } from "react-hook-form";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import type { AttendanceFormValues } from "./AttendanceTable";

// OMNI 0-10 (Robertson et al.): even indices map validated adult-OMNI anchors;
// odd indices are documented interpolations so every integer shows one word.
// "Moderado" sits at the midpoint (5) per the scientific reference.
const RPE_LABELS = [
  "Reposo",      // 0
  "Muy fácil",   // 1
  "Fácil",       // 2
  "Ligero",      // 3
  "Algo fácil",  // 4
  "Moderado",    // 5 ← midpoint
  "Algo duro",   // 6
  "Duro",        // 7
  "Muy duro",    // 8
  "Muy muy duro", // 9
  "Máximo",      // 10
];
// Faces aligned: calm/rested (0) → neutral midpoint (5, 😐) → exhausted (10)
const RPE_FACES = ["😴", "😌", "🙂", "😊", "😀", "😐", "🫤", "😮‍💨", "😤", "😩", "🥵"];

const RUBRIC_LABELS: Record<number, string> = {
  1: "Muy bajo",
  2: "Bajo",
  3: "Regular",
  4: "Bueno",
  5: "Excelente",
};

// Discrete steps rendered as ToggleGroup options (replaces native <input type="range">).
const RPE_VALUES = Array.from({ length: 11 }, (_, i) => i); // 0..10
const RUBRIC_VALUES = [1, 2, 3, 4, 5];

// Fixed 48x48 square so every option meets the >=48x48px touch-target minimum
// (constitution III). The parent uses `flex flex-wrap` so the row wraps onto
// additional lines on narrow viewports instead of overflowing or shrinking
// options below the minimum size.
const toggleItemClass =
  "h-12 w-12 shrink-0 rounded-lg border border-[rgba(34,42,53,0.12)] px-0 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white";

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
              <span className="text-xs text-text-disclaimer">
                {val} — {RUBRIC_LABELS[val]}
              </span>
            </div>
            <ToggleGroup
              type="single"
              value={String(val)}
              onValueChange={(v) => {
                if (v) field.onChange(Number(v));
              }}
              disabled={disabled}
              aria-label={label}
              className="flex flex-wrap gap-1.5"
            >
              {RUBRIC_VALUES.map((n) => (
                <ToggleGroupItem
                  key={n}
                  value={String(n)}
                  aria-label={`${label}: ${n} — ${RUBRIC_LABELS[n]}`}
                  className={toggleItemClass}
                >
                  {n}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
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
                <span className="text-xs text-text-disclaimer">
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
              <ToggleGroup
                type="single"
                value={String(val)}
                onValueChange={(v) => {
                  if (v) field.onChange(Number(v));
                }}
                disabled={disabled}
                aria-label="RPE OMNI 0-10"
                className="flex flex-wrap gap-1.5"
              >
                {RPE_VALUES.map((n) => (
                  <ToggleGroupItem
                    key={n}
                    value={String(n)}
                    aria-label={`RPE OMNI 0-10: ${n} — ${RPE_LABELS[n]}`}
                    className={toggleItemClass}
                  >
                    {n}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
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
              className="w-full resize-none rounded-lg px-2.5 py-2 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
            />
          </div>
        )}
      />
    </div>
  );
}
