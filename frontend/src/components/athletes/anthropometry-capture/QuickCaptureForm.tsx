import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm, type UseFormReturn } from "react-hook-form";

import { BenchHeightField } from "./BenchHeightField";
import { DecimalInput } from "./DecimalInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getBenchHeightCm } from "@/lib/anthropometry/devicePrefs";
import {
  anthropometryCaptureSchema,
  todayISO,
  type AnthropometryCaptureValues,
} from "@/schemas/anthropometryCapture.schema";

export interface QuickCaptureFormProps {
  /** Valores iniciales (p. ej. al editar: talla sentado neta y banco 0). */
  defaultValues?: Partial<AnthropometryCaptureValues>;
  /** Recibe los valores validados (talla sentado BRUTA; usar `toAnthropometryPayload`). */
  onReview: (values: AnthropometryCaptureValues) => void;
  /** @default "Revisar y guardar" */
  submitLabel?: string;
  /** Fecha fija (jornada grupal). */
  dateLocked?: boolean;
  /** Persistir el banco en el dispositivo; en edición, false. @default true */
  persistBench?: boolean;
  isPending?: boolean;
  /**
   * Formulario compartido con el padre (p. ej. el asistente guiado) para que
   * los valores sobrevivan al cambiar de modo. Sin él, el componente crea el suyo.
   */
  form?: UseFormReturn<AnthropometryCaptureValues>;
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-danger">
      {message}
    </p>
  );
}

/**
 * Captura rápida (feature 048): cuadrícula de una sola pantalla con fecha,
 * peso, talla de pie, talla sentado (con banco) y envergadura opcional.
 * Una columna en teléfono; 2 columnas desde `sm`.
 */
export function QuickCaptureForm({
  defaultValues,
  onReview,
  submitLabel = "Revisar y guardar",
  dateLocked = false,
  persistBench = true,
  isPending = false,
  form: sharedForm,
}: QuickCaptureFormProps) {
  const ownForm = useForm<AnthropometryCaptureValues>({
    resolver: zodResolver(anthropometryCaptureSchema),
    defaultValues: {
      evaluation_date: todayISO(),
      weight_kg: undefined,
      standing_height_cm: undefined,
      sitting_height_cm: undefined,
      arm_span_cm: null,
      bench_height_cm: persistBench ? getBenchHeightCm() : 0,
      notes: null,
      ...defaultValues,
    },
  });
  const form = sharedForm ?? ownForm;
  const { control, register, handleSubmit, watch, formState } = form;
  const errors = formState.errors;
  const gross = watch("sitting_height_cm");
  const today = todayISO();

  return (
    <form
      noValidate
      onSubmit={handleSubmit(onReview)}
      className="flex flex-col gap-5"
      aria-label="Captura rápida de medición"
    >
      <div className="flex flex-col gap-1.5 sm:max-w-xs">
        <Label htmlFor="qc-date">Fecha de la medición</Label>
        <Input
          id="qc-date"
          type="date"
          max={today}
          disabled={dateLocked}
          aria-invalid={errors.evaluation_date ? true : undefined}
          aria-describedby={errors.evaluation_date ? "qc-date-error" : undefined}
          {...register("evaluation_date")}
        />
        <FieldError id="qc-date-error" message={errors.evaluation_date?.message} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-weight">Peso (kg)</Label>
          <Controller
            control={control}
            name="weight_kg"
            render={({ field }) => (
              <DecimalInput
                id="qc-weight"
                value={field.value}
                onBlur={field.onBlur}
                aria-invalid={errors.weight_kg ? true : undefined}
                aria-describedby={errors.weight_kg ? "qc-weight-error" : undefined}
                onValueChange={(v) => field.onChange(v as number)}
              />
            )}
          />
          <FieldError id="qc-weight-error" message={errors.weight_kg?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-standing">Talla de pie (cm)</Label>
          <Controller
            control={control}
            name="standing_height_cm"
            render={({ field }) => (
              <DecimalInput
                id="qc-standing"
                value={field.value}
                onBlur={field.onBlur}
                aria-invalid={errors.standing_height_cm ? true : undefined}
                aria-describedby={errors.standing_height_cm ? "qc-standing-error" : undefined}
                onValueChange={(v) => field.onChange(v as number)}
              />
            )}
          />
          <FieldError id="qc-standing-error" message={errors.standing_height_cm?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-sitting">Lectura del tallímetro, sentado (cm)</Label>
          <Controller
            control={control}
            name="sitting_height_cm"
            render={({ field }) => (
              <DecimalInput
                id="qc-sitting"
                value={field.value}
                onBlur={field.onBlur}
                aria-invalid={errors.sitting_height_cm ? true : undefined}
                aria-describedby={errors.sitting_height_cm ? "qc-sitting-error" : undefined}
                onValueChange={(v) => field.onChange(v as number)}
              />
            )}
          />
          <FieldError id="qc-sitting-error" message={errors.sitting_height_cm?.message} />
        </div>

        <Controller
          control={control}
          name="bench_height_cm"
          render={({ field }) => (
            <BenchHeightField
              benchValue={field.value}
              onBenchChange={(v) => field.onChange(v ?? null)}
              grossValue={gross}
              persist={persistBench}
              error={errors.bench_height_cm?.message}
            />
          )}
        />

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-arm-span">Envergadura (cm), opcional</Label>
          <Controller
            control={control}
            name="arm_span_cm"
            render={({ field }) => (
              <DecimalInput
                id="qc-arm-span"
                value={field.value}
                onBlur={field.onBlur}
                aria-invalid={errors.arm_span_cm ? true : undefined}
                aria-describedby={errors.arm_span_cm ? "qc-arm-error" : undefined}
                onValueChange={(v) => field.onChange(v === undefined ? null : v)}
              />
            )}
          />
          <FieldError id="qc-arm-error" message={errors.arm_span_cm?.message} />
        </div>
      </div>

      <Button type="submit" size="lg" disabled={isPending} className="sm:self-start">
        {submitLabel}
      </Button>
    </form>
  );
}
