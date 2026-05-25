import type { ReactNode } from "react";
import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

interface ProtectedRouteProps {
  children: ReactNode;
  allowedRoles?: UserRole[];
}

export function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const location = useLocation();
  // Selectores atómicos: evita que cambios en cualquier otro slice del
  // auth store re-renderen ProtectedRoute (que envuelve toda la app).
  const accessToken = useAuthStore((s) => s.accessToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const refreshSession = useAuthStore((s) => s.refreshSession);

  useEffect(() => {
    if (!accessToken && refreshToken) {
      void refreshSession();
    }
  }, [accessToken, refreshSession, refreshToken]);

  // Bloquea el render de hijos mientras el accessToken aún no está disponible
  // pero hay un refreshToken → evita que las queries se disparen sin token.
  if (isLoading || (!accessToken && !!refreshToken)) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-600">
        Cargando sesión...
      </div>
    );
  }

  if (!isAuthenticated && !accessToken && !refreshToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    const ROLE_FALLBACKS: Record<UserRole, string> = {
      [UserRole.admin]: "/dashboard",
      [UserRole.coach]: "/dashboard",
      [UserRole.parent]: "/my-athletes",
      [UserRole.athlete]: "/login",
    };
    const fallback = ROLE_FALLBACKS[user.role] ?? "/login";
    return <Navigate to={fallback} replace />;
  }

  return <AppShell>{children}</AppShell>;
}
