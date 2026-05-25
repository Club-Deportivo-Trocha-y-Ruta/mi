import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { AppErrorFallback } from "@/components/common/AppErrorFallback";
import { RouteFallback } from "@/components/common/RouteFallback";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { setQueryClient } from "@/lib/queryClientHandle";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuthStore } from "@/store/auth.store";
import { AIHealthPage } from "@/routes/admin/AIHealthPage";
import { LoginPage } from "@/routes/auth/LoginPage";
import { DashboardPage } from "@/routes/dashboard/DashboardPage";
import { ParentsListPage } from "@/routes/parents/ParentsListPage";
import { ParentDetailPage } from "@/routes/parents/ParentDetailPage";
import { OnboardingPage } from "@/routes/auth/OnboardingPage";
import { PrivacyPage } from "@/routes/PrivacyPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { SessionsListPage } from "@/routes/training/SessionsListPage";
import { SessionFormPage } from "@/routes/training/SessionFormPage";
import { SessionDetailPage } from "@/routes/training/SessionDetailPage";
import { CalendarPage } from "@/routes/calendar/CalendarPage";
import { UserRole } from "@/types/enums";

// ─── Lazy routes ──────────────────────────────────────────────────────────────
// Race-analysis bundle es pesado (react-markdown + AI hooks) y sólo coach/admin
// lo abren ocasionalmente.
const RaceAnalysisPage = lazy(() => import("@/routes/results/RaceAnalysisPage"));

// Rutas parent-only — el coach nunca las carga, así que evitamos el costo en
// el bundle inicial para coach/admin (la mayoría de logins).
const ParentDashboardPage = lazy(() =>
  import("@/routes/parents/ParentDashboardPage").then((m) => ({
    default: m.ParentDashboardPage,
  })),
);
const MyAthleteDetailPage = lazy(() =>
  import("@/routes/parents/MyAthleteDetailPage").then((m) => ({
    default: m.MyAthleteDetailPage,
  })),
);
const ParentSessionsPage = lazy(() =>
  import("@/routes/parents/training/ParentSessionsPage").then((m) => ({
    default: m.ParentSessionsPage,
  })),
);
const ParentSessionDetailPage = lazy(() =>
  import("@/routes/parents/training/ParentSessionDetailPage").then((m) => ({
    default: m.ParentSessionDetailPage,
  })),
);
const ParentMonthlyOverviewPage = lazy(() =>
  import("@/routes/parents/training/ParentMonthlyOverviewPage").then((m) => ({
    default: m.ParentMonthlyOverviewPage,
  })),
);
const ParentCalendarPage = lazy(() =>
  import("@/routes/parents/calendar/ParentCalendarPage").then((m) => ({
    default: m.ParentCalendarPage,
  })),
);
const ParentEventDetailPage = lazy(() =>
  import("@/routes/parents/calendar/ParentEventDetailPage").then((m) => ({
    default: m.ParentEventDetailPage,
  })),
);

// Coach-only de bajo uso: athletes CRUD, reports, event-form.
const AthletesListPage = lazy(() =>
  import("@/routes/athletes/AthletesListPage").then((m) => ({
    default: m.AthletesListPage,
  })),
);
const AthleteDetailPage = lazy(() =>
  import("@/routes/athletes/AthleteDetailPage").then((m) => ({
    default: m.AthleteDetailPage,
  })),
);
const AthleteFormPage = lazy(() =>
  import("@/routes/athletes/AthleteFormPage").then((m) => ({
    default: m.AthleteFormPage,
  })),
);
const EventFormPage = lazy(() =>
  import("@/routes/calendar/EventFormPage").then((m) => ({
    default: m.EventFormPage,
  })),
);
const ReportsListPage = lazy(() =>
  import("@/routes/training/ReportsListPage").then((m) => ({
    default: m.ReportsListPage,
  })),
);
const ReportDetailPage = lazy(() =>
  import("@/routes/training/ReportDetailPage").then((m) => ({
    default: m.ReportDetailPage,
  })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 3,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
    },
  },
});

// Privacy R1: registramos el QueryClient en el singleton para que el
// auth store (Zustand) pueda invocar `queryClient.clear()` en logout()
// y evitar fugas de cache entre cuentas en máquinas compartidas.
setQueryClient(queryClient);

function RootRedirect() {
  const user = useAuthStore((s) => s.user);
  const to = user?.role === UserRole.parent ? "/my-athletes" : "/dashboard";
  return <Navigate to={to} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200} skipDelayDuration={300}>
        <ErrorBoundary FallbackComponent={AppErrorFallback}>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <RootRedirect />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.admin, UserRole.coach]}>
                    <DashboardPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/athletes"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <AthletesListPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/athletes/new"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <AthleteFormPage mode="create" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/athletes/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <AthleteDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/athletes/:id/edit"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <AthleteFormPage mode="edit" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <ParentsListPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach]}>
                    <ParentDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/my-athletes"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentDashboardPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/my-athletes/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <MyAthleteDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/ai"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.admin]}>
                    <AIHealthPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/sessions"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <SessionsListPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/sessions/new"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <SessionFormPage mode="create" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/sessions/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <SessionDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/sessions/:id/edit"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <SessionFormPage mode="edit" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/reports"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <ReportsListPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/training/reports/:year/:month"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <ReportDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents/training/sessions"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentSessionsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents/training/sessions/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentSessionDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents/training/overview"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentMonthlyOverviewPage />
                  </ProtectedRoute>
                }
              />
              {/* ── Calendar routes (coach/admin) ── */}
              <Route
                path="/calendar"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <CalendarPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/calendar/events/new"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <EventFormPage mode="create" />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/calendar/events/:id/edit"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <EventFormPage mode="edit" />
                  </ProtectedRoute>
                }
              />

              {/* ── Calendar routes (parent) ── */}
              <Route
                path="/parents/calendar"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentCalendarPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/parents/calendar/events/:id"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.parent]}>
                    <ParentEventDetailPage />
                  </ProtectedRoute>
                }
              />

              {/* ── Race analysis v2 (coach/admin) ── */}
              <Route
                path="/coach/race-analysis"
                element={
                  <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
                    <RaceAnalysisPage />
                  </ProtectedRoute>
                }
              />

              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route path="/privacidad" element={<PrivacyPage />} />
              <Route
                path="/registro-padre"
                element={<Navigate to="/onboarding" replace />}
              />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
