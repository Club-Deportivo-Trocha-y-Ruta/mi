import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

interface AthleteLinkProps {
  athleteId: number;
  /** Usualmente el nombre del deportista. */
  children: ReactNode;
  /** Tab a preseleccionar en el detalle, vía query param `?tab=`. */
  tab?: string;
  className?: string;
}

/**
 * `/athletes/:id` está restringida a `UserRole.coach` (ver `src/App.tsx`) —
 * admin NO tiene acceso y `ProtectedRoute` lo redirige en silencio al
 * dashboard. Mantener sincronizado con el `allowedRoles` de esa ruta.
 */
const ATHLETE_DETAIL_ALLOWED_ROLES: readonly UserRole[] = [UserRole.coach];

/**
 * Enlace al detalle de un deportista consciente del RBAC de `/athletes/:id`.
 * Varias superficies visibles para admin apuntaban ahí con un <Link> normal;
 * como esa ruta es coach-only, ProtectedRoute rebotaba a admin de vuelta al
 * dashboard en silencio. Aquí, si el rol actual no tiene acceso, se renderiza
 * un <span> con las mismas clases/contenido en vez de un enlace que nunca
 * debería seguirse.
 */
export function AthleteLink({ athleteId, children, tab, className }: AthleteLinkProps) {
  const role = useAuthStore((state) => state.user?.role);
  const canNavigate = role !== undefined && ATHLETE_DETAIL_ALLOWED_ROLES.includes(role);

  if (!canNavigate) {
    return <span className={className}>{children}</span>;
  }

  const to = tab ? `/athletes/${athleteId}?tab=${tab}` : `/athletes/${athleteId}`;

  return (
    <Link to={to} className={className}>
      {children}
    </Link>
  );
}
