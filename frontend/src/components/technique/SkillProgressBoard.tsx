/**
 * SkillProgressBoard — tablero de progreso de habilidades técnicas por atleta (US4 / T039).
 *
 * Muestra, para UN solo atleta:
 *   - Estado actual por habilidad (introducido / en progreso / dominado) con
 *     colores de estado consistentes.
 *   - Historial de evolución de la temporada.
 *   - Control para registrar / actualizar el estado de una habilidad
 *     (usa useAddProgress).
 *
 * Diseño intencionalmente de crecimiento personal anclado a la edad biológica
 * del deportista. ABSOLUTAMENTE SIN clasificación / SIN comparación con otros
 * atletas (FR-017, SC-005).
 *
 * WCAG 2.1 AA: roles semánticos, botones min-h-12 (48 px), colores ≥ 4.5:1,
 * estados diseñados de carga / vacío / error en toda superficie asíncrona.
 */
import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { CheckCircle2, Clock3, Sparkles, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";

import { apiClient } from "@/api/client";
import { mapTechniqueError } from "@/api/technique";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAthleteSkillProgress,
  useAddProgress,
} from "@/hooks/technique/useTechnique";
import { progressInputSchema, type ProgressInputForm } from "@/schemas/technique.schemas";
import type { AthleteProgress, SkillProgressStatus } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Skills with numeric id — local schema (the shared skillSchema strips `id`)
// ---------------------------------------------------------------------------

const skillWithIdSchema = z
  .object({
    id: z.number(),
    code: z.string(),
    slug: z.string(),
    name: z.string(),
  })
  .strip();

type SkillWithId = z.infer<typeof skillWithIdSchema>;

function useSkillsWithId() {
  return useQuery<SkillWithId[]>({
    queryKey: ["technique", "skills-with-id"],
    queryFn: async () => {
      const response = await apiClient.get<unknown>("/api/technique/skills");
      return skillWithIdSchema.array().parse(response.data);
    },
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------------------
// Status display helpers
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<SkillProgressStatus, string> = {
  introducido: "Introducido",
  en_progreso: "En progreso",
  dominado: "Dominado",
};

const STATUS_BADGE_VARIANT: Record<
  SkillProgressStatus,
  "secondary" | "warning" | "success"
> = {
  introducido: "secondary",
  en_progreso: "warning",
  dominado: "success",
};

function StatusIcon({ status }: { status: SkillProgressStatus }) {
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
      aria-label="Cargando progreso de habilidades…"
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
  const { data: skills, isLoading: skillsLoading } = useSkillsWithId();
  const addProgress = useAddProgress(athleteId);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const currentYear = new Date().getFullYear();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProgressInputForm>({
    resolver: zodResolver(progressInputSchema),
    defaultValues: {
      skill_id: 0,
      status: "introducido",
      coach_note: "",
      season: currentYear,
    },
  });

  function onSubmit(data: ProgressInputForm) {
    setSubmitError(null);
    addProgress.mutate(data, {
      onSuccess: () => {
        reset({
          skill_id: 0,
          status: "introducido",
          coach_note: "",
          season: currentYear,
        });
        onSuccess?.();
      },
      onError: (err) => {
        setSubmitError(mapTechniqueError(err).message);
      },
    });
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-4"
      aria-label="Registrar progreso de habilidad"
      noValidate
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Habilidad */}
        <div>
          <label
            htmlFor="skill_id"
            className="mb-1 block text-sm font-medium text-slate-700"
          >
            Habilidad
          </label>
          <select
            id="skill_id"
            {...register("skill_id", { valueAsNumber: true })}
            disabled={skillsLoading}
            aria-invalid={!!errors.skill_id}
            aria-describedby={errors.skill_id ? "skill_id-error" : undefined}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
          >
            <option value={0}>Selecciona una habilidad</option>
            {skills?.map((skill) => (
              <option key={skill.slug} value={skill.id}>
                {skill.name}
              </option>
            ))}
          </select>
          {errors.skill_id && (
            <p id="skill_id-error" role="alert" className="mt-1 text-xs text-red-600">
              {errors.skill_id.message}
            </p>
          )}
        </div>

        {/* Estado */}
        <div>
          <label
            htmlFor="status"
            className="mb-1 block text-sm font-medium text-slate-700"
          >
            Estado
          </label>
          <select
            id="status"
            {...register("status")}
            aria-invalid={!!errors.status}
            aria-describedby={errors.status ? "status-error" : undefined}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
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
            className="mb-1 block text-sm font-medium text-slate-700"
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
            className="min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
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
            className="mb-1 block text-sm font-medium text-slate-700"
          >
            Nota (opcional)
          </label>
          <textarea
            id="coach_note"
            {...register("coach_note")}
            rows={2}
            maxLength={500}
            placeholder="Contexto sobre el progreso observado…"
            aria-invalid={!!errors.coach_note}
            aria-describedby={errors.coach_note ? "coach_note-error" : undefined}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          {errors.coach_note && (
            <p id="coach_note-error" role="alert" className="mt-1 text-xs text-red-600">
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

      <Button
        type="submit"
        disabled={addProgress.isPending}
        className="min-h-12"
      >
        {addProgress.isPending ? "Guardando…" : "Registrar progreso"}
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// CurrentStatusTable — estado actual por habilidad
// ---------------------------------------------------------------------------

interface CurrentStatusTableProps {
  progress: AthleteProgress;
}

function CurrentStatusTable({ progress }: CurrentStatusTableProps) {
  if (progress.current.length === 0) {
    return (
      <div className="rounded-xl border border-slate-100 bg-slate-50 p-8 text-center">
        <Sparkles
          size={24}
          className="mx-auto mb-2 text-slate-300"
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-slate-700">
          Sin habilidades registradas todavía
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Usa el formulario de abajo para registrar el primer progreso.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto -mx-1">
      <table
        className="w-full min-w-[520px] text-sm"
        aria-label="Estado actual de habilidades técnicas"
      >
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Habilidad
            </th>
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Estado
            </th>
            <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Fecha
            </th>
            <th className="pb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Nota
            </th>
          </tr>
        </thead>
        <tbody>
          {progress.current.map((entry) => (
            <tr
              key={entry.skill.slug}
              className="border-b border-slate-100 last:border-0"
            >
              <td className="py-2.5 pr-4">
                <span className="font-medium text-slate-800">
                  {entry.skill.name}
                </span>
                <span className="ml-1.5 text-[11px] font-medium text-slate-400">
                  {entry.skill.code}
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
              <td className="py-2.5 pr-4 text-xs text-slate-500">
                {new Date(entry.recorded_at).toLocaleDateString("es-CO", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </td>
              <td className="py-2.5 max-w-[200px]">
                {entry.coach_note ? (
                  <span className="line-clamp-2 text-xs text-slate-600">
                    {entry.coach_note}
                  </span>
                ) : (
                  <span className="text-slate-300 text-xs">—</span>
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
// HistoryTimeline — evolución de la temporada
// ---------------------------------------------------------------------------

interface HistoryTimelineProps {
  progress: AthleteProgress;
}

function HistoryTimeline({ progress }: HistoryTimelineProps) {
  const [expanded, setExpanded] = useState(false);

  // newest first for display
  const history = [...progress.history].reverse();
  const PREVIEW_COUNT = 5;
  const visible = expanded ? history : history.slice(0, PREVIEW_COUNT);
  const hiddenCount = history.length - PREVIEW_COUNT;

  return (
    <div>
      <ol
        aria-label="Historial de progreso de la temporada"
        className="space-y-2"
      >
        {visible.map((event) => (
          <li
            key={event.id}
            className="flex items-start gap-3 rounded-lg border border-slate-100 bg-white p-3 text-sm shadow-sm"
          >
            <div className="mt-0.5 shrink-0">
              <Badge
                variant={STATUS_BADGE_VARIANT[event.status]}
                className="inline-flex items-center gap-1 text-[11px]"
              >
                <StatusIcon status={event.status} />
                {STATUS_LABEL[event.status]}
              </Badge>
            </div>

            <div className="flex-1 min-w-0">
              <span className="font-medium text-slate-800">
                {event.skill.name}
              </span>
              {event.coach_note && (
                <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
                  {event.coach_note}
                </p>
              )}
            </div>

            <time
              dateTime={event.recorded_at}
              className="shrink-0 text-right text-xs text-slate-400"
            >
              {new Date(event.recorded_at).toLocaleDateString("es-CO", {
                day: "numeric",
                month: "short",
              })}
              <br />
              <span className="font-medium text-slate-500">
                T{event.season}
              </span>
            </time>
          </li>
        ))}
      </ol>

      {history.length > PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          className="mt-3 inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        >
          {expanded ? (
            <>
              <ChevronUp size={14} aria-hidden="true" />
              Ver menos
            </>
          ) : (
            <>
              <ChevronDown size={14} aria-hidden="true" />
              Ver {hiddenCount} registro{hiddenCount !== 1 ? "s" : ""} anterior
              {hiddenCount !== 1 ? "es" : ""}
            </>
          )}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SkillProgressBoard — public API
// ---------------------------------------------------------------------------

export interface SkillProgressBoardProps {
  athleteId: number;
}

/**
 * Tablero de progreso técnico personal para un atleta (T039).
 *
 * Carga lazy: el consumidor debe usar React.lazy:
 * ```tsx
 * const SkillProgressBoard = lazy(() =>
 *   import("@/components/technique/SkillProgressBoard").then((m) => ({
 *     default: m.SkillProgressBoard,
 *   }))
 * );
 * ```
 */
export function SkillProgressBoard({ athleteId }: SkillProgressBoardProps) {
  const { data, isLoading, isError, error, refetch } =
    useAthleteSkillProgress(athleteId, athleteId > 0);

  // ── Estado: cargando ────────────────────────────────────────────────────
  if (isLoading) {
    return <ProgressSkeleton />;
  }

  // ── Estado: error ───────────────────────────────────────────────────────
  if (isError || !data) {
    const info = mapTechniqueError(error);
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 p-5"
      >
        <p className="text-sm font-semibold text-red-700">
          {info.kind === "not_found"
            ? "Este atleta no tiene habilidades registradas todavía."
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
      {/* ── Estado actual por habilidad ────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Estado actual de habilidades</CardTitle>
          <p className="text-sm text-slate-500">
            Avance personal anclado a la etapa de maduración biológica del
            deportista — no se compara con otros atletas.
          </p>
        </CardHeader>
        <CardContent>
          <CurrentStatusTable progress={data} />
        </CardContent>
      </Card>

      {/* ── Historial / evolución de la temporada ──────────────────────── */}
      {data.history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Evolución en la temporada</CardTitle>
            <p className="text-sm text-slate-500">
              Registro cronológico de los cambios de estado observados durante
              los entrenamientos.
            </p>
          </CardHeader>
          <CardContent>
            <HistoryTimeline progress={data} />
          </CardContent>
        </Card>
      )}

      {/* ── Formulario para registrar / actualizar estado ──────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Registrar progreso</CardTitle>
          <p className="text-sm text-slate-500">
            El estado actual de cada habilidad siempre refleja el registro más
            reciente — registra un nuevo evento para actualizar.
          </p>
        </CardHeader>
        <CardContent>
          <AddProgressForm athleteId={athleteId} />
        </CardContent>
      </Card>
    </div>
  );
}

export default SkillProgressBoard;
