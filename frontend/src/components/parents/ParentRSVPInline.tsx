import { useState } from "react";
import { Check, X, HelpCircle } from "lucide-react";

import { useRSVPEvent } from "@/api/calendar";
import type { RSVPStatus } from "@/types/calendar.types";

interface ParentRSVPInlineProps {
  eventId: number;
  athleteId: number;
  currentRSVP: RSVPStatus;
  disabled?: boolean;
}

interface RSVPOption {
  value: RSVPStatus;
  label: string;
  icon: React.ReactNode;
  activeClasses: string;
  inactiveClasses: string;
}

const RSVP_OPTIONS: RSVPOption[] = [
  {
    value: "accepted",
    label: "Aceptar",
    icon: <Check size={14} aria-hidden="true" />,
    activeClasses: "bg-green-600 text-white border-green-600",
    inactiveClasses: "border-green-600 text-green-700 hover:bg-green-50",
  },
  {
    value: "declined",
    label: "Declinar",
    icon: <X size={14} aria-hidden="true" />,
    activeClasses: "bg-red-600 text-white border-red-600",
    inactiveClasses: "border-red-600 text-red-700 hover:bg-red-50",
  },
  {
    value: "tentative",
    label: "Tentativo",
    icon: <HelpCircle size={14} aria-hidden="true" />,
    activeClasses: "bg-amber-500 text-white border-amber-500",
    inactiveClasses: "border-amber-500 text-amber-700 hover:bg-amber-50",
  },
];

export function ParentRSVPInline({
  eventId,
  athleteId,
  currentRSVP,
  disabled = false,
}: ParentRSVPInlineProps) {
  const [optimisticRSVP, setOptimisticRSVP] = useState<RSVPStatus>(currentRSVP);
  const [savedFeedback, setSavedFeedback] = useState(false);

  const rsvpMutation = useRSVPEvent(eventId);

  function handleRSVP(status: RSVPStatus) {
    if (disabled || rsvpMutation.isPending) return;
    const previous = optimisticRSVP;
    setOptimisticRSVP(status);

    rsvpMutation.mutate(
      { athlete_id: athleteId, rsvp_status: status },
      {
        onSuccess: () => {
          setSavedFeedback(true);
          setTimeout(() => setSavedFeedback(false), 2000);
        },
        onError: () => {
          // revert optimistic update on error
          setOptimisticRSVP(previous);
        },
      },
    );
  }

  const isDisabled = disabled || rsvpMutation.isPending;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
        Responder convocatoria
      </p>
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="Estado de asistencia al evento"
      >
        {RSVP_OPTIONS.map((option) => {
          const isActive = optimisticRSVP === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => handleRSVP(option.value)}
              disabled={isDisabled}
              aria-pressed={isActive}
              className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isActive ? option.activeClasses : option.inactiveClasses
              }`}
            >
              {option.icon}
              {option.label}
            </button>
          );
        })}
      </div>
      {savedFeedback && (
        <p
          className="text-xs font-medium text-green-700"
          role="status"
          aria-live="polite"
          data-testid="rsvp-saved-feedback"
        >
          Respuesta guardada
        </p>
      )}
      {rsvpMutation.isError && (
        <p
          className="text-xs text-red-600"
          role="alert"
          data-testid="rsvp-error"
        >
          No se pudo guardar la respuesta. Intenta de nuevo.
        </p>
      )}
    </div>
  );
}
