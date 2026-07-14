/**
 * ProgressNotesBoard — tablero de progreso de fuerza y acondicionamiento por
 * atleta (US4 / T037). Mirroring de `components/technique/SkillProgressBoard.tsx`
 * (feature 018) adaptado al modelo de datos de fuerza: `GET .../progress`
 * devuelve el **último registro por ejercicio** (`items: StrengthProgressOut[]`),
 * sin historial separado (no hay `current`/`history` como en técnica).
 *
 * Diseño intencionalmente de clima de maestría (mastery-climate): enfoque en
 * proceso y esfuerzo individual, ancla en la maduración biológica del
 * deportista. ABSOLUTAMENTE SIN clasificación / SIN comparación entre atletas
 * (FR-015, mirror FR-017/SC-005 de 018) — este componente SIEMPRE se monta
 * con un único `athleteId` y jamás renderiza datos de más de un atleta a la
 * vez, ni en la misma vista ni en columnas/tablas lado a lado.
 *
 * WCAG 2.1 AA: roles semánticos, botones min-h-12 (48 px), colores ≥ 4.5:1,
 * estados de carga / vacío / error en toda superficie asíncrona.
 */
import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock3, ChevronUp, RefreshCw, Sparkles } from "lucide-react";

import { apiClient, mapStrengthError } from "@/api/strength";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAddStrengthProgress,
  useAthleteStrengthProgress,
} from "@/hooks/strength/useStrength";
import {
  strengthProgressInSchema,
  type StrengthProgressInput,
  type StrengthProgressOut,
} from "@/schemas/strength.schemas";
import type { StrengthProgressStatus } from "@/schemas/strength.schemas";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Ejercicios con id numérico — para el selector del formulario. El catálogo
// completo trae más campos de los que el formulario necesita; se recorta con
// `.strip()` local (misma técnica que `useSkillsWithId` en 018).
// ---------------------------------------------------------------------------

const exerciseWithIdSchema = z
  .object({
    id: z.number(),
    slug: z.string(),
    name: z.string(),
  })
  .passthrough();

type ExerciseWithId = z.infer<typeof exerciseWithIdSchema>;

function useExercisesWithId() {
  return useQuery<ExerciseWithId[]>({
    queryKey: ["strength", "exercises-with-id"],
    queryFn: async () => {
      const response = await apiClient.get<unknown>("/api/strength/exercises");
      const parsed = z
        .object({ items: z.array(exerciseWithIdSchema) })
        .parse(response.data);
      return parsed.items;
    },
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------------------
// Status display helpers
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<StrengthProgressStatus, string> = {
  introducido: "Introducido",
  en_progreso: "En progreso",
  dominado: "Dominado",
};

const STATUS_BADGE_VARIANT: Record<
  StrengthProgressStatus,
  "secondary" | "warning" | "success"
> = {
  introducido: "secondary",
  en_progreso: "warning",
  dominado: "success",
};

function StatusIcon({ status }: { status: StrengthProgressStatus }) {
  if (status === "dominado") {
    return <CheckCircle2 size={12} aria-hidden="true" />;
  }
  if (status === "en_progreso") {
    return <ChevronUp size={12} aria-hidden="true" />;
  }
  return <Clock3 size={12} aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Skeleton de carga
// ---------------------------------------------------------------------------

function ProgressSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando progreso de fuerza…"
      className="space-y-4"
    >
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-4 w-44" />
            <Skeleton className="h-5 w-24 rounded-full" />
          </div>
        ))}
      </div>
      <Skeleton className="h-32 w-full rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// AddProgressForm
// ---------------------------------------------------------------------------

interface AddProgressFormProps {
  athleteId: number;
  onSuccess?: () => void;
}

function AddProgressForm({ athleteId, onSuccess }: AddProgressFormProps) {
  const { data: exercises, isLoading: exercisesLoading } = useExercisesWithId();
  const addProgress = useAddStrengthProgress(athleteId);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const currentYear = new Date().getFullYear();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<StrengthProgressInput>({
    resolver: zodResolver(strengthProgressInSchema),
    defaultValues: {
      exercise_id: 0,
      status: "introducido",
      coach_note: "",
      season: currentYear,
    },
  });

  function onSubmit(data: StrengthProgressInput) {
    setSubmitError(null);
    addProgress.mutate(data, {
      onSuccess: () => {
        reset({
          exercise_id: 0,
          status: "introducido",
          coach_note: "",
          season: currentYear,
        });
        onSuccess?.();
      },
      onError: (err) => {
        setSubmitError(mapStrengthError(err).message);
      },
    });
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-4"
      aria-label="Registrar progreso de ejercicio de fuerza"
      noValidate
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Ejercicio */}
        <div>
          <label
            htmlFor="exercise_id"
            className="mb-1 block text-sm font-medium text-charcoal"
          >
            Ejercicio
          </label>
          <select
            id="exercise_id"
            {...register("exercise_id", { valueAsNumber: true })}
            disabled={exercisesLoading}
            aria-invalid={!!errors.exercise_id}
            aria-describedby={
              errors.exercise_id ? "exercise_id-error" : undefined
            }
            className="min-h-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
          >
            <option value={0}>Selecciona un ejercicio</option>
            {exercises?.map((exercise) => (
              <option key={exercise.slug} value={exercise.id}>
                {exercise.name}
              </option>
            ))}
          </select>
          {errors.exercise_id && (
            <p
              id="exercise_id-error"
              role="alert"
              className="mt-1 text-xs text-red-600"
            >
              {errors.exercise_id.message}
            </p>
          )}
        </div>

        {/* Estado */}
        <div>
          <label
            htmlFor="status"
            className="mb-1 block text-sm font-medium text-charcoal"
          >
            Estado
          </label>
          <select
            id="status"
            {...register("status")}
            aria-invalid={!!errors.status}
            aria-describedby={errors.status ? "status-error" : undefined}
            className="min-h-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="introducido">Introducido</option>
            <option value="en_progreso">En progreso</option>
            <option value="dominado">Dominado</option>
          </select>
          {errors.status && (
            <p id="status-error" role="alert" className="mt-1 text-xs text-red-600">
              {errors.status.message}
            </p>
          )}
        </div>

        {/* Temporada */}
        <div>
          <label
            htmlFor="season"
            className="mb-1 block text-sm font-medium text-charcoal"
          >
            Temporada
          </label>
          <input
            id="season"
            type="number"
            inputMode="numeric"
            {...register("season", { valueAsNumber: true })}
            aria-invalid={!!errors.season}
            aria-describedby={errors.season ? "season-error" : undefined}
            className="min-h-12 w-full rounded-lg border border-border-gray px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          {errors.season && (
            <p id="season-error" role="alert" className="mt-1 text-xs text-red-600">
              {errors.season.message}
            </p>
          )}
        </div>

        {/* Nota del entrenador */}
        <div>
          <label
            htmlFor="coach_note"
            className="mb-1 block text-sm font-medium text-charcoal"
          >
            Nota (opcional)
          </label>
          <textarea
            id="coach_note"
            {...register("coach_note")}
            rows={2}
            maxLength={500}
            placeholder="Contexto sobre el progreso observado, esfuerzo, técnica…"
            aria-invalid={!!errors.coach_note}
            aria-describedby={
              errors.coach_note ? "coach_note-error" : undefined
            }
            className="w-full rounded-lg border border-border-gray px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          {errors.coach_note && (
            <p
              id="coach_note-error"
              role="alert"
              className="mt-1 text-xs text-red-600"
            >
              {errors.coach_note.message}
            </p>
          )}
        </div>
      </div>

      {submitError && (
        <p role="alert" className="text-sm text-red-600">
          {submitError}
        </p>
      )}

      <Button type="submit" disabled={addProgress.isPending} className="min-h-12">
        {addProgress.isPending ? "Guardando…" : "Registrar progreso"}
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// CurrentStatusTable — último registro por ejercicio de este atleta
// ---------------------------------------------------------------------------

interface CurrentStatusTableProps {
  items: StrengthProgressOut[];
}

function CurrentStatusTable({ items }: CurrentStatusTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-border-gray bg-light-gray p-8 text-center">
        <Sparkles
          size={24}
          className="mx-auto mb-2 text-mid-gray"
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-charcoal">
          Sin ejercicios registrados todavía
        </p>
        <p className="mt-1 text-xs text-mid-gray">
          Usa el formulario de abajo para registrar el primer progreso.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto -mx-1">
      <table
        className="w-full min-w-[520px] text-sm"
        aria-label="Estado actual de ejercicios de fuerza — solo este deportista"
      >
        <thead>
          <tr className="border-b border-border-gray text-left">
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Ejercicio
            </th>
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Estado
            </th>
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Temporada
            </th>
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Fecha
            </th>
            <th className="pb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Nota
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((entry) => (
            <tr
              key={entry.exercise_id}
              className="border-b border-border-gray last:border-0"
            >
              <td className="py-2.5 pr-4">
                <span className="font-medium text-charcoal">
                  {entry.exercise_name}
                </span>
              </td>
              <td className="py-2.5 pr-4">
                <Badge
                  variant={STATUS_BADGE_VARIANT[entry.status]}
                  className="inline-flex items-center gap-1 text-[11px]"
                >
                  <StatusIcon status={entry.status} />
                  {STATUS_LABEL[entry.status]}
                </Badge>
              </td>
              <td className="py-2.5 pr-4 text-xs text-mid-gray">
                T{entry.season}
              </td>
              <td className="py-2.5 pr-4 text-xs text-mid-gray">
                {new Date(entry.recorded_at).toLocaleDateString("es-CO", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </td>
              <td className="py-2.5 max-w-[200px]">
                {entry.coach_note ? (
                  <span className="line-clamp-2 text-xs text-mid-gray">
                    {entry.coach_note}
                  </span>
                ) : (
                  <span className="text-mid-gray text-xs">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProgressNotesBoard — public API
// ---------------------------------------------------------------------------

export interface ProgressNotesBoardProps {
  athleteId: number;
}

/**
 * Tablero de progreso de fuerza y acondicionamiento para UN solo atleta (T037).
 *
 * Carga lazy: el consumidor debe usar React.lazy:
 * ```tsx
 * const ProgressNotesBoard = lazy(() =>
 *   import("@/components/strength/ProgressNotesBoard").then((m) => ({
 *     default: m.ProgressNotesBoard,
 *   }))
 * );
 * ```
 *
 * IMPORTANTE (FR-015): este componente recibe un único `athleteId` por prop y
 * SIEMPRE renderiza los datos de ese único atleta. No existe, ni debe
 * agregarse, ninguna superficie que muestre el progreso de dos o más atletas
 * lado a lado (tabla comparativa, ranking, leaderboard, gráfica multi-serie,
 * etc.) — el clima motivacional del club es de maestría personal, no de
 * comparación social.
 */
export function ProgressNotesBoard({ athleteId }: ProgressNotesBoardProps) {
  const { data, isLoading, isError, error, refetch } =
    useAthleteStrengthProgress(athleteId, athleteId > 0);

  // ── Estado: cargando ────────────────────────────────────────────────────
  if (isLoading) {
    return <ProgressSkeleton />;
  }

  // ── Estado: error ───────────────────────────────────────────────────────
  if (isError || !data) {
    const info = mapStrengthError(error);
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 p-5"
      >
        <p className="text-sm font-semibold text-red-700">
          {info.kind === "not_found"
            ? "Este atleta no tiene ejercicios de fuerza registrados todavía."
            : info.message}
        </p>
        {info.kind !== "not_found" && (
          <Button
            variant="outline"
            onClick={() => void refetch()}
            className="min-h-12 self-start gap-1.5"
          >
            <RefreshCw size={14} aria-hidden="true" />
            Reintentar
          </Button>
        )}
      </div>
    );
  }

  // ── Estado: datos disponibles ───────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* ── Estado actual por ejercicio (solo este deportista) ─────────── */}
      <Card>
        <CardHeader>
          {/*
           * h2 (no CardTitle/h3) intencional: esta tarjeta se monta dentro
           * de AthleteProgressPage, cuyo h1 es el único ancestro de
           * encabezado — usar h3 aquí rompería el orden jerárquico WCAG
           * (heading-order). Clases idénticas a `CardTitle` para mantener
           * el estilo visual.
           */}
          <h2 className="text-base font-semibold text-charcoal">
            Estado actual de fuerza y acondicionamiento
          </h2>
          <p className="text-sm text-mid-gray">
            Avance personal anclado al proceso y al esfuerzo — no se compara
            con otros deportistas.
          </p>
        </CardHeader>
        <CardContent>
          <CurrentStatusTable items={data.items} />
        </CardContent>
      </Card>

      {/* ── Formulario para registrar un nuevo progreso ─────────────────── */}
      <Card>
        <CardHeader>
          <h2 className="text-base font-semibold text-charcoal">
            Registrar progreso
          </h2>
          <p className="text-sm text-mid-gray">
            Cada registro es un nuevo evento (histórico append-only); el
            estado actual siempre refleja el más reciente por ejercicio.
          </p>
        </CardHeader>
        <CardContent>
          <AddProgressForm athleteId={athleteId} />
        </CardContent>
      </Card>
    </div>
  );
}

export default ProgressNotesBoard;
