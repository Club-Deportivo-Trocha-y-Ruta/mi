import { useEffect, useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
 * Feature 048 (T046): desde la jornada de medición grupal llega con
 * `?returnTo=/anthropometry/session`; al terminar o cancelar vuelve a la
 * cola. Solo se acepta EXACTAMENTE esa ruta interna (lista blanca): cualquier
 * otro valor se ignora para no abrir una redirección arbitraria.
 *
 * Privacidad: la pantalla no muestra el nombre del deportista ni ningún
 * dato identificable; los toasts no incluyen edad ni valores.
 */

/** Únicos destinos aceptados en `?returnTo=` (sin redirecciones abiertas). */
export const SKINFOLD_RETURN_PATHS = ["/anthropometry/session"] as const;

function safeReturnTo(value: string | null): string | null {
  return value !== null && (SKINFOLD_RETURN_PATHS as readonly string[]).includes(value)
    ? value
    : null;
}

export function SkinfoldCapturePage() {
  const params = useParams<{ id: string; recordId: string }>();
  const navigate = useNavigate();
  const athleteId = Number(params.id);
  const recordId = Number(params.recordId);
  const [searchParams] = useSearchParams();
  const returnTo = safeReturnTo(searchParams.get("returnTo"));
  const exitPath = returnTo ?? `/athletes/${athleteId}?tab=growth`;
  const backLabel = returnTo ? "Volver a la jornada" : "Volver al perfil";

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
    navigate(exitPath, { replace: true });
  }, [tooYoung, navigate, exitPath]);

  const header = (
    <PageHeader
      title="Medición de pliegues cutáneos"
      subtitle="Seis sitios del lado derecho, dos lecturas por sitio."
      backTo={{ to: exitPath, label: backLabel }}
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
          <Link to={exitPath} className="font-medium text-link-blue underline">
            {backLabel}
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
          navigate(exitPath);
        }}
      />
    </div>
  );
}

export default SkinfoldCapturePage;
