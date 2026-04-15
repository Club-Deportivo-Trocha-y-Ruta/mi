import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AthleteForm, type AthleteFormValues } from "@/components/athletes/AthleteForm";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useCreateAthlete } from "@/hooks/athletes/useCreateAthlete";
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

  const athleteId = Number(id);
  const isEdit = mode === "edit";
  const athleteQuery = useAthlete(athleteId, isEdit);
  const createMutation = useCreateAthlete();
  const updateMutation = useUpdateAthlete();

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

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
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
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

  return (
    <section className="space-y-5">
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          {isEdit ? "Editar atleta" : "Nuevo atleta"}
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          {isEdit ? "Actualiza la información básica del atleta." : "Registra un nuevo atleta en el club."}
        </p>
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
    </section>
  );
}
