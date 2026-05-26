import { useQuery } from "@tanstack/react-query";

import { getMyAthletes } from "@/api/parents";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

/**
 * Privacy R2: el queryKey incluye `userId` para aislar el cache por
 * cuenta. Sin esto, dos padres usando la misma tablet podrían reusar
 * datos cacheados del otro. `enabled` también lo exige como defensa en
 * profundidad: si por algún motivo accessToken existe pero user es null,
 * la query no dispara con un key huérfano.
 *
 * Bug #2 (race-analysis): `GET /api/parent-athletes/my-athletes` exige
 * `role=parent` en el backend. Si un coach/admin invoca el hook (p. ej.
 * porque comparte una página con padres), genera ruido 403 en logs y
 * en Network sin valor funcional. El hook ahora corta de raíz: la query
 * sólo se habilita cuando el usuario autenticado tiene rol `parent`.
 * Los callers que dependan de los datos ya deben proteger el componente
 * con un route guard — este `enabled` es defensa en profundidad.
 */
export function useMyAthletes() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const role = useAuthStore((s) => s.user?.role ?? null);

  return useQuery({
    queryKey: ["my-athletes", userId],
    queryFn: getMyAthletes,
    enabled: !!accessToken && userId !== null && role === UserRole.parent,
  });
}
