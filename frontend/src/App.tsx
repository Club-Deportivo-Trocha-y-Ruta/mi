import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Profile module (lazy — all authenticated roles)
const ProfilePage = lazy(() =>
  import("@/routes/profile/ProfilePage").then((m) => ({
    default: m.ProfilePage,
  })),
);
const ConfirmEmailChangePage = lazy(() =>
  import("@/routes/profile/ConfirmEmailChangePage").then((m) => ({
    default: m.ConfirmEmailChangePage,
  })),
);

// AI Session Assistant (lazy — coach/admin only)
const SessionAssistantPage = lazy(() =>
  import("@/routes/training/SessionAssistantPage").then((m) => ({
    default: m.SessionAssistantPage,
  })),
);

import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { setQueryClient } from "@/lib/queryClientHandle";
import { landingPathForRole } from "@/lib/landing";
import { TooltipProvider } from "@/components/ui/tooltip";

// PR1: índice slim de análisis IA (solo vistas cross-válida, sin lanzador ni chat).
const InsightsHubPage = lazy(() =>
  import("@/routes/competitions/insights/InsightsHubPage").then((m) => ({
    default: m.InsightsHubPage,
  })),
);
// Paso 3: página de competidores sin enlazar (wrapper sobre UnlinkedCompetitorsTab).
const UnlinkedCompetitorsPage = lazy(() =>
  import("@/routes/competitions/UnlinkedCompetitorsPage").then((m) => ({
    default: m.UnlinkedCompetitorsPage,
  })),
);
// PR3: subpáginas IA cross-válida bajo /competitions/insights/* (lazy por chunk).
const SeasonInsightsPage = lazy(
  () => import("@/routes/competitions/insights/SeasonInsightsPage"),
);
const AthleteInsightsPage = lazy(
  () => import("@/routes/competitions/insights/AthleteInsightsPage"),
);
const ClubInsightsPage = lazy(
  () => import("@/routes/competitions/insights/ClubInsightsPage"),
);
import { useAuthStore } from "@/store/auth.store";
import { AIHealthPage } from "@/routes/admin/AIHealthPage";
import { LoginPage } from "@/routes/auth/LoginPage";
import { DashboardPage } from "@/routes/dashboard/DashboardPage";
import { AthletesListPage } from "@/routes/athletes/AthletesListPage";
import { AthleteDetailPage } from "@/routes/athletes/AthleteDetailPage";
import { AthleteFormPage } from "@/routes/athletes/AthleteFormPage";
import { ParentsListPage } from "@/routes/parents/ParentsListPage";
import { ParentDetailPage } from "@/routes/parents/ParentDetailPage";
import { ParentDashboardPage } from "@/routes/parents/ParentDashboardPage";
import { MyAthleteDetailPage } from "@/routes/parents/MyAthleteDetailPage";
import { OnboardingPage } from "@/routes/auth/OnboardingPage";
import { ForgotPasswordPage } from "@/routes/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "@/routes/auth/ResetPasswordPage";
import { PrivacyPage } from "@/routes/PrivacyPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { GonePage } from "@/routes/GonePage";
import { SessionsListPage } from "@/routes/training/SessionsListPage";
import { SessionFormPage } from "@/routes/training/SessionFormPage";
import { SessionDetailPage } from "@/routes/training/SessionDetailPage";
import { ReportsListPage } from "@/routes/training/ReportsListPage";
import { ReportDetailPage } from "@/routes/training/ReportDetailPage";
import { ProjectProfilePage } from "@/routes/training/ProjectProfilePage";
import { AthleteNewslettersDashboardPage } from "@/routes/training/AthleteNewslettersDashboardPage";
import { AthleteNewsletterDetailPage } from "@/routes/training/AthleteNewsletterDetailPage";
import { ParentSessionsPage } from "@/routes/parents/training/ParentSessionsPage";
import { ParentSessionDetailPage } from "@/routes/parents/training/ParentSessionDetailPage";
import { ParentMonthlyOverviewPage } from "@/routes/parents/training/ParentMonthlyOverviewPage";
import { CalendarPage } from "@/routes/calendar/CalendarPage";
import { EventFormPage } from "@/routes/calendar/EventFormPage";
import { ParentCalendarPage } from "@/routes/parents/calendar/ParentCalendarPage";
import { ParentEventDetailPage } from "@/routes/parents/calendar/ParentEventDetailPage";
import { CompetitionsListPage } from "@/routes/competitions/CompetitionsListPage";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";
import { CompetitionImportPage } from "@/routes/competitions/CompetitionImportPage";
import { UserRole } from "@/types/enums";

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
  return <Navigate to={landingPathForRole(user?.role)} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200} skipDelayDuration={300}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/recuperar-contrasena" element={<ForgotPasswordPage />} />
        <Route path="/restablecer-contrasena" element={<ResetPasswordPage />} />
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
          path="/training/sessions/assistant"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando asistente IA...
                  </div>
                }
              >
                <SessionAssistantPage />
              </Suspense>
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
          path="/training/reports/project-profile"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <ProjectProfilePage />
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
          path="/training/athlete-newsletters"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <AthleteNewslettersDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/athlete-newsletters/:athleteId/:newsletterId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <AthleteNewsletterDetailPage />
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

        {/* ── PR7 (D7): legacy club-insights deprecado definitivamente (410).
              Tras un ciclo completo con redirect 301, ahora muestra GonePage. ── */}
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <GonePage />
            </ProtectedRoute>
          }
        />

        {/* ── Competencias (coach/admin) ── */}
        <Route
          path="/competitions"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionsListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/new"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionFormPage mode="create" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/import"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionImportPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id/edit"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionFormPage mode="edit" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id/import"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <CompetitionImportPage />
            </ProtectedRoute>
          }
        />

        {/* ── Análisis IA carreras — índice slim (solo vistas cross-válida).
              Rediseño: sin lanzador, sin chat, sin import. ── */}
        <Route
          path="/competitions/insights"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando análisis IA...
                  </div>
                }
              >
                <InsightsHubPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Competidores sin enlazar — reubicado desde el hub ── */}
        <Route
          path="/competitions/unlinked"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando competidores...
                  </div>
                }
              >
                <UnlinkedCompetitorsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── PR3: subpáginas IA cross-válida. RBAC coach/admin (parent →
              redirect por ProtectedRoute; backend devuelve 403). ── */}
        <Route
          path="/competitions/insights/club"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando análisis del club...
                  </div>
                }
              >
                <ClubInsightsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/insights/season/:year"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando panorama de temporada...
                  </div>
                }
              >
                <SeasonInsightsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/insights/athletes/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando análisis del deportista...
                  </div>
                }
              >
                <AthleteInsightsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── PR7 (D7): ruta legacy del módulo IA deprecada definitivamente (410).
              Tras un ciclo completo con redirect 301, ahora muestra GonePage. ── */}
        <Route
          path="/coach/race-analysis"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <GonePage />
            </ProtectedRoute>
          }
        />

        {/* ── Perfil de usuario (todos los roles autenticados) ── */}
        <Route
          path="/perfil"
          element={
            <ProtectedRoute>
              <Suspense
                fallback={
                  <div className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray">
                    Cargando perfil...
                  </div>
                }
              >
                <ProfilePage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Confirmación de cambio de correo (pública) ── */}
        <Route
          path="/confirmar-correo"
          element={
            <Suspense
              fallback={
                <div className="flex min-h-screen items-center justify-center text-sm text-mid-gray">
                  Verificando enlace...
                </div>
              }
            >
              <ConfirmEmailChangePage />
            </Suspense>
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
      </TooltipProvider>
    </QueryClientProvider>
  );
}
