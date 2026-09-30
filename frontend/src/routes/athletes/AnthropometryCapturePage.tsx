import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { AnthropometryCapture } from "@/components/athletes/anthropometry-capture/AnthropometryCapture";
import { PageHeader } from "@/components/shared/PageHeader";
import { RouteFallback } from "@/components/shared/RouteFallback";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { skinfoldCapturePath } from "@/lib/bodyComposition/eligibility";

/**
 * AnthropometryCapturePage — `/athletes/:id/anthropometry/new` (feature 048,
 * T038). Coach/admin únicamente (guard en `App.tsx`).
 *
 * Monta la captura guiada/rápida. «Guardar y terminar» vuelve a la pestaña
 * «Antropometría»; «Guardar y agregar pliegues» abre el asistente del 046.
 * La fecha de nacimiento solo se pasa para calcular edad; nunca se muestra.
 */
export function AnthropometryCapturePage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const athleteId = Number(params.id);
  const validId = Number.isFinite(athleteId) && athleteId > 0;
  const profilePath = `/athletes/${athleteId}?tab=anthropometry`;

  const { data: athlete, isLoading, isError } = useAthlete(athleteId, validId);

  const header = (
    <PageHeader
      title="Nueva medición"
      subtitle={
        athlete ? `${athlete.first_name} ${athlete.last_name}` : "Peso, tallas y envergadura."
      }
      backTo={{ to: profilePath, label: "Volver al perfil" }}
    />
  );

  if (validId && isLoading) {
    return <RouteFallback label="Cargando deportista..." />;
  }

  if (!validId || isError || !athlete) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="text-sm text-charcoal">
          {isError
            ? "No se pudo cargar el deportista. Revisa tu conexión e intenta de nuevo."
            : "No encontramos este deportista."}{" "}
          <Link to="/athletes" className="font-medium text-link-blue underline">
            Volver a deportistas
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {header}
      <div className="rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline sm:p-6">
        <AnthropometryCapture
          athlete={{ id: athlete.id, sex: athlete.sex, birth_date: athlete.birth_date }}
          onDone={({ recordId, intent }) => {
            toast.success("Medición guardada.");
            if (intent === "skinfolds") {
              navigate(skinfoldCapturePath(athlete.id, recordId));
            } else {
              navigate(profilePath);
            }
          }}
        />
      </div>
    </div>
  );
}

export default AnthropometryCapturePage;
