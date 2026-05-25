/**
 * Formulario para iniciar un análisis race-results (race-analysis §10.2).
 *
 * Inputs: athlete (combobox), season, valida_nums (CSV), explain_mode toggle.
 * use_case se diferirá a futuro — el backend lo decide vía heurística.
 *
 * Submit dispara `useStartRun` y el padre (RaceAnalysisPage) navega o
 * actualiza la pestaña "Runs activos" con el run_id devuelto.
 *
 * UX: el coach no maneja IDs numéricos — selecciona deportistas por nombre
 * vía AthleteCombobox. El form sigue enviando `athlete_id` al backend.
 */
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { HelpCircle, Loader2, Play } from "lucide-react";
import { z } from "zod";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { useStartRun } from "@/hooks/ai/useRaceRun";
import { useExplainModeStore } from "@/store/explainMode.store";
import { cn } from "@/lib/utils";

/** Schema: athlete_id es number (lo setea el combobox), season y valida son
 * strings que se transforman en submit. */
const startRunSchema = z.object({
  athlete_id: z
    .number({ message: "Selecciona un deportista del listado" })
    .int()
    .positive("Selecciona un deportista del listado"),
  season: z
    .string()
    .min(1, "Temporada requerida")
    .refine(
      (v) => /^\d+$/.test(v) && Number(v) >= 2020 && Number(v) <= 2100,
      "Temporada inválida (2020-2100)",
    ),
  valida_nums_csv: z
    .string()
    .optional()
    .refine((v) => {
      if (!v || v.trim().length === 0) return true;
      const parts = v.split(",").map((s) => s.trim());
      return parts.every((p) => /^\d+$/.test(p) && Number(p) >= 1 && Number(p) <= 12);
    }, "Lista de válidas inválida (números 1-12 separados por coma)"),
});

type StartRunFormValues = z.infer<typeof startRunSchema>;

interface StartRunFormProps {
  /** Callback al recibir run_id del backend. */
  onStarted?: (runId: string) => void;
  className?: string;
}

export function StartRunForm({ onStarted, className }: StartRunFormProps) {
  const mutation = useStartRun();
  const explainEnabled = useExplainModeStore((s) => s.enabled);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<StartRunFormValues>({
    resolver: zodResolver(startRunSchema),
    defaultValues: {
      // undefined fuerza al usuario a seleccionar antes de poder enviar.
      athlete_id: undefined as unknown as number,
      season: String(new Date().getFullYear()),
      valida_nums_csv: "",
    },
  });

  const onSubmit = async (values: StartRunFormValues) => {
    setSubmitError(null);
    const valida_nums = values.valida_nums_csv
      ? values.valida_nums_csv
          .split(",")
          .map((s) => Number(s.trim()))
          .filter((n) => !Number.isNaN(n))
      : null;
    try {
      const result = await mutation.mutateAsync({
        athlete_id: Number(values.athlete_id),
        season: Number(values.season),
        valida_nums,
        explain_mode: explainEnabled,
      });
      reset();
      onStarted?.(result.run_id);
    } catch (err) {
      setSubmitError(
        err instanceof Error
          ? err.message
          : "Error iniciando el análisis (revisa los datos).",
      );
    }
  };

  const cardStyle: React.CSSProperties = {
    boxShadow:
      "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className={cn("rounded-xl bg-white p-5 space-y-4", className)}
      style={cardStyle}
      data-testid="start-run-form"
      aria-label="Iniciar análisis de carrera"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold text-charcoal">
          Iniciar análisis
        </h2>
        <span
          role="img"
          className="inline-flex items-center text-mid-gray"
          title="El agente combinará datos de carrera con principios LTAD del marco teórico."
          aria-label="El agente combinará datos de carrera con principios LTAD del marco teórico"
          data-testid="start-run-help"
        >
          <HelpCircle size={14} aria-hidden="true" />
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Controller
            control={control}
            name="athlete_id"
            render={({ field }) => (
              <AthleteCombobox
                id="athlete_id"
                label="Deportista"
                value={field.value ?? null}
                onChange={(id) => field.onChange(id ?? undefined)}
                error={errors.athlete_id?.message}
                data-testid="start-run-athlete-combobox"
              />
            )}
          />
        </div>

        <div>
          <label
            htmlFor="season"
            className="block text-xs font-medium text-mid-gray"
          >
            Temporada
          </label>
          <input
            id="season"
            type="number"
            min={2020}
            max={2100}
            {...register("season")}
            className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
            data-testid="start-run-season"
          />
          {errors.season && (
            <p className="mt-1 text-xs text-red-600" role="alert">
              {errors.season.message}
            </p>
          )}
        </div>

        <div>
          <label
            htmlFor="valida_nums_csv"
            className="block text-xs font-medium text-mid-gray"
          >
            Válidas (CSV, opcional)
          </label>
          <input
            id="valida_nums_csv"
            type="text"
            placeholder="ej: 1,2,3,4 — vacío = todas"
            {...register("valida_nums_csv")}
            className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
            data-testid="start-run-valida-nums"
          />
          {errors.valida_nums_csv && (
            <p className="mt-1 text-xs text-red-600" role="alert">
              {errors.valida_nums_csv.message}
            </p>
          )}
        </div>
      </div>

      {explainEnabled && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Modo aprendizaje activo — el agente pausará en cada paso clave
          para tu aprobación.
        </p>
      )}

      {submitError && (
        <p className="text-sm text-red-600" role="alert">
          {submitError}
        </p>
      )}

      <button
        type="submit"
        disabled={isSubmitting || mutation.isPending}
        data-testid="start-run-submit"
        className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        ) : (
          <Play size={16} aria-hidden="true" />
        )}
        Analizar deportista
      </button>
    </form>
  );
}
