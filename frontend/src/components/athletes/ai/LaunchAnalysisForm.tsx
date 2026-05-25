/**
 * LaunchAnalysisForm — form para que coach/admin lance un nuevo
 * análisis de race-results para el atleta (FE-1).
 *
 * Inputs:
 *   - season (select de años disponibles)
 *   - valida_nums (grid de checkboxes 1-7 + Cto. Departamental)
 *   - explain_mode (switch HTML nativo)
 *
 * Submit dispara `useLaunchAthleteAnalysis(athleteId)`. Al éxito:
 *   - Invalida runs/insights del atleta (lo hace el hook)
 *   - Llama `onStarted(run_id)` para que el padre cambie a la pestaña
 *     "Histórico" o muestre el `AnalysisRunTimeline` arriba.
 *
 * El nombre del deportista se muestra read-only (UX: confirmar que es
 * el correcto antes de gastar tokens de LLM).
 */
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Play, User as UserIcon } from "lucide-react";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";
import { cn } from "@/lib/utils";

/* shadow-card utility */
const VALIDA_CHOICES: Array<{ value: number; label: string }> = [
  { value: 1, label: "I" },
  { value: 2, label: "II" },
  { value: 3, label: "III" },
  { value: 4, label: "IV" },
  { value: 5, label: "V" },
  { value: 6, label: "VI" },
  { value: 7, label: "VII" },
  { value: 99, label: "CD" },
];

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

const launchSchema = z.object({
  season: z
    .number({ message: "Temporada requerida" })
    .int()
    .min(2020)
    .max(2100),
  valida_nums: z.array(z.number().int().min(1).max(99)),
  explain_mode: z.boolean(),
});

type LaunchFormValues = z.infer<typeof launchSchema>;

interface LaunchAnalysisFormProps {
  athleteId: number;
  athleteName: string;
  onStarted?: (runId: string) => void;
}

export function LaunchAnalysisForm({
  athleteId,
  athleteName,
  onStarted,
}: LaunchAnalysisFormProps) {
  const mutation = useLaunchAthleteAnalysis(athleteId);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    reset,
    register,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LaunchFormValues>({
    resolver: zodResolver(launchSchema),
    defaultValues: {
      season: getDefaultSeason(),
      valida_nums: [],
      explain_mode: false,
    },
  });

  const watchedValidaNums = watch("valida_nums");

  const onSubmit = async (values: LaunchFormValues) => {
    setSubmitError(null);
    try {
      const result = await mutation.mutateAsync({
        season: values.season,
        valida_nums:
          values.valida_nums.length > 0 ? values.valida_nums : null,
        explain_mode: values.explain_mode,
      });
      reset({
        season: values.season,
        valida_nums: [],
        explain_mode: false,
      });
      onStarted?.(result.run_id);
    } catch (err) {
      setSubmitError(
        err instanceof Error
          ? err.message
          : "Error iniciando el análisis. Revisa los datos e intenta de nuevo.",
      );
    }
  };

  const toggleValida = (value: number) => {
    const current = watchedValidaNums ?? [];
    if (current.includes(value)) {
      setValue(
        "valida_nums",
        current.filter((v) => v !== value),
        { shouldValidate: true },
      );
    } else {
      setValue("valida_nums", [...current, value].sort((a, b) => a - b), {
        shouldValidate: true,
      });
    }
  };

  const seasonOptions = (() => {
    const cur = getDefaultSeason();
    const arr: number[] = [];
    for (let y = cur; y >= 2024; y--) arr.push(y);
    return arr;
  })();

  const isDisabled = isSubmitting || mutation.isPending;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="rounded-xl bg-white p-5 space-y-5"
      aria-label="Lanzar análisis IA"
      data-testid="launch-analysis-form"
    >
      <h3
        className="flex items-center gap-2 text-base text-charcoal font-heading"
      >
        <Play size={16} aria-hidden="true" />
        Lanzar análisis IA
      </h3>

      {/* Atleta read-only */}
      <div className="flex items-center gap-3 rounded-lg bg-light-gray/30 px-3 py-2">
        <UserIcon size={16} className="text-mid-gray" aria-hidden="true" />
        <span className="text-sm font-medium text-charcoal">{athleteName}</span>
        <Badge variant="secondary" className="ml-auto">
          ID interno protegido
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Season */}
        <div>
          <label
            htmlFor="launch-season"
            className="block text-xs font-medium text-mid-gray"
          >
            Temporada
          </label>
          <Controller
            control={control}
            name="season"
            render={({ field }) => (
              <select
                {...field}
                onChange={(e) => field.onChange(Number(e.target.value))}
                id="launch-season"
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                data-testid="launch-season-select"
              >
                {seasonOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            )}
          />
          {errors.season && (
            <p className="mt-1 text-xs text-red-600" role="alert">
              {errors.season.message}
            </p>
          )}
        </div>

        {/* Explain mode */}
        <div className="flex items-end">
          <label
            htmlFor="launch-explain"
            className="flex w-full cursor-pointer items-center justify-between rounded-lg bg-light-gray/30 px-3 py-2"
          >
            <span className="flex-1">
              <span className="block text-sm font-medium text-charcoal">
                Modo explicativo
              </span>
              <span className="block text-xs text-mid-gray">
                El agente pausará para tu aprobación en cada paso.
              </span>
            </span>
            <input
              id="launch-explain"
              type="checkbox"
              role="switch"
              {...register("explain_mode")}
              className="h-5 w-5 cursor-pointer accent-charcoal"
              data-testid="launch-explain-switch"
            />
          </label>
        </div>
      </div>

      {/* Valida nums — grid de chips clickeables */}
      <fieldset className="space-y-2">
        <legend className="text-xs font-medium text-mid-gray">
          Válidas a analizar
        </legend>
        <p className="text-[11px] text-mid-gray">
          Deja vacío para analizar todas las válidas disponibles de la
          temporada.
        </p>
        <div
          className="flex flex-wrap gap-2"
          role="group"
          aria-label="Selecciona una o más válidas"
        >
          {VALIDA_CHOICES.map((c) => {
            const isChecked = watchedValidaNums?.includes(c.value);
            return (
              <button
                key={c.value}
                type="button"
                onClick={() => toggleValida(c.value)}
                aria-pressed={isChecked}
                data-testid={`launch-valida-${c.value}`}
                className={cn(
                  "min-h-9 rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
                  isChecked
                    ? "bg-charcoal text-white"
                    : "bg-light-gray/40 text-charcoal hover:bg-light-gray/60",
                )}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      {submitError && (
        <p className="text-sm text-red-600" role="alert">
          {submitError}
        </p>
      )}

      <div className="flex items-center justify-end gap-3">
        <button
          type="submit"
          disabled={isDisabled}
          data-testid="launch-submit"
          className={cn(
            "inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity",
            isDisabled ? "cursor-not-allowed opacity-60" : "hover:opacity-90",
          )}
        >
          {isDisabled ? (
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Play size={16} aria-hidden="true" />
          )}
          {isDisabled ? "Lanzando…" : "Analizar deportista"}
        </button>
      </div>
    </form>
  );
}
