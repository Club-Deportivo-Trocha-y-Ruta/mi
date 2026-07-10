/**
 * Hooks de la conexión Strava de un atleta (feature 025, T024).
 *
 * `useStravaConnection` — query del estado actual (contracts/api.md §A GET
 * /connection). `useConnectStrava` — mutation que inicia el flujo OAuth
 * (POST /connect); el caller debe redirigir el navegador a `authorize_url`.
 * `useDisconnectStrava` — mutation de desconexión (DELETE /connection).
 *
 * Las mutations invalidan tanto la query de conexión como el listado de
 * actividades del atleta para que la UI refleje el nuevo estado sin
 * recargar la página.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  connectStrava,
  disconnectStrava,
  getStravaConnection,
} from "@/api/stravaActivities";

export function useStravaConnection(athleteId: number, enabled = true) {
  return useQuery({
    queryKey: ["strava-connection", athleteId],
    queryFn: ({ signal }) => getStravaConnection(athleteId, { signal }),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
  });
}

export function useConnectStrava(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => connectStrava(athleteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["strava-connection", athleteId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete-activities", athleteId],
      });
    },
  });
}

export function useDisconnectStrava(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => disconnectStrava(athleteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["strava-connection", athleteId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete-activities", athleteId],
      });
    },
  });
}
