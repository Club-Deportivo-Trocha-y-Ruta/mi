import { useEffect, useState } from "react";

import { AlertsCard } from "@/components/parents/home/AlertsCard";
import { AthleteHomeBlock } from "@/components/parents/home/AthleteHomeBlock";
import { ChildCard } from "@/components/parents/portal/ChildCard";
import { ConsentRenewalModal } from "@/components/consent/ConsentRenewalModal";
import { ConsentStatusPanel } from "@/components/consent/ConsentStatusPanel";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveAthlete } from "@/hooks/parents/useActiveAthlete";
import { useMyConsentStatus } from "@/hooks/consent";
import type { AthleteConsentStatus } from "@/types/consent";

function SkeletonCard() {
  return <Skeleton className="h-48 rounded-xl" />;
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
// Componente principal — Wave 4: home feed reorganizado
// ---------------------------------------------------------------------------
//
// Orden vertical:
//   1. AlertsCard (consentimiento — solo si aplica)
//   2. Bloque(s) home feed:
//        - Si hay atleta activo (1 hijo, o multi-hijo con selección):
//          un solo bloque sin encabezado.
//        - Si multi-hijo sin selección: N bloques apilados, cada uno
//          con encabezado de nombre + toggle "Ver todos los hijos" para
//          confirmar/cambiar la elección.
//   3. ChildCard grid (perfil de antropometría/PHV — acceso a detalle).
//   4. ConsentStatusPanel (denso, último).
//
// Mantenemos URL /my-athletes intacta. El ConsentRenewalModal sigue siendo
// bloqueante: no se toca su semántica.

export function ParentDashboardPage() {
  const {
    athlete,
    athletes,
    isLoading,
    activeAthleteId,
    setActiveAthlete,
  } = useActiveAthlete();
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
    setCurrentQueueIndex((prev) => prev + 1);
  };

  const hasAthletes = athletes.length > 0;
  // Multi-hijo sin selección activa explícita → apilamos un bloque por hijo.
  const showStacked =
    hasAthletes && athletes.length > 1 && activeAthleteId === null;
  // Multi-hijo con selección → mostramos toggle "Ver todos".
  const showToggleAll = athletes.length > 1 && activeAthleteId !== null;

  return (
    <section className="space-y-6">
      <div>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Mis Atletas
        </h1>
        <p className="mt-1 text-sm text-mid-gray">Seguimiento de tus deportistas</p>
      </div>

      {/* 1. Alertas críticas (consentimiento) */}
      <AlertsCard
        consentsPerAthlete={consentStatus?.consents_per_athlete}
        isLoading={isConsentLoading}
      />

      {/* 2. Home feed por atleta */}
      {isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando tu resumen"
          className="space-y-3"
        >
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      )}

      {!isLoading && hasAthletes && athlete && !showStacked && (
        <>
          {showToggleAll && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setActiveAthlete(null)}
                className="rounded-lg px-3 py-2 text-sm font-medium text-link-blue transition-colors hover:bg-light-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                data-testid="see-all-athletes"
              >
                Ver todos los hijos
              </button>
            </div>
          )}
          <AthleteHomeBlock athlete={athlete} />
        </>
      )}

      {!isLoading && showStacked && (
        <div className="space-y-6">
          {athletes.map((a) => (
            <AthleteHomeBlock key={a.athlete_id} athlete={a} showHeader />
          ))}
        </div>
      )}

      {/* 3. Grid de perfil deportivo (acceso a detalle de cada hijo) */}
      {isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando mis atletas"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {!isLoading && hasAthletes && (
        <div>
          <h2
            className="font-display mb-3 text-base text-charcoal"
          >
            Perfil deportivo
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {athletes.map((a) => (
              <ChildCard key={a.athlete_id} athlete={a} />
            ))}
          </div>
        </div>
      )}

      {!isLoading && athletes !== undefined && athletes.length === 0 && (
        <Card className="px-5 py-6">
          <p className="text-sm text-mid-gray">
            No tienes atletas vinculados aún. Contacta a tu entrenador.
          </p>
        </Card>
      )}

      {/* 4. Panel denso de gestión de consentimiento — al final */}
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
