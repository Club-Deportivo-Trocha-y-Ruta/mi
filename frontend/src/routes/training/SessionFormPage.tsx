/**
 * SessionFormPage — alta/edición de una sesión de entrenamiento.
 *
 * Estructura (post-B5):
 *  - `session-form/useSessionForm`    → form + snapshot + diff + persist.
 *  - `session-form/GeneralInfoSection` → fecha/hora/duración/lugar/foco/desc.
 *  - `session-form/RouteSection`       → texto recorrido + Strava (opcional).
 *  - `session-form/AthletesSection`    → multi-select de convocados.
 *
 * Este archivo queda como el "shell": layout + header + footer + diálogo.
 */
import { Link, useParams } from "react-router-dom";

import { NotifyParentsDialog } from "@/components/training/NotifyParentsDialog";

import { AthletesSection } from "./session-form/AthletesSection";
import { GeneralInfoSection } from "./session-form/GeneralInfoSection";
import { RouteSection } from "./session-form/RouteSection";
import { useSessionForm } from "./session-form/useSessionForm";

interface SessionFormPageProps {
  mode: "create" | "edit";
}

export function SessionFormPage({ mode }: SessionFormPageProps) {
  const { id } = useParams();
  const sessionId = Number(id);

  const {
    form,
    sessionQuery,
    attendanceQuery,
    pending,
    dialogError,
    dialogPending,
    mutationError,
    isEdit,
    onSubmit,
    persistPending,
    handleDialogCancel,
    handleCancel,
    onError,
  } = useSessionForm({ mode, sessionId });

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = form;

  if (isEdit && (sessionQuery.isLoading || attendanceQuery.isLoading)) {
    return (
      <section className="space-y-3">
        <div className="h-6 w-52 animate-pulse rounded bg-light-gray" />
        <div className="h-80 animate-pulse rounded-xl bg-light-gray" />
      </section>
    );
  }

  if (isEdit && sessionQuery.isError) {
    return (
      <section className="space-y-3">
        <h1 className="text-2xl text-charcoal font-heading">Editar sesión</h1>
        <p className="text-sm text-red-700">No se pudo cargar la sesión.</p>
        <Link
          to="/training/sessions"
          className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          Volver a la lista
        </Link>
      </section>
    );
  }

  return (
    <section className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl text-charcoal font-heading">
            {isEdit ? "Editar sesión" : "Nueva sesión"}
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            {isEdit
              ? "Actualiza los datos de la sesión."
              : "Planifica una nueva sesión de entrenamiento."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleCancel}
          className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
        >
          Cancelar
        </button>
      </div>

      <form
        onSubmit={(e) => {
          void handleSubmit(onSubmit, onError)(e);
        }}
        className="space-y-6"
        noValidate
      >
        <GeneralInfoSection
          register={register}
          control={control}
          errors={errors}
        />
        <RouteSection register={register} errors={errors} />
        <AthletesSection control={control} errors={errors} />

        {mutationError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {mutationError}
          </p>
        )}

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight"
          >
            {isSubmitting
              ? "Guardando..."
              : isEdit
                ? "Guardar cambios"
                : "Crear sesión"}
          </button>
        </div>
      </form>

      <NotifyParentsDialog
        open={pending !== null}
        variant={pending?.variant ?? "create"}
        parentCount={
          pending?.variant === "attendance"
            ? pending.addedAthletes.length
            : (pending?.payload.convocados_athlete_ids.length ?? 0)
        }
        changes={pending?.changes ?? []}
        addedAthletes={pending?.addedAthletes ?? []}
        removedAthletes={pending?.removedAthletes ?? []}
        isPending={dialogPending}
        errorMessage={dialogError}
        onSend={() => void persistPending(true)}
        onSkip={() => void persistPending(false)}
        onCancel={handleDialogCancel}
      />
    </section>
  );
}
