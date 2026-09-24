import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useCreateAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useBodyComposition } from "@/hooks/athletes/useBodyComposition";
import {
  ageFromBirthDate,
  isIntervalBlocked,
  SKINFOLD_MIN_AGE_YEARS,
} from "@/lib/bodyComposition/eligibility";
import { formatDate } from "@/lib/datetime";
import { computeAgeDecimal } from "@/lib/category";
import { calculatePHV, type PHVResult } from "@/lib/phv";
import { PHVBadge } from "@/components/athletes/PHVBadge";
import type { Sex } from "@/types/enums";

const anthropometrySchema = z.object({
  evaluation_date: z
    .string()
    .min(1, "Fecha requerida")
    .refine((v) => v <= new Date().toISOString().slice(0, 10), "No puede ser futura"),
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
  /** "Guardar y terminar" — comportamiento de siempre. */
  onSuccess: () => void;
  /**
   * Feature 046 (T031): segunda salida "Guardar y agregar pliegues". Recibe
   * el id de la evaluación recién creada (el llamador navega al asistente
   * de captura). Si se omite, el formulario conserva su único botón.
   */
  onAddSkinfolds?: (recordId: number) => void;
}

type SubmitIntent = "finish" | "skinfolds";

const inputClass =
  "mt-1 w-full rounded-lg bg-surface-raised px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

export function AnthropometryForm({
  athleteId,
  athleteSex,
  athleteBirthDate,
  onSuccess,
  onAddSkinfolds,
}: AnthropometryFormProps) {
  const createMutation = useCreateAnthropometry(athleteId);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Qué botón disparó el envío (ambos son `type="submit"` del mismo form).
  const intentRef = useRef<SubmitIntent>("finish");
  const [pendingIntent, setPendingIntent] = useState<SubmitIntent | null>(null);
  // `next_due_date` del intervalo mínimo entre sets de pliegues; sólo se
  // consulta cuando la salida de pliegues está habilitada por el llamador.
  const bodyCompositionQuery = useBodyComposition(athleteId, !!onAddSkinfolds);

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

  // Salida "Guardar y agregar pliegues": oculta si el deportista tendría
  // menos de 9 años en la fecha de evaluación o si el intervalo mínimo entre
  // sets la bloquea (el backend vuelve a validar ambas reglas, 409).
  const ageAtDate = evaluationDate ? ageFromBirthDate(athleteBirthDate, evaluationDate) : null;
  const skinfoldsAgeOk = ageAtDate !== null && ageAtDate >= SKINFOLD_MIN_AGE_YEARS;
  const nextDueDate = bodyCompositionQuery.data?.next_due_date ?? null;
  const skinfoldsIntervalBlocked =
    !!evaluationDate && isIntervalBlocked(evaluationDate, nextDueDate);
  const showSkinfoldsExit =
    !!onAddSkinfolds &&
    skinfoldsAgeOk &&
    !bodyCompositionQuery.isLoading &&
    !skinfoldsIntervalBlocked;
  const showIntervalNote = !!onAddSkinfolds && skinfoldsAgeOk && skinfoldsIntervalBlocked;

  const handleSubmit = async (values: AnthropometryFormValues) => {
    setSubmitError(null);
    const intent = intentRef.current;
    setPendingIntent(intent);
    try {
      const created = await createMutation.mutateAsync({
        evaluation_date: values.evaluation_date,
        weight_kg: values.weight_kg,
        standing_height_cm: values.standing_height_cm,
        arm_span_cm: values.arm_span_cm && !Number.isNaN(values.arm_span_cm) ? values.arm_span_cm : null,
        sitting_height_cm: values.sitting_height_cm,
      });
      form.reset();
      if (intent === "skinfolds" && onAddSkinfolds && created?.id) {
        onAddSkinfolds(created.id);
      } else {
        onSuccess();
      }
    } catch {
      setSubmitError("No se pudo guardar la medición. Intenta de nuevo.");
    } finally {
      intentRef.current = "finish";
      setPendingIntent(null);
    }
  };

  return (
    <div className="space-y-5">
      <form
        onSubmit={form.handleSubmit((v) => void handleSubmit(v))}
        className="space-y-5"
      >
        {/* Fecha */}
        <div>
          <label className="text-sm font-medium text-charcoal">
            Fecha de evaluación
            <input
              type="date"
              className={`${inputClass} md:w-64`}
              max={new Date().toISOString().slice(0, 10)}
              {...form.register("evaluation_date")}
            />
            <span className="text-xs text-red-600">
              {form.formState.errors.evaluation_date?.message}
            </span>
          </label>
        </div>

        {/* Grid de medidas */}
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
          <label className="text-sm font-medium text-charcoal">
            Peso (kg)
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              className={inputClass}
              {...form.register("weight_kg", { valueAsNumber: true })}
            />
            <span className="text-xs text-red-600">
              {form.formState.errors.weight_kg?.message}
            </span>
          </label>
          <label className="text-sm font-medium text-charcoal">
            Talla de pie (cm)
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              className={inputClass}
              {...form.register("standing_height_cm", { valueAsNumber: true })}
            />
            <span className="text-xs text-red-600">
              {form.formState.errors.standing_height_cm?.message}
            </span>
          </label>
          <label className="text-sm font-medium text-charcoal">
            Envergadura (cm)
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              className={inputClass}
              {...form.register("arm_span_cm", { valueAsNumber: true })}
              placeholder="Opcional"
            />
          </label>
          <label className="text-sm font-medium text-charcoal">
            Talla sentado (cm)
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              className={inputClass}
              {...form.register("sitting_height_cm", { valueAsNumber: true })}
            />
            <span className="text-xs text-red-600">
              {form.formState.errors.sitting_height_cm?.message}
            </span>
          </label>
        </div>

        {submitError && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{submitError}</p>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <button
            type="submit"
            disabled={createMutation.isPending}
            onClick={() => {
              intentRef.current = "finish";
            }}
            className="min-h-[48px] rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-surface transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight"
          >
            {createMutation.isPending && pendingIntent !== "skinfolds"
              ? "Guardando..."
              : showSkinfoldsExit
                ? "Guardar y terminar"
                : "Guardar medición"}
          </button>
          {showSkinfoldsExit && (
            <button
              type="submit"
              disabled={createMutation.isPending}
              onClick={() => {
                intentRef.current = "skinfolds";
              }}
              className="min-h-[48px] rounded-lg bg-surface-raised px-4 py-2 text-sm font-medium text-charcoal ring-1 ring-hairline transition-colors hover:bg-light-gray disabled:opacity-50"
            >
              {createMutation.isPending && pendingIntent === "skinfolds"
                ? "Guardando..."
                : "Guardar y agregar pliegues"}
            </button>
          )}
        </div>
        {showIntervalNote && nextDueDate && (
          <p className="text-xs text-mid-gray" data-testid="skinfolds-interval-note">
            Pliegues cutáneos: la próxima toma puede hacerse desde el{" "}
            {formatDate(`${nextDueDate.slice(0, 10)}T12:00:00`)}.
          </p>
        )}
      </form>

      {/* Panel PHV en tiempo real */}
      <div
        className="rounded-xl bg-light-gray p-4"
        data-testid="phv-preview"
      >
        <h3
          className="font-display mb-3 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          Cálculo PHV (en tiempo real)
        </h3>
        {phvResult ? (
          <div className="grid gap-2 text-sm text-charcoal md:grid-cols-2">
            <p data-testid="leg-length">Longitud pierna: {phvResult.legLengthCm} cm</p>
            <p>Ratio pierna/sentado: {phvResult.legSittingRatio}</p>
            <p data-testid="maturity-offset">
              Maturity Offset:{" "}
              {phvResult.maturityOffset > 0
                ? `+${phvResult.maturityOffset}`
                : phvResult.maturityOffset}
            </p>
            <p data-testid="age-at-phv">Edad al PHV: {phvResult.ageAtPhv} años</p>
            <div className="flex items-center gap-2" data-testid="maturation-status">
              <span>Estado:</span>
              <PHVBadge status={phvResult.maturationStatus} />
            </div>
            <p className="md:col-span-2 rounded-lg bg-surface-raised p-2.5 text-xs text-mid-gray">
              {phvResult.trainingImplications}
            </p>
          </div>
        ) : (
          <p className="text-sm text-mid-gray">
            Completa los campos para ver el cálculo.
          </p>
        )}
      </div>
    </div>
  );
}
