/**
 * LaunchAnalysisForm — form para que coach/admin lance un nuevo
 * análisis de race-results para el atleta (FE-1).
 *
 * Inputs:
 *   - season (select de años disponibles)
 *   - carreras a analizar (grid de chips poblado con las carreras REALES en las
 *     que el atleta participó esa temporada — vía useAthleteRaces). Cada chip
 *     lleva su event_id; el campeonato (series_kind="championship") ya no usa el
 *     valida_num=99 retirado (feature 014).
 *   - explain_mode (switch HTML nativo)
 *
 * Submit (desambiguado por evento):
 *   - 0 selección → {season, valida_nums: null} → analiza toda la temporada.
 *   - 1 selección → {season, event_id} → ancla por evento (copa o campeonato),
 *     sin ambigüedad cup vs championship (mismo sequence_number).
 *   - >1 selección → {season, valida_nums: [sequence_number...]} (multi-válida
 *     de copa). Si se mezcla el campeonato el backend puede responder 409.
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
import { Loader2, Sparkles, User as UserIcon } from "lucide-react";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";
import { useAthleteRaces } from "@/hooks/athletes/useAthleteRaces";
import { cn } from "@/lib/utils";

const MAX_VALIDA_SELECTION = 4;

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

const launchSchema = z.object({
  season: z
    .number({ message: "Temporada requerida" })
    .int()
    .min(2020)
    .max(2100),
  // Identidad estable por evento (event_id), no por valida_num: evita la
  // ambigüedad copa vs campeonato (mismo sequence_number en la temporada).
  event_ids: z.array(z.number().int().positive()),
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
      event_ids: [],
      explain_mode: false,
    },
  });

  const watchedSeason = watch("season");
  const watchedEventIds = watch("event_ids");

  // Carreras reales del atleta en la temporada → pueblan los chips. Cada chip
  // lleva event_id + sequence_number + series_kind.
  const races = useAthleteRaces(athleteId, watchedSeason);
  const raceOptions = races.data?.items ?? [];

  const onSubmit = async (values: LaunchFormValues) => {
    setSubmitError(null);
    const selected = raceOptions.filter((r) =>
      values.event_ids.includes(r.event_id),
    );
    // Cuerpo desambiguado: 1 evento → event_id; varios → valida_nums (copa).
    const body =
      selected.length === 1
        ? { season: values.season, event_id: selected[0].event_id }
        : {
            season: values.season,
            valida_nums:
              selected.length > 0
                ? selected.map((r) => r.sequence_number)
                : null,
          };
    try {
      const result = await mutation.mutateAsync({
        ...body,
        explain_mode: values.explain_mode,
      });
      reset({
        season: values.season,
        event_ids: [],
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

  const toggleEvent = (eventId: number) => {
    const current = watchedEventIds ?? [];
    if (current.includes(eventId)) {
      setValue(
        "event_ids",
        current.filter((v) => v !== eventId),
        { shouldValidate: true },
      );
    } else {
      // No-op silencioso si ya se alcanzó el cap
      if (current.length >= MAX_VALIDA_SELECTION) return;
      setValue("event_ids", [...current, eventId], { shouldValidate: true });
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
      className={cn("rounded-xl bg-white p-5 space-y-5", "shadow-card")}
      aria-label="Analizar con IA"
      data-testid="launch-analysis-form"
    >
      <h3
        className="font-display flex items-center gap-2 text-base text-charcoal"
      >
        <Sparkles size={16} aria-hidden="true" />
        Analizar con IA
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
                onChange={(e) => {
                  field.onChange(Number(e.target.value));
                  // Los event_ids son de una temporada concreta.
                  setValue("event_ids", [], { shouldValidate: true });
                }}
                id="launch-season"
                className={cn(
                  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
                  "shadow-ring",
                )}
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

      {/* Carreras a analizar — grid de chips poblado con carreras reales */}
      <fieldset className="space-y-2">
        <legend className="text-xs font-medium text-mid-gray">
          Carreras a analizar
        </legend>
        <p className="text-[11px] text-mid-gray">
          Deja vacío para analizar todas las carreras de la temporada. Máximo 4
          por lanzamiento.
        </p>
        {races.isLoading ? (
          <p className="text-xs text-mid-gray" data-testid="launch-races-loading">
            Cargando carreras…
          </p>
        ) : raceOptions.length === 0 ? (
          <p className="text-xs text-mid-gray" data-testid="launch-races-empty">
            Sin carreras registradas para esta temporada.
          </p>
        ) : (
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Selecciona una o más carreras"
          >
            {raceOptions.map((r) => {
              const isChecked = watchedEventIds?.includes(r.event_id);
              const currentLength = watchedEventIds?.length ?? 0;
              const isCapReached =
                !isChecked && currentLength >= MAX_VALIDA_SELECTION;
              return (
                <button
                  key={r.event_id}
                  type="button"
                  onClick={() => toggleEvent(r.event_id)}
                  aria-pressed={isChecked}
                  aria-disabled={isCapReached}
                  disabled={isCapReached}
                  title={
                    isCapReached
                      ? "Máximo 4 carreras por lanzamiento (cap v2). Usa resumen temporada para visión global."
                      : r.label
                  }
                  data-testid={`launch-event-${r.event_id}`}
                  className={cn(
                    "min-h-9 rounded-full px-3 py-1 text-xs font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
                    isChecked
                      ? "bg-charcoal text-white"
                      : "bg-light-gray/40 text-charcoal hover:bg-light-gray/60",
                    isCapReached && "cursor-not-allowed opacity-50",
                  )}
                >
                  {r.series_kind === "championship"
                    ? "CD"
                    : `Válida ${r.sequence_number}`}
                </button>
              );
            })}
          </div>
        )}
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
            "shadow-button-highlight",
          )}
        >
          {isDisabled ? (
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles size={16} aria-hidden="true" />
          )}
          {isDisabled ? "Lanzando…" : "Analizar deportista"}
        </button>
      </div>
    </form>
  );
}
