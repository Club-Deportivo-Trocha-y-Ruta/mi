import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Trash2 } from "lucide-react";

import { AthleteForm, type AthleteFormValues } from "@/components/athletes/AthleteForm";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useCreateAthlete } from "@/hooks/athletes/useCreateAthlete";
import { useDeleteAthlete } from "@/hooks/athletes/useDeleteAthlete";
import { useUpdateAthlete } from "@/hooks/athletes/useUpdateAthlete";
import { useAuthStore } from "@/store/auth.store";

interface AthleteFormPageProps {
  mode: "create" | "edit";
}

export function AthleteFormPage({ mode }: AthleteFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const user = useAuthStore((state) => state.user);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const athleteId = Number(id);
  const isEdit = mode === "edit";
  const athleteQuery = useAthlete(athleteId, isEdit);
  const createMutation = useCreateAthlete();
  const updateMutation = useUpdateAthlete();
  const deleteMutation = useDeleteAthlete();

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  const handleDelete = () => {
    setDeleteError(null);
    deleteMutation.mutate(athleteId, {
      onSuccess: () => {
        setDeleteOpen(false);
        navigate("/athletes");
      },
      onError: () => {
        setDeleteError("No se pudo eliminar el atleta. Intenta de nuevo.");
      },
    });
  };

  const initialValues = useMemo(() => {
    return athleteQuery.data;
  }, [athleteQuery.data]);

  const handleSubmit = async (values: AthleteFormValues) => {
    setSubmitError(null);
    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: athleteId,
          payload: {
            first_name: values.first_name,
            last_name: values.last_name,
            club_join_date: values.club_join_date || null,
          },
        });
        navigate(`/athletes/${athleteId}`);
        return;
      }

      const clubId = user?.club_ids?.[0];
      if (!clubId) {
        setSubmitError("No tienes un club asignado para crear atletas.");
        return;
      }

      const created = await createMutation.mutateAsync({
        first_name: values.first_name,
        last_name: values.last_name,
        birth_date: values.birth_date,
        sex: values.sex,
        club_join_date: values.club_join_date || null,
        club_id: clubId,
      });
      navigate(`/athletes/${created.id}`);
    } catch {
      setSubmitError("No se pudo guardar el atleta. Intenta de nuevo.");
    }
  };

  if (isEdit && athleteQuery.isLoading) {
    return (
      <section className="space-y-3">
        <div className="h-6 w-52 animate-pulse rounded bg-light-gray" />
        <div className="h-56 animate-pulse rounded-xl bg-light-gray" />
      </section>
    );
  }

  if (isEdit && athleteQuery.isError) {
    return (
      <section className="space-y-3">
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Editar atleta
        </h1>
        <p className="text-sm text-red-700">No se pudo cargar el atleta.</p>
        <Link
          to="/athletes"
          className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          Volver a la lista
        </Link>
      </section>
    );
  }

  const athleteFullName = initialValues
    ? `${initialValues.first_name} ${initialValues.last_name}`
    : "";

  return (
    <section className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1
            className="font-display text-2xl text-charcoal"
          >
            {isEdit ? "Editar atleta" : "Nuevo atleta"}
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            {isEdit ? "Actualiza la información básica del atleta." : "Registra un nuevo atleta en el club."}
          </p>
        </div>
        {isEdit && (
          <button
            type="button"
            onClick={() => {
              setDeleteError(null);
              setDeleteOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
          >
            <Trash2 size={14} />
            Eliminar atleta
          </button>
        )}
      </div>

      <AthleteForm
        mode={mode}
        initialValues={initialValues}
        isSubmitting={isSubmitting}
        submitError={submitError}
        onSubmit={(values) => {
          void handleSubmit(values);
        }}
      />

      {isEdit && (
        <ConfirmDialog
          open={deleteOpen}
          title="Eliminar atleta"
          description={
            <>
              <span className="font-medium text-charcoal">{athleteFullName}</span>
              <br />
              Se eliminarán de forma permanente el perfil del atleta, sus mediciones antropométricas, vínculos con padres/acudientes, invitaciones y consentimientos. Esta acción no se puede deshacer.
            </>
          }
          confirmLabel="Sí, eliminar atleta"
          tone="danger"
          isPending={deleteMutation.isPending}
          errorMessage={deleteError ?? undefined}
          onCancel={() => setDeleteOpen(false)}
          onConfirm={handleDelete}
        />
      )}
    </section>
  );
}
