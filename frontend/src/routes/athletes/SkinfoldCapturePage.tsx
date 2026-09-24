import { useEffect, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { SkinfoldWizard } from "@/components/athletes/body-composition/SkinfoldWizard";
import { PageHeader } from "@/components/shared/PageHeader";
import { RouteFallback } from "@/components/shared/RouteFallback";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { ageAtEvaluation, SKINFOLD_MIN_AGE_YEARS } from "@/lib/bodyComposition/eligibility";

/**
 * SkinfoldCapturePage — `/athletes/:id/anthropometry/:recordId/skinfolds`
 * (feature 046, US1, T029). Coach/admin únicamente (guard en `App.tsx`).
 *
 * Carga la evaluación antropométrica, verifica la edad mínima y monta el
 * `SkinfoldWizard`. Al guardar vuelve a la pestaña «Crecimiento» del
 * perfil del deportista.
 *
 * Edad en la fecha de la evaluación: se deriva de la propia evaluación
 * (`ageAtEvaluation`, `lib/bodyComposition/eligibility.ts`), así que no se
 * necesita la fecha de nacimiento del menor en esta pantalla. Es una compuerta de UX: el
 * backend vuelve a validar con la fecha de nacimiento exacta
 * (`check_min_age`, 409 `athlete_too_young`) y el asistente muestra ese
 * error si llegara a ocurrir en el límite.
 *
 * Privacidad: la pantalla no muestra el nombre del deportista ni ningún
 * dato identificable; los toasts no incluyen edad ni valores.
 */

export function SkinfoldCapturePage() {
  const params = useParams<{ id: string; recordId: string }>();
  const navigate = useNavigate();
  const athleteId = Number(params.id);
  const recordId = Number(params.recordId);
  const profilePath = `/athletes/${athleteId}?tab=growth`;

  const { data: records, isLoading, isError } = useAnthropometry(
    Number.isFinite(athleteId) ? athleteId : 0,
  );

  const record = useMemo(
    () => records?.find((r) => r.id === recordId) ?? null,
    [records, recordId],
  );
  const ageYears = record ? ageAtEvaluation(record) : null;
  const tooYoung = ageYears !== null && ageYears < SKINFOLD_MIN_AGE_YEARS;

  useEffect(() => {
    if (!tooYoung) return;
    toast.error("Los pliegues cutáneos se miden desde los 9 años.");
    navigate(profilePath, { replace: true });
  }, [tooYoung, navigate, profilePath]);

  const header = (
    <PageHeader
      title="Medición de pliegues cutáneos"
      subtitle="Seis sitios del lado derecho, dos lecturas por sitio."
      backTo={{ to: profilePath, label: "Volver al perfil" }}
    />
  );

  if (isLoading) {
    return <RouteFallback label="Cargando evaluación..." />;
  }

  if (isError || !record || ageYears === null) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="text-sm text-charcoal">
          {isError
            ? "No se pudo cargar la evaluación. Revisa tu conexión e intenta de nuevo."
            : "No encontramos esta evaluación."}{" "}
          <Link to={profilePath} className="font-medium text-link-blue underline">
            Volver al perfil
          </Link>
        </p>
      </div>
    );
  }

  if (tooYoung) {
    // La redirección ocurre en el efecto; no se monta el asistente.
    return null;
  }

  return (
    <div className="flex flex-col gap-6">
      {header}
      <SkinfoldWizard
        athleteId={athleteId}
        recordId={recordId}
        ageYears={ageYears}
        onDone={({ declinedAll }) => {
          toast.success(
            declinedAll
              ? "Quedó registrado que hoy prefirió no medirse."
              : "Medición de pliegues guardada.",
          );
          navigate(profilePath);
        }}
      />
    </div>
  );
}

export default SkinfoldCapturePage;
