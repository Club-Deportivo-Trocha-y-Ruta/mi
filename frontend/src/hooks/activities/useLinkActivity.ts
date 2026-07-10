/**
 * useLinkActivity — mutation for PATCH /api/activities/{id}/link (feature
 * 025, T032, FR-007).
 *
 * Coach/admin only (backend-enforced 403 for parent/athlete roles — this
 * hook does not itself gate the action; the caller must not render the
 * link UI for other roles, see `LinkSessionDialog` / `ActivityCard`).
 *
 * `trainingSessionId: number` links/re-links; `null` unlinks. On success it
 * invalidates every cache the change can affect:
 *   - the coach review list (`activities-review` prefix — TanStack matches
 *     by queryKey prefix, so every filter/page combination is covered)
 *   - the athlete's own activity list (`athlete-activities`, athleteId)
 *   - the linked-activities section of the NEW session (T033,
 *     `session-activities`, sessionId) and of the PREVIOUS session when
 *     re-linking/unlinking, so both session-detail views drop/gain the row
 *     immediately without a manual refresh.
 *   - the session-detail redesign's unlinked-near-date lookup
 *     (`unlinked-activities-near-date` prefix, session-detail-redesign.md
 *     §3.5) — without this, linking from the new row-level "Enlazar"
 *     action leaves the activity visible in BOTH the "sin enlazar" state
 *     and (after the `session-activities` invalidation above) the linked
 *     state, until the coach reloads the page.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { linkActivity } from "@/api/stravaActivities";
import type { ActivityOut } from "@/types/strava.types";

export interface LinkActivityVariables {
  activityId: number;
  /** New session to link to; `null` unlinks. */
  trainingSessionId: number | null;
  /** Owning athlete of the activity — invalidates that athlete's list. */
  athleteId: number;
  /** Session the activity was linked to before this mutation, if any. */
  previousSessionId?: number | null;
}

export function useLinkActivity() {
  const queryClient = useQueryClient();

  return useMutation<ActivityOut, unknown, LinkActivityVariables>({
    mutationFn: ({ activityId, trainingSessionId }) =>
      linkActivity(activityId, trainingSessionId),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["activities-review"] });
      void queryClient.invalidateQueries({
        queryKey: ["athlete-activities", variables.athleteId],
      });
      void queryClient.invalidateQueries({ queryKey: ["unlinked-activities-near-date"] });
      if (variables.trainingSessionId != null) {
        void queryClient.invalidateQueries({
          queryKey: ["session-activities", variables.trainingSessionId],
        });
      }
      if (
        variables.previousSessionId != null &&
        variables.previousSessionId !== variables.trainingSessionId
      ) {
        void queryClient.invalidateQueries({
          queryKey: ["session-activities", variables.previousSessionId],
        });
      }
    },
  });
}
