/**
 * ConsentStatusPanel — Sección expandible que muestra el estado de consentimiento
 * de cada atleta vinculado al padre autenticado.
 *
 * Permite al padre:
 *   - Ver versión de política aceptada, fecha y estado (vigente/desactualizado/revocado)
 *   - Revocar consentimiento activo
 *   - Renovar consentimiento desactualizado
 *
 * Se renderiza en ParentDashboardPage como sección secundaria, por debajo de las cards
 * de atletas. La renovación urgente la maneja el ConsentRenewalModal bloqueante.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { formatDateMedium } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";
import { useRenewConsent } from "@/hooks/consent";
import { ConsentRenewalModal } from "./ConsentRenewalModal";
import { RevokeConsentDialog } from "./RevokeConsentDialog";

// ---------------------------------------------------------------------------
// Helpers de estado
// ---------------------------------------------------------------------------

type ConsentState = "current" | "outdated" | "revoked" | "never";

function getConsentState(athlete: AthleteConsentStatus): ConsentState {
  if (!athlete.current_consent) return "never";
  if (athlete.current_consent.withdrawn_at) return "revoked";
  if (!athlete.current_consent.is_current_policy) return "outdated";
  return "current";
}

/**
 * consentStatus — adaptador puro estado de consentimiento → { status, label }
 * para `StatusBadge` (contracts/status-vocabulary-sweep.md §6).
 */
export function consentStatus(state: ConsentState): { status: Status; label: string } {
  switch (state) {
    case "never":
      return { status: "neutral", label: "Sin consentimiento" };
    case "outdated":
      return { status: "warning", label: "Desactualizado" };
    case "revoked":
      return { status: "danger", label: "Revocado" };
    case "current":
      return { status: "success", label: "Vigente" };
  }
}

/**
 * aiConsentStatus — adaptador puro para la fila de sub-toggle IA embebida
 * (`AiConsentRow`, autorización de `third_party_sharing`), per
 * contracts/status-vocabulary-sweep.md §6.
 */
export function aiConsentStatus(isActive: boolean): { status: Status; label: string } {
  return isActive
    ? { status: "success", label: "IA: activa" }
    : { status: "neutral", label: "IA: no autorizada" };
}


// ---------------------------------------------------------------------------
// Sub-componente: fila de atleta
// ---------------------------------------------------------------------------

interface AthleteConsentRowProps {
  athlete: AthleteConsentStatus;
  activePolicy: PrivacyPolicySummary;
  onRenew: (athlete: AthleteConsentStatus) => void;
  onRevoke: (athlete: AthleteConsentStatus) => void;
}

function AthleteConsentRow({
  athlete,
  activePolicy,
  onRenew,
  onRevoke,
}: AthleteConsentRowProps) {
  const state = getConsentState(athlete);
  const badge = consentStatus(state);
  const consent = athlete.current_consent;

  const isRevocable = state === "current" || state === "outdated";
  const isRenewable = state === "outdated" || state === "never" || state === "revoked";

  return (
    <div className="flex flex-col gap-2 py-4">
      {/* Fila principal: info + acciones */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* Info del atleta */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-charcoal">{athlete.athlete_name}</p>
            <StatusBadge status={badge.status} label={badge.label} />
          </div>

          {/* Detalle de la versión aceptada */}
          {consent && !consent.withdrawn_at && (
            <p className="mt-0.5 text-xs text-mid-gray">
              Política {consent.policy_version} —{" "}
              {formatDateMedium(consent.consented_at)}
              {!consent.is_current_policy && (
                <span className="ml-1 text-amber-600">
                  (política actual: {activePolicy.version})
                </span>
              )}
            </p>
          )}
          {consent?.withdrawn_at && (
            <p className="mt-0.5 text-xs text-mid-gray">
              Revocado el {formatDateMedium(consent.withdrawn_at)}
            </p>
          )}
          {!consent && (
            <p className="mt-0.5 text-xs text-mid-gray">
              Nunca se registró consentimiento
            </p>
          )}
        </div>

        {/* Acciones */}
        <div className="flex shrink-0 gap-2">
          {isRenewable && (
            <button
              type="button"
              onClick={() => onRenew(athlete)}
              className={cn(
                "rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90",
                "shadow-ring",
              )}
            >
              {state === "revoked" ? "Dar consentimiento" : "Renovar"}
            </button>
          )}

          {isRevocable && (
            <button
              type="button"
              onClick={() => onRevoke(athlete)}
              className={cn(
                "rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition-opacity hover:opacity-80",
                "shadow-ring",
              )}
            >
              Revocar
            </button>
          )}
        </div>
      </div>

      {/* Fila IA: solo visible cuando hay consentimiento vigente */}
      <AiConsentRow athlete={athlete} activePolicy={activePolicy} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: fila de estado IA (third_party_sharing)
// ---------------------------------------------------------------------------

interface AiConsentRowProps {
  athlete: AthleteConsentStatus;
  activePolicy: PrivacyPolicySummary;
}

function AiConsentRow({ athlete, activePolicy }: AiConsentRowProps) {
  const { mutate: renew, isPending, isError } = useRenewConsent();
  const consent = athlete.current_consent;

  // Solo se muestra si hay consentimiento vigente (no revocado)
  if (!consent || consent.withdrawn_at) return null;

  const isAiActive = consent.grants.third_party_sharing === true;
  const aiBadge = aiConsentStatus(isAiActive);

  const handleToggleAi = () => {
    renew({
      athlete_id: athlete.athlete_id,
      policy_version: activePolicy.version,
      accept_data_collection: consent.grants.data_collection,
      accept_anthropometry: consent.grants.anthropometry,
      accept_third_party_sharing: !isAiActive,
    });
  };

  return (
    <div
      className="flex items-center justify-between gap-3 py-2"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        <StatusBadge status={aiBadge.status} label={aiBadge.label} />
        {isError && (
          <span className="text-xs text-red-600" role="alert">
            Error al actualizar. Intenta de nuevo.
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={handleToggleAi}
        disabled={isPending}
        className={cn(
          "flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-medium transition-opacity disabled:opacity-50 shadow-ring",
          isAiActive
            ? "bg-white text-red-600"
            : "bg-charcoal text-white hover:opacity-90",
        )}
        aria-label={
          isAiActive
            ? `Revocar autorización de IA para ${athlete.athlete_name}`
            : `Activar autorización de IA para ${athlete.athlete_name}`
        }
      >
        {isPending && (
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        )}
        {isAiActive ? "Revocar IA" : "Activar IA"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props del panel principal
// ---------------------------------------------------------------------------

interface ConsentStatusPanelProps {
  consentsPerAthlete: AthleteConsentStatus[];
  activePolicy: PrivacyPolicySummary;
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ConsentStatusPanel({
  consentsPerAthlete,
  activePolicy,
}: ConsentStatusPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Atleta para el que se está renovando o revocando desde el panel manual
  const [renewTarget, setRenewTarget] = useState<AthleteConsentStatus | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<AthleteConsentStatus | null>(null);

  const pendingCount = consentsPerAthlete.filter(
    (a) =>
      a.current_consent === null ||
      !a.current_consent.is_current_policy ||
      !!a.current_consent.withdrawn_at,
  ).length;

  return (
    <>
      <div className={cn("rounded-xl bg-white", "shadow-card")}>
        {/* Header con toggle */}
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex w-full items-center justify-between px-5 py-4 text-left"
          aria-expanded={isExpanded}
          aria-controls="consent-panel-body"
        >
          <div className="flex items-center gap-3">
            <div>
              <p
                className="font-display text-sm font-medium text-charcoal"
              >
                Gestionar consentimiento
              </p>
              <p className="text-xs text-mid-gray">
                {pendingCount > 0
                  ? `${pendingCount} atleta${pendingCount > 1 ? "s" : ""} con consentimiento pendiente`
                  : "Todos los consentimientos al día"}
              </p>
            </div>
            {pendingCount > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                {pendingCount}
              </span>
            )}
          </div>

          {isExpanded ? (
            <ChevronUp size={16} className="text-mid-gray" aria-hidden="true" />
          ) : (
            <ChevronDown size={16} className="text-mid-gray" aria-hidden="true" />
          )}
        </button>

        {/* Contenido expandible */}
        {isExpanded && (
          <div
            id="consent-panel-body"
            className="border-t border-[rgba(34,42,53,0.08)]"
          >
            <div className="divide-y divide-[rgba(34,42,53,0.06)] px-5">
              {consentsPerAthlete.map((athlete) => (
                <AthleteConsentRow
                  key={athlete.athlete_id}
                  athlete={athlete}
                  activePolicy={activePolicy}
                  onRenew={(a) => setRenewTarget(a)}
                  onRevoke={(a) => setRevokeTarget(a)}
                />
              ))}
            </div>

            {/* Nota legal */}
            <div className="px-5 pb-4 pt-2">
              <p className="text-xs text-mid-gray">
                El consentimiento se rige por la Ley 1581 de 2012 (Colombia). Puedes
                ejercer tus derechos de acceso, rectificación y supresión contactando
                al entrenador del club.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Modal de renovación desde el panel manual */}
      {renewTarget && (
        <ConsentRenewalModal
          athlete={renewTarget}
          activePolicy={activePolicy}
          onRenewed={() => {
            setRenewTarget(null);
            toast.success("Consentimiento actualizado correctamente.");
          }}
        />
      )}

      {/* Diálogo de revocación desde el panel manual */}
      {revokeTarget && (
        <RevokeConsentDialog
          athlete={revokeTarget}
          onClose={() => setRevokeTarget(null)}
          onSuccess={() => toast.success("Consentimiento revocado correctamente.")}
        />
      )}
    </>
  );
}
