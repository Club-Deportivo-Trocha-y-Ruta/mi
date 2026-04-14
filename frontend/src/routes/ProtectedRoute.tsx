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
  const {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    isLoading,
    refreshSession,
  } = useAuthStore();

  useEffect(() => {
    if (!accessToken && refreshToken) {
      void refreshSession();
    }
  }, [accessToken, refreshSession, refreshToken]);

  if (isLoading) {
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
    return <Navigate to="/dashboard" replace />;
  }

  return <AppShell>{children}</AppShell>;
}
