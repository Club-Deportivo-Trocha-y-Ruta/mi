/**
 * Formulario para iniciar un análisis race-results (race-analysis §10.2).
 *
 * Inputs: athlete_id, season, valida_nums (CSV), explain_mode toggle.
 * use_case se diferirá a futuro — el backend lo decide vía heurística.
 *
 * Submit dispara `useStartRun` y el padre (RaceAnalysisPage) navega o
 * actualiza la pestaña "Runs activos" con el run_id devuelto.
 *
 * Validación liviana con Zod inline (sin schemas file para no
 * proliferar archivos para un solo form).
 */
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Play } from "lucide-react";
import { z } from "zod";

import { useStartRun } from "@/hooks/ai/useRaceRun";
import { useExplainModeStore } from "@/store/explainMode.store";
import { cn } from "@/lib/utils";

/** Schema string-based: react-hook-form maneja inputs como strings y
 * Zod los valida + transforma a números. */
const startRunSchema = z.object({
  athlete_id: z
    .string()
    .min(1, "Athlete ID requerido")
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 1, "Athlete ID inválido"),
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
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<StartRunFormValues>({
    resolver: zodResolver(startRunSchema),
    defaultValues: {
      athlete_id: "",
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
      <div>
        <h2 className="text-base font-semibold text-charcoal">
          Iniciar análisis
        </h2>
        <p className="mt-0.5 text-xs text-mid-gray">
          El agente combinará datos de carrera con principios LTAD del marco
          teórico.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="athlete_id"
            className="block text-xs font-medium uppercase tracking-wide text-mid-gray"
          >
            Athlete ID
          </label>
          <input
            id="athlete_id"
            type="number"
            min={1}
            {...register("athlete_id")}
            className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="start-run-athlete-id"
          />
          {errors.athlete_id && (
            <p className="mt-1 text-xs text-red-600" role="alert">
              {errors.athlete_id.message}
            </p>
          )}
        </div>

        <div>
          <label
            htmlFor="season"
            className="block text-xs font-medium uppercase tracking-wide text-mid-gray"
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
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="start-run-season"
          />
          {errors.season && (
            <p className="mt-1 text-xs text-red-600" role="alert">
              {errors.season.message}
            </p>
          )}
        </div>

        <div className="sm:col-span-2">
          <label
            htmlFor="valida_nums_csv"
            className="block text-xs font-medium uppercase tracking-wide text-mid-gray"
          >
            Válidas (CSV, opcional)
          </label>
          <input
            id="valida_nums_csv"
            type="text"
            placeholder="ej: 1,2,3,4 — vacío = todas las de la temporada"
            {...register("valida_nums_csv")}
            className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
        Iniciar análisis
      </button>
    </form>
  );
}
