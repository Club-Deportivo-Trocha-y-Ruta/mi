/**
 * ProjectProfilePage — Edición del perfil de proyecto del club.
 *
 * Carga con useProjectProfile (GET /api/clubs/:id/project-profile).
 * Si el backend retorna 404, trata como perfil vacío (todos los campos vacíos).
 * Guarda con useUpsertProjectProfile (PUT /api/clubs/:id/project-profile).
 *
 * specific_objectives se gestiona como lista editable (añadir/quitar items).
 *
 * Path: /training/reports/project-profile
 * Roles: coach, admin (ProtectedRoute en App.tsx)
 */

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";

import { useProjectProfile, useUpsertProjectProfile } from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";

// ---------------------------------------------------------------------------
// Schema Zod
// ---------------------------------------------------------------------------

const projectProfileSchema = z.object({
  project_name: z.string().max(300, "Máximo 300 caracteres").optional().or(z.literal("")),
  executing_entity: z.string().max(300, "Máximo 300 caracteres").optional().or(z.literal("")),
  report_responsible: z.string().max(300, "Máximo 300 caracteres").optional().or(z.literal("")),
  purpose: z.string().max(2000, "Máximo 2000 caracteres").optional().or(z.literal("")),
  general_objective: z.string().max(2000, "Máximo 2000 caracteres").optional().or(z.literal("")),
  territory_location: z.string().max(500, "Máximo 500 caracteres").optional().or(z.literal("")),
  territory_description: z.string().max(2000, "Máximo 2000 caracteres").optional().or(z.literal("")),
});

type ProjectProfileFormValues = z.infer<typeof projectProfileSchema>;

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const errorClass = "mt-1 text-xs text-red-600";

// ---------------------------------------------------------------------------
// SpecificObjectivesList — gestor de lista de objetivos específicos
// ---------------------------------------------------------------------------

interface SpecificObjectivesListProps {
  items: string[];
  onChange: (items: string[]) => void;
}

function SpecificObjectivesList({ items, onChange }: SpecificObjectivesListProps) {
  function handleChange(index: number, value: string) {
    const next = [...items];
    next[index] = value;
    onChange(next);
  }

  function handleAdd() {
    onChange([...items, ""]);
  }

  function handleRemove(index: number) {
    const next = items.filter((_, i) => i !== index);
    onChange(next);
  }

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            type="text"
            value={item}
            onChange={(e) => handleChange(index, e.target.value)}
            placeholder={`Objetivo específico ${index + 1}`}
            className={`${inputClass} shadow-ring`}
            aria-label={`Objetivo específico ${index + 1}`}
            id={`specific-objective-${index}`}
          />
          <button
            type="button"
            onClick={() => handleRemove(index)}
            aria-label={`Eliminar objetivo ${index + 1}`}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={handleAdd}
        className="flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
        data-testid="add-objective-btn"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        Agregar objetivo específico
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProjectProfilePage
// ---------------------------------------------------------------------------

export function ProjectProfilePage() {
  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0];

  const profileQuery = useProjectProfile(clubId);
  const upsertMutation = useUpsertProjectProfile(clubId ?? 0);

  const [specificObjectives, setSpecificObjectives] = useState<string[]>([]);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ProjectProfileFormValues>({
    resolver: zodResolver(projectProfileSchema),
    defaultValues: {
      project_name: "",
      executing_entity: "",
      report_responsible: "",
      purpose: "",
      general_objective: "",
      territory_location: "",
      territory_description: "",
    },
  });

  // Poblar el form cuando llegan los datos (o el perfil es null/vacío)
  useEffect(() => {
    if (profileQuery.isLoading) return;
    const p = profileQuery.data;
    reset({
      project_name: p?.project_name ?? "",
      executing_entity: p?.executing_entity ?? "",
      report_responsible: p?.report_responsible ?? "",
      purpose: p?.purpose ?? "",
      general_objective: p?.general_objective ?? "",
      territory_location: p?.territory_location ?? "",
      territory_description: p?.territory_description ?? "",
    });
    setSpecificObjectives(p?.specific_objectives ?? []);
  }, [profileQuery.isLoading, profileQuery.data, reset]);

  async function onSubmit(values: ProjectProfileFormValues) {
    if (!clubId) return;
    setSaveError(null);
    setSaveSuccess(false);

    const payload = {
      project_name: values.project_name || null,
      executing_entity: values.executing_entity || null,
      report_responsible: values.report_responsible || null,
      purpose: values.purpose || null,
      general_objective: values.general_objective || null,
      specific_objectives: specificObjectives.filter((o) => o.trim().length > 0),
      territory_location: values.territory_location || null,
      territory_description: values.territory_description || null,
    };

    upsertMutation.mutate(payload, {
      onSuccess: () => {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      },
      onError: () => {
        setSaveError("No se pudo guardar el perfil del proyecto. Intenta de nuevo.");
      },
    });
  }

  const isLoading = profileQuery.isLoading;

  if (isLoading) {
    return (
      <section className="max-w-3xl mx-auto space-y-4">
        <div className="h-6 w-48 animate-pulse rounded bg-light-gray" />
        <div className="h-96 animate-pulse rounded-xl bg-white shadow-card" />
      </section>
    );
  }

  return (
    <section className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Link
            to="/training/reports"
            className="mb-1 inline-block text-xs text-mid-gray transition-opacity hover:opacity-70"
          >
            ← Informes del club
          </Link>
          <h1
            className="font-display text-2xl text-charcoal"
          >
            Datos del proyecto
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Información institucional que se incluirá en los informes técnicos mensuales.
          </p>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          void handleSubmit(onSubmit)(e);
        }}
        noValidate
        className="space-y-5"
      >
        {/* Identificación del proyecto */}
        <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
          <h2 className="text-base font-semibold text-charcoal">
            Identificación del proyecto
          </h2>

          <div>
            <label htmlFor="project_name" className={labelClass}>
              Nombre del proyecto{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="project_name"
              type="text"
              {...register("project_name")}
              className={`${inputClass} shadow-ring`}
              placeholder="Ej: Formación deportiva XCO Valle del Cauca"
              aria-describedby={errors.project_name ? "project_name-error" : undefined}
              aria-invalid={!!errors.project_name}
            />
            {errors.project_name && (
              <p id="project_name-error" className={errorClass}>{errors.project_name.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="executing_entity" className={labelClass}>
              Entidad ejecutora{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="executing_entity"
              type="text"
              {...register("executing_entity")}
              className={`${inputClass} shadow-ring`}
              placeholder="Ej: Club Deportivo Trocha y Ruta"
              aria-describedby={errors.executing_entity ? "executing_entity-error" : undefined}
              aria-invalid={!!errors.executing_entity}
            />
            {errors.executing_entity && (
              <p id="executing_entity-error" className={errorClass}>{errors.executing_entity.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="report_responsible" className={labelClass}>
              Responsable del informe{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="report_responsible"
              type="text"
              {...register("report_responsible")}
              className={`${inputClass} shadow-ring`}
              placeholder="Nombre del entrenador o coordinador"
              aria-describedby={errors.report_responsible ? "report_responsible-error" : undefined}
              aria-invalid={!!errors.report_responsible}
            />
            {errors.report_responsible && (
              <p id="report_responsible-error" className={errorClass}>{errors.report_responsible.message}</p>
            )}
          </div>
        </div>

        {/* Propósito y objetivos */}
        <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
          <h2 className="text-base font-semibold text-charcoal">Propósito y objetivos</h2>

          <div>
            <label htmlFor="purpose" className={labelClass}>
              Propósito{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <textarea
              id="purpose"
              rows={3}
              {...register("purpose")}
              className={`${inputClass} resize-none shadow-ring`}
              placeholder="Describe el propósito general del proyecto deportivo…"
              aria-describedby={errors.purpose ? "purpose-error" : undefined}
              aria-invalid={!!errors.purpose}
            />
            {errors.purpose && (
              <p id="purpose-error" className={errorClass}>{errors.purpose.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="general_objective" className={labelClass}>
              Objetivo general{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <textarea
              id="general_objective"
              rows={3}
              {...register("general_objective")}
              className={`${inputClass} resize-none shadow-ring`}
              placeholder="Objetivo general del programa de formación…"
              aria-describedby={errors.general_objective ? "general_objective-error" : undefined}
              aria-invalid={!!errors.general_objective}
            />
            {errors.general_objective && (
              <p id="general_objective-error" className={errorClass}>{errors.general_objective.message}</p>
            )}
          </div>

          <div>
            <p className={`${labelClass} mb-2`}>
              Objetivos específicos{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </p>
            <SpecificObjectivesList
              items={specificObjectives}
              onChange={setSpecificObjectives}
            />
          </div>
        </div>

        {/* Territorio */}
        <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
          <h2 className="text-base font-semibold text-charcoal">Territorio</h2>

          <div>
            <label htmlFor="territory_location" className={labelClass}>
              Municipio / Localidad{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="territory_location"
              type="text"
              {...register("territory_location")}
              className={`${inputClass} shadow-ring`}
              placeholder="Ej: Cali, Valle del Cauca"
              aria-describedby={errors.territory_location ? "territory_location-error" : undefined}
              aria-invalid={!!errors.territory_location}
            />
            {errors.territory_location && (
              <p id="territory_location-error" className={errorClass}>{errors.territory_location.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="territory_description" className={labelClass}>
              Descripción del territorio{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <textarea
              id="territory_description"
              rows={3}
              {...register("territory_description")}
              className={`${inputClass} resize-none shadow-ring`}
              placeholder="Describe las características del territorio donde opera el club…"
              aria-describedby={errors.territory_description ? "territory_description-error" : undefined}
              aria-invalid={!!errors.territory_description}
            />
            {errors.territory_description && (
              <p id="territory_description-error" className={errorClass}>{errors.territory_description.message}</p>
            )}
          </div>
        </div>

        {/* Feedback */}
        {saveSuccess && (
          <p
            className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
            role="status"
            data-testid="save-success-msg"
          >
            Perfil del proyecto guardado correctamente.
          </p>
        )}
        {saveError && (
          <p
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            role="alert"
            data-testid="save-error-msg"
          >
            {saveError}
          </p>
        )}

        {/* Acciones */}
        <div className="flex justify-end gap-3">
          <Link
            to="/training/reports"
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={isSubmitting || upsertMutation.isPending || (!isDirty && !upsertMutation.isIdle)}
            className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight"
            data-testid="save-profile-btn"
          >
            {isSubmitting || upsertMutation.isPending ? "Guardando…" : "Guardar perfil"}
          </button>
        </div>
      </form>
    </section>
  );
}
