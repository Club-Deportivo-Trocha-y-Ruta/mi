import { UserRole } from "@/types/enums";

/**
 * Ruta de aterrizaje por defecto según el rol del usuario autenticado.
 *
 * La "primera ruta" que ve un usuario con sesión válida es siempre su panel
 * principal (Dashboard para coach/admin, "Mis atletas" para padres), nunca el
 * formulario de login. El login se reserva para sesiones inexistentes o
 * vencidas (ver `ProtectedRoute`).
 *
 * Centralizada aquí para evitar divergencias entre `RootRedirect`, `LoginPage`
 * y los fallbacks de `ProtectedRoute`.
 */
export function landingPathForRole(role: UserRole | null | undefined): string {
  switch (role) {
    case UserRole.parent:
      return "/my-athletes";
    case UserRole.admin:
    case UserRole.coach:
      return "/dashboard";
    default:
      // Sin rol resuelto (incluye `athlete`, que no inicia sesión): que el
      // flujo de protección decida — termina en login si no hay sesión.
      return "/dashboard";
  }
}
