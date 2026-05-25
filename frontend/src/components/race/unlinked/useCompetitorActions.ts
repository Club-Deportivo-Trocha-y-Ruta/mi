/**
 * useCompetitorActions — encapsula la coordinación entre link/unlink
 * mutations + toast feedback + estado de "athleteId en flight" para mostrar
 * spinner por sugerencia.
 *
 * Extraído de UnlinkedCompetitorsTab en B5.
 */
import { useState } from "react";

import {
  useLinkCompetitor,
  useUnlinkCompetitor,
} from "@/hooks/race/useUnlinkedCompetitors";
import { getCompetitorErrorMessage } from "@/lib/api/errorMessages";
import type {
  CompetitorLinkResponse,
  UnlinkedCompetitorItem,
} from "@/types/raceCompetitors.types";

import type { ToastVariant } from "./ToastBanner";

interface UseCompetitorActionsArgs {
  showToast: (variant: ToastVariant, message: string) => void;
}

export function useCompetitorActions({ showToast }: UseCompetitorActionsArgs) {
  const linkMutation = useLinkCompetitor();
  const unlinkMutation = useUnlinkCompetitor();
  const [linkingAthleteId, setLinkingAthleteId] = useState<number | null>(null);

  const handleLink = (
    competitorId: number,
    athleteId: number,
    competitor: UnlinkedCompetitorItem,
  ) => {
    setLinkingAthleteId(athleteId);
    linkMutation.mutate(
      { competitorId, athleteId },
      {
        onSuccess: (data: CompetitorLinkResponse) => {
          setLinkingAthleteId(null);
          // Nombre del athlete: lo resolvemos por sugerencia para evitar fetch extra
          const suggestion = competitor.suggestions.find(
            (s) => s.athlete_id === athleteId,
          );
          const athleteName = suggestion?.full_name ?? `Atleta #${athleteId}`;
          if (data.already_linked) {
            showToast("info", "Ya estaba enlazado, sin cambios.");
          } else {
            showToast(
              "success",
              `Enlazado: ${data.results_propagated} resultado${data.results_propagated === 1 ? "" : "s"} asociado${data.results_propagated === 1 ? "" : "s"} a ${athleteName}.`,
            );
          }
        },
        onError: (err) => {
          setLinkingAthleteId(null);
          showToast("error", getCompetitorErrorMessage(err));
        },
      },
    );
  };

  const handleUnlinkConfirm = (
    target: UnlinkedCompetitorItem,
    onComplete: () => void,
  ) => {
    unlinkMutation.mutate(
      { competitorId: target.id },
      {
        onSuccess: (data) => {
          onComplete();
          showToast(
            "info",
            data.was_linked
              ? `Desvinculado: ${data.results_propagated} resultado${data.results_propagated === 1 ? "" : "s"} sin atleta asociado.`
              : "El competidor no estaba enlazado.",
          );
        },
        onError: (err) => {
          onComplete();
          showToast("error", getCompetitorErrorMessage(err));
        },
      },
    );
  };

  return {
    linkMutation,
    unlinkMutation,
    linkingAthleteId,
    handleLink,
    handleUnlinkConfirm,
  };
}
