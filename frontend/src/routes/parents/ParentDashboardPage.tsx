import { useState, useEffect } from "react";

import { ChildCard } from "@/components/parents/portal/ChildCard";
import { ConsentRenewalModal } from "@/components/consent/ConsentRenewalModal";
import { ConsentStatusPanel } from "@/components/consent/ConsentStatusPanel";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useMyConsentStatus } from "@/hooks/consent";
import type { AthleteConsentStatus } from "@/types/consent";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function SkeletonCard() {
  return <div className="h-48 animate-pulse rounded-xl bg-light-gray" />;
}

// ---------------------------------------------------------------------------
// Lógica de cola de modales bloqueantes
// ---------------------------------------------------------------------------

/**
 * Construye la cola de atletas que necesitan renovar consentimiento.
 *
 * Un atleta entra en la cola si:
 *   - Nunca dio consentimiento (current_consent === null)
 *   - Su consentimiento está desactualizado (is_current_policy === false)
 *
 * Los revocados NO entran en la cola bloqueante — el padre revocó a propósito,
 * no es un error. Puede renovar desde el ConsentStatusPanel cuando quiera.
 */
function buildRenewalQueue(
  consentsPerAthlete: AthleteConsentStatus[],
): AthleteConsentStatus[] {
  return consentsPerAthlete.filter(
    (a) =>
      a.current_consent === null ||
      (!a.current_consent.withdrawn_at && !a.current_consent.is_current_policy),
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ParentDashboardPage() {
  const { data: athletes, isLoading, isError } = useMyAthletes();
  const { data: consentStatus, isLoading: isConsentLoading } = useMyConsentStatus();

  // Cola de atletas pendientes de renovación. Se inicializa una sola vez cuando
  // llegan los datos y no vuelve a recalcularse automáticamente — la invalidación
  // de "my-consent" por useRenewConsent hace que consentStatus cambie, lo que
  // elimina el atleta de la cola via el useEffect de abajo.
  const [renewalQueue, setRenewalQueue] = useState<AthleteConsentStatus[]>([]);
  const [currentQueueIndex, setCurrentQueueIndex] = useState(0);

  useEffect(() => {
    if (consentStatus) {
      const queue = buildRenewalQueue(consentStatus.consents_per_athlete);
      setRenewalQueue(queue);
      setCurrentQueueIndex(0);
    }
  }, [consentStatus]);

  // Atleta actualmente bloqueante (primero de la cola)
  const pendingAthlete = renewalQueue[currentQueueIndex] ?? null;

  const handleAthleteRenewed = () => {
    // Avanzar en la cola. Cuando currentQueueIndex >= renewalQueue.length,
    // pendingAthlete queda null y el modal no se renderiza.
    setCurrentQueueIndex((prev) => prev + 1);
  };

  return (
    <section className="space-y-6">
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Mis Atletas
        </h1>
        <p className="mt-1 text-sm text-mid-gray">Seguimiento de tus deportistas</p>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {isError && !isLoading && (
        <div
          className="rounded-xl bg-white px-5 py-6"
          style={{ boxShadow: CARD_SHADOW }}
        >
          <p className="text-sm text-mid-gray">
            No fue posible cargar tus atletas. Intenta de nuevo.
          </p>
        </div>
      )}

      {!isLoading && !isError && athletes !== undefined && athletes.length === 0 && (
        <div
          className="rounded-xl bg-white px-5 py-6"
          style={{ boxShadow: CARD_SHADOW }}
        >
          <p className="text-sm text-mid-gray">
            No tienes atletas vinculados aún. Contacta a tu entrenador.
          </p>
        </div>
      )}

      {!isLoading && !isError && athletes && athletes.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {athletes.map((athlete) => (
            <ChildCard key={athlete.athlete_id} athlete={athlete} />
          ))}
        </div>
      )}

      {/* Panel de gestión de consentimiento — visible cuando hay datos */}
      {!isConsentLoading && consentStatus && (
        <ConsentStatusPanel
          consentsPerAthlete={consentStatus.consents_per_athlete}
          activePolicy={consentStatus.active_policy}
        />
      )}

      {/* Modal bloqueante de renovación — un atleta a la vez */}
      {pendingAthlete && consentStatus && (
        <ConsentRenewalModal
          athlete={pendingAthlete}
          activePolicy={consentStatus.active_policy}
          onRenewed={handleAthleteRenewed}
        />
      )}
    </section>
  );
}
