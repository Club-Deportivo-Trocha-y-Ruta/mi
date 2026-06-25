/**
 * ExerciseForm — formulario RHF + Zod para crear/editar ejercicios (US5 / T046).
 *
 * Campos:
 *   - name, summary, how_to, difficulty (select), is_game, is_gymkhana (checkboxes)
 *   - layout_ascii, layout_alt (solo visibles; layout_ascii requerido si is_gymkhana=true)
 *   - age_bands (multi-toggle, ≥1)
 *   - skill_slugs (multi-toggle desde useSkills, ≥1)
 *   - material_slugs (multi-toggle desde useMaterials)
 *
 * Manejo de errores: inline en español neutro, vinculados con aria-describedby.
 * Estados de carga: Skeleton mientras cargan skills/materials.
 * WCAG 2.1 AA: áreas táctiles ≥48×48 px; labels explícitos; aria-invalid.
 */
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useSkills, useMaterials } from "@/hooks/technique/useTechnique";
import {
  exerciseCreateSchema,
  type ExerciseCreateForm,
} from "@/schemas/technique.schemas";
import type { ExerciseDetail } from "@/types/technique.types";

// Input type (fields as typed in the form — booleans and arrays optional because
// they have .default() in the schema). Output type (ExerciseCreateForm) is what
// the resolver produces after parsing and is what onSubmit receives.
type ExerciseFormInput = z.input<typeof exerciseCreateSchema>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIFFICULTY_OPTIONS = [
  { value: "facil", label: "Fácil" },
  { value: "media", label: "Media" },
  { value: "avanzada", label: "Avanzada" },
] as const;

const AGE_BAND_OPTIONS = [
  { value: "7-9", label: "7–9 años" },
  { value: "10-12", label: "10–12 años" },
  { value: "13-15", label: "13–15 años" },
] as const;

// ---------------------------------------------------------------------------
// Shared field style tokens (matches session-wizard/StepGeneral pattern)
// ---------------------------------------------------------------------------

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "w-full min-h-[48px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ExerciseFormProps {
  /** When provided the form will be pre-populated with existing exercise data. */
  defaultValues?: Partial<ExerciseDetail>;
  /** Called with validated form values when the user submits. */
  onSubmit: (values: ExerciseCreateForm) => void;
  /** When true, the submit button shows a loading spinner and is disabled. */
  isPending?: boolean;
  /** Text for the submit button. Default: "Guardar ejercicio" */
  submitLabel?: string;
  /** Optional cancel handler — renders a "Cancelar" button when provided. */
  onCancel?: () => void;
}

// ---------------------------------------------------------------------------
// Helper: convert ExerciseDetail to ExerciseCreateForm defaults
// ---------------------------------------------------------------------------

function toFormDefaults(exercise?: Partial<ExerciseDetail>): Partial<ExerciseCreateForm> {
  if (!exercise) return {};
  return {
    name: exercise.name ?? "",
    summary: exercise.summary ?? "",
    how_to: exercise.how_to ?? "",
    difficulty: exercise.difficulty,
    is_game: exercise.is_game ?? false,
    is_gymkhana: exercise.is_gymkhana ?? false,
    layout_ascii: exercise.layout_ascii ?? "",
    layout_alt: exercise.layout_alt ?? "",
    age_bands: exercise.age_bands ?? [],
    skill_slugs: exercise.skills?.map((s) => s.slug) ?? [],
    material_slugs: exercise.materials?.map((m) => m.slug) ?? [],
  };
}

// ---------------------------------------------------------------------------
// Multi-toggle button (reusable inside the form)
// ---------------------------------------------------------------------------

interface ToggleChipProps {
  label: string;
  active: boolean;
  onToggle: () => void;
  colorActive?: string;
}

function ToggleChip({
  label,
  active,
  onToggle,
  colorActive = "bg-primary text-white border-primary",
}: ToggleChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      className={[
        "min-h-[48px] rounded-lg border px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2",
        active
          ? colorActive
          : "border-[rgba(34,42,53,0.12)] bg-white text-charcoal hover:bg-light-gray",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExerciseForm({
  defaultValues,
  onSubmit,
  isPending = false,
  submitLabel = "Guardar ejercicio",
  onCancel,
}: ExerciseFormProps) {
  const { data: skills, isLoading: skillsLoading, isError: skillsError } = useSkills();
  const { data: materials, isLoading: materialsLoading } = useMaterials();

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ExerciseFormInput, unknown, ExerciseCreateForm>({
    resolver: zodResolver(exerciseCreateSchema),
    defaultValues: {
      name: "",
      summary: "",
      how_to: "",
      difficulty: "facil",
      is_game: false,
      is_gymkhana: false,
      layout_ascii: "",
      layout_alt: "",
      age_bands: [],
      skill_slugs: [],
      material_slugs: [],
      ...toFormDefaults(defaultValues),
    },
  });

  const isGymkhana = watch("is_gymkhana");

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="space-y-5"
      aria-label="Formulario de ejercicio"
    >
      {/* ------------------------------------------------------------------ */}
      {/* Nombre                                                               */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <label htmlFor="exercise-name" className={labelClass}>
          Nombre <span aria-hidden="true" className="text-red-500">*</span>
        </label>
        <input
          id="exercise-name"
          type="text"
          placeholder="Ej: Slalom de conos"
          {...register("name")}
          className={`mt-1 ${inputClass}`}
          style={inputStyle}
          aria-describedby={errors.name ? "exercise-name-error" : undefined}
          aria-invalid={!!errors.name}
          aria-required="true"
        />
        {errors.name && (
          <p id="exercise-name-error" role="alert" className={errorClass}>
            {errors.name.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Resumen                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <label htmlFor="exercise-summary" className={labelClass}>
          Resumen <span aria-hidden="true" className="text-red-500">*</span>
        </label>
        <input
          id="exercise-summary"
          type="text"
          placeholder="Una frase que describa el ejercicio"
          {...register("summary")}
          className={`mt-1 ${inputClass}`}
          style={inputStyle}
          aria-describedby={errors.summary ? "exercise-summary-error" : undefined}
          aria-invalid={!!errors.summary}
          aria-required="true"
        />
        {errors.summary && (
          <p id="exercise-summary-error" role="alert" className={errorClass}>
            {errors.summary.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Instrucciones (how_to)                                              */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <label htmlFor="exercise-how-to" className={labelClass}>
          Instrucciones <span aria-hidden="true" className="text-red-500">*</span>
        </label>
        <Textarea
          id="exercise-how-to"
          rows={5}
          placeholder="Describe paso a paso cómo ejecutar el ejercicio…"
          {...register("how_to")}
          className="mt-1 min-h-[120px]"
          aria-describedby={errors.how_to ? "exercise-how-to-error" : undefined}
          aria-invalid={!!errors.how_to}
          aria-required="true"
        />
        {errors.how_to && (
          <p id="exercise-how-to-error" role="alert" className={errorClass}>
            {errors.how_to.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Dificultad                                                           */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <label htmlFor="exercise-difficulty" className={labelClass}>
          Dificultad <span aria-hidden="true" className="text-red-500">*</span>
        </label>
        <select
          id="exercise-difficulty"
          {...register("difficulty")}
          className={`mt-1 ${inputClass}`}
          style={inputStyle}
          aria-describedby={errors.difficulty ? "exercise-difficulty-error" : undefined}
          aria-invalid={!!errors.difficulty}
        >
          {DIFFICULTY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {errors.difficulty && (
          <p id="exercise-difficulty-error" role="alert" className={errorClass}>
            {errors.difficulty.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Tipo de ejercicio: juego / gymkhana                                 */}
      {/* ------------------------------------------------------------------ */}
      <fieldset className="space-y-2">
        <legend className={`${labelClass} mb-1`}>Tipo de ejercicio</legend>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            {...register("is_game")}
            className="h-5 w-5 rounded border-slate-300 text-primary focus:ring-2 focus:ring-primary/50"
          />
          <span className="text-sm text-charcoal">
            Juego de participación
            <span className="ml-1 text-xs text-mid-gray">(ejercicio lúdico / de motivación)</span>
          </span>
        </label>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            {...register("is_gymkhana")}
            className="h-5 w-5 rounded border-slate-300 text-primary focus:ring-2 focus:ring-primary/50"
          />
          <span className="text-sm text-charcoal">
            Gymkhana
            <span className="ml-1 text-xs text-mid-gray">(requiere diagrama de circuito)</span>
          </span>
        </label>
      </fieldset>

      {/* ------------------------------------------------------------------ */}
      {/* Layout ASCII (requerido si is_gymkhana)                             */}
      {/* ------------------------------------------------------------------ */}
      {isGymkhana && (
        <div>
          <label htmlFor="exercise-layout-ascii" className={labelClass}>
            Diagrama del circuito (ASCII){" "}
            <span aria-hidden="true" className="text-red-500">*</span>
          </label>
          <Textarea
            id="exercise-layout-ascii"
            rows={6}
            placeholder={"Dibuja el circuito usando caracteres ASCII:\n\n  [CONO] ---> [CONO]\n     ^           |\n     |           v\n  [INICIO]  [CONO]"}
            {...register("layout_ascii")}
            className="mt-1 min-h-[120px] font-mono text-xs"
            aria-describedby={errors.layout_ascii ? "exercise-layout-ascii-error" : undefined}
            aria-invalid={!!errors.layout_ascii}
            aria-required="true"
          />
          {errors.layout_ascii && (
            <p id="exercise-layout-ascii-error" role="alert" className={errorClass}>
              {errors.layout_ascii.message}
            </p>
          )}

          <label htmlFor="exercise-layout-alt" className={`${labelClass} mt-3`}>
            Descripción alternativa del diagrama{" "}
            <span className="font-normal text-mid-gray">(opcional, para accesibilidad)</span>
          </label>
          <input
            id="exercise-layout-alt"
            type="text"
            placeholder="Ej: Circuito en forma de U con 4 conos equidistantes"
            {...register("layout_alt")}
            className={`mt-1 ${inputClass}`}
            style={inputStyle}
          />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Franjas de edad (multi-toggle, ≥1)                                  */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <p
          className={labelClass}
          id="exercise-age-bands-label"
        >
          Franjas de edad{" "}
          <span aria-hidden="true" className="text-red-500">*</span>
        </p>
        <p className="mt-0.5 text-xs text-mid-gray">Selecciona al menos una.</p>

        <Controller
          name="age_bands"
          control={control}
          render={({ field }) => (
            <div
              className="mt-2 flex flex-wrap gap-2"
              role="group"
              aria-labelledby="exercise-age-bands-label"
              aria-describedby={errors.age_bands ? "exercise-age-bands-error" : undefined}
            >
              {AGE_BAND_OPTIONS.map((o) => {
                const active = field.value.includes(o.value);
                return (
                  <ToggleChip
                    key={o.value}
                    label={o.label}
                    active={active}
                    onToggle={() => {
                      const next = active
                        ? field.value.filter((v) => v !== o.value)
                        : [...field.value, o.value];
                      field.onChange(next);
                    }}
                  />
                );
              })}
            </div>
          )}
        />
        {errors.age_bands && (
          <p id="exercise-age-bands-error" role="alert" className={errorClass}>
            {errors.age_bands.message ?? (errors.age_bands as { root?: { message?: string } }).root?.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Habilidades (multi-toggle, ≥1)                                      */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <p
          className={labelClass}
          id="exercise-skills-label"
        >
          Habilidades{" "}
          <span aria-hidden="true" className="text-red-500">*</span>
        </p>
        <p className="mt-0.5 text-xs text-mid-gray">Selecciona al menos una habilidad técnica.</p>

        {skillsLoading && (
          <div
            className="mt-2 flex flex-wrap gap-2"
            aria-busy="true"
            aria-label="Cargando habilidades…"
          >
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-28 rounded-lg" />
            ))}
          </div>
        )}

        {skillsError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            No se pudieron cargar las habilidades. Intenta de nuevo.
          </p>
        )}

        {!skillsLoading && !skillsError && skills && (
          <Controller
            name="skill_slugs"
            control={control}
            render={({ field }) => (
              <div
                className="mt-2 flex flex-wrap gap-2"
                role="group"
                aria-labelledby="exercise-skills-label"
                aria-describedby={errors.skill_slugs ? "exercise-skills-error" : undefined}
              >
                {skills.map((skill) => {
                  const active = field.value.includes(skill.slug);
                  return (
                    <ToggleChip
                      key={skill.slug}
                      label={skill.name}
                      active={active}
                      onToggle={() => {
                        const next = active
                          ? field.value.filter((s) => s !== skill.slug)
                          : [...field.value, skill.slug];
                        field.onChange(next);
                      }}
                      colorActive="bg-emerald-600 text-white border-emerald-600"
                    />
                  );
                })}
              </div>
            )}
          />
        )}
        {errors.skill_slugs && (
          <p id="exercise-skills-error" role="alert" className={errorClass}>
            {errors.skill_slugs.message ?? (errors.skill_slugs as { root?: { message?: string } }).root?.message}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Materiales (multi-toggle, opcional)                                 */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <p
          className={labelClass}
          id="exercise-materials-label"
        >
          Materiales necesarios{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </p>
        <p className="mt-0.5 text-xs text-mid-gray">
          Deja sin marcar si el ejercicio no requiere materiales.
        </p>

        {materialsLoading && (
          <div
            className="mt-2 flex flex-wrap gap-2"
            aria-busy="true"
            aria-label="Cargando materiales…"
          >
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-24 rounded-lg" />
            ))}
          </div>
        )}

        {!materialsLoading && materials && (
          <Controller
            name="material_slugs"
            control={control}
            render={({ field }) => (
              <div
                className="mt-2 flex flex-wrap gap-2"
                role="group"
                aria-labelledby="exercise-materials-label"
              >
                {materials
                  .filter((m) => !m.is_none)
                  .map((mat) => {
                    const current = field.value ?? [];
                    const active = current.includes(mat.slug);
                    return (
                      <ToggleChip
                        key={mat.slug}
                        label={mat.name}
                        active={active}
                        onToggle={() => {
                          const next = active
                            ? current.filter((s) => s !== mat.slug)
                            : [...current, mat.slug];
                          field.onChange(next);
                        }}
                        colorActive="bg-slate-700 text-white border-slate-700"
                      />
                    );
                  })}
              </div>
            )}
          />
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Acciones                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={isPending}
          className="min-h-[48px] rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2 disabled:opacity-50"
        >
          {isPending ? "Guardando…" : submitLabel}
        </button>

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="min-h-[48px] rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-6 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-light-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2 disabled:opacity-50"
          >
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
}

export default ExerciseForm;
