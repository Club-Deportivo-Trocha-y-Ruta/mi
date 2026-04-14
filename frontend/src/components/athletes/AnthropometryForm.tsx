import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useCreateAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { computeAgeDecimal } from "@/lib/category";
import { calculatePHV, type PHVResult } from "@/lib/phv";
import { PHVBadge } from "@/components/shared/PHVBadge";
import type { Sex } from "@/types/enums";

const anthropometrySchema = z.object({
  evaluation_date: z
    .string()
    .min(1, "Fecha requerida")
    .refine((v) => new Date(v).getTime() <= Date.now(), "No puede ser futura"),
  weight_kg: z.number().min(20, "Min 20 kg").max(150, "Max 150 kg"),
  standing_height_cm: z.number().min(100, "Min 100 cm").max(220, "Max 220 cm"),
  arm_span_cm: z
    .union([z.number().min(100).max(220), z.nan()])
    .optional()
    .nullable(),
  sitting_height_cm: z.number().min(50, "Min 50 cm").max(120, "Max 120 cm"),
});

type AnthropometryFormValues = z.output<typeof anthropometrySchema>;

interface AnthropometryFormProps {
  athleteId: number;
  athleteSex: Sex;
  athleteBirthDate: string;
  onSuccess: () => void;
}

export function AnthropometryForm({
  athleteId,
  athleteSex,
  athleteBirthDate,
  onSuccess,
}: AnthropometryFormProps) {
  const createMutation = useCreateAnthropometry(athleteId);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<z.input<typeof anthropometrySchema>, unknown, AnthropometryFormValues>({
    resolver: zodResolver(anthropometrySchema),
    defaultValues: {
      evaluation_date: new Date().toISOString().slice(0, 10),
      weight_kg: undefined as unknown as number,
      standing_height_cm: undefined as unknown as number,
      arm_span_cm: null,
      sitting_height_cm: undefined as unknown as number,
    },
  });

  const evaluationDate = form.watch("evaluation_date");
  const weightKg = form.watch("weight_kg");
  const standingHeightCm = form.watch("standing_height_cm");
  const sittingHeightCm = form.watch("sitting_height_cm");

  const phvResult = useMemo<PHVResult | null>(() => {
    if (!evaluationDate || !weightKg || !standingHeightCm || !sittingHeightCm) {
      return null;
    }
    const evalDate = new Date(`${evaluationDate}T00:00:00`);
    const birthDate = new Date(`${athleteBirthDate}T00:00:00`);
    if (Number.isNaN(evalDate.getTime()) || Number.isNaN(birthDate.getTime())) {
      return null;
    }
    const ageDecimal = computeAgeDecimal(birthDate, evalDate);
    return calculatePHV({
      sex: athleteSex,
      ageDecimal,
      weightKg,
      standingHeightCm,
      sittingHeightCm,
    });
  }, [evaluationDate, weightKg, standingHeightCm, sittingHeightCm, athleteSex, athleteBirthDate]);

  const handleSubmit = async (values: AnthropometryFormValues) => {
    setSubmitError(null);
    try {
      await createMutation.mutateAsync({
        evaluation_date: values.evaluation_date,
        weight_kg: values.weight_kg,
        standing_height_cm: values.standing_height_cm,
        arm_span_cm: values.arm_span_cm && !Number.isNaN(values.arm_span_cm) ? values.arm_span_cm : null,
        sitting_height_cm: values.sitting_height_cm,
      });
      form.reset();
      onSuccess();
    } catch {
      setSubmitError("No se pudo guardar la medicion. Intenta de nuevo.");
    }
  };

  return (
    <div className="space-y-4">
      <form
        onSubmit={form.handleSubmit((v) => void handleSubmit(v))}
        className="space-y-4"
      >
        <div>
          <label className="text-sm text-slate-700">
            Fecha de evaluacion
            <input
              type="date"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 md:w-64"
              {...form.register("evaluation_date")}
            />
            <span className="text-xs text-rose-600">
              {form.formState.errors.evaluation_date?.message}
            </span>
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm text-slate-700">
            Peso (kg)
            <input
              type="number"
              step="0.1"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("weight_kg", { valueAsNumber: true })}
            />
            <span className="text-xs text-rose-600">
              {form.formState.errors.weight_kg?.message}
            </span>
          </label>
          <label className="text-sm text-slate-700">
            Talla de pie (cm)
            <input
              type="number"
              step="0.1"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("standing_height_cm", { valueAsNumber: true })}
            />
            <span className="text-xs text-rose-600">
              {form.formState.errors.standing_height_cm?.message}
            </span>
          </label>
          <label className="text-sm text-slate-700">
            Envergadura (cm)
            <input
              type="number"
              step="0.1"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("arm_span_cm", { valueAsNumber: true })}
              placeholder="Opcional"
            />
          </label>
          <label className="text-sm text-slate-700">
            Talla sentado (cm)
            <input
              type="number"
              step="0.1"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("sitting_height_cm", { valueAsNumber: true })}
            />
            <span className="text-xs text-rose-600">
              {form.formState.errors.sitting_height_cm?.message}
            </span>
          </label>
        </div>

        {submitError && <p className="text-sm text-rose-600">{submitError}</p>}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800 disabled:opacity-60"
        >
          {createMutation.isPending ? "Guardando..." : "Guardar medicion"}
        </button>
      </form>

      {/* Panel PHV en tiempo real */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="phv-preview">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">
          Calculo PHV (en tiempo real)
        </h3>
        {phvResult ? (
          <div className="grid gap-2 text-sm text-slate-700 md:grid-cols-2">
            <p data-testid="leg-length">Longitud pierna: {phvResult.legLengthCm} cm</p>
            <p>Ratio pierna/sentado: {phvResult.legSittingRatio}</p>
            <p data-testid="maturity-offset">
              Maturity Offset:{" "}
              {phvResult.maturityOffset > 0
                ? `+${phvResult.maturityOffset}`
                : phvResult.maturityOffset}
            </p>
            <p data-testid="age-at-phv">Edad al PHV: {phvResult.ageAtPhv} anos</p>
            <div className="flex items-center gap-2" data-testid="maturation-status">
              <span>Estado:</span>
              <PHVBadge status={phvResult.maturationStatus} />
            </div>
            <p className="md:col-span-2 rounded-md bg-white p-2 text-xs text-slate-600">
              {phvResult.trainingImplications}
            </p>
          </div>
        ) : (
          <p className="text-sm text-slate-500">
            Completa los campos para ver el calculo.
          </p>
        )}
      </div>
    </div>
  );
}
