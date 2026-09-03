import { lazy, Suspense, useMemo } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";

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
import {
  buildBuster,
  createQueryPersister,
  PERSIST_MAX_AGE,
} from "@/lib/queryPersister";
import { shouldDehydrateQuery } from "@/lib/persistAllowList";
import { landingPathForRole } from "@/lib/landing";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { RouteFallback } from "@/components/shared/RouteFallback";

// Paso 3: página de competidores sin enlazar (wrapper sobre UnlinkedCompetitorsTab).
const UnlinkedCompetitorsPage = lazy(() =>
  import("@/routes/competitions/UnlinkedCompetitorsPage").then((m) => ({
    default: m.UnlinkedCompetitorsPage,
  })),
);
// Panorama de temporada (única vista no duplicada del extinto hub IA cross-válida;
// relocada fuera de competitions/insights/ en feature 029).
const SeasonInsightsPage = lazy(
  () => import("@/routes/competitions/SeasonInsightsPage"),
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
import { ParentNewsletterListPage } from "@/routes/parents/newsletters/ParentNewsletterListPage";
import { ParentNewsletterPage } from "@/routes/parents/newsletters/ParentNewsletterPage";
import { OnboardingPage } from "@/routes/auth/OnboardingPage";
import { ForgotPasswordPage } from "@/routes/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "@/routes/auth/ResetPasswordPage";
import { PrivacyPage } from "@/routes/PrivacyPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { SessionsListPage } from "@/routes/training/SessionsListPage";
import { SessionFormPage } from "@/routes/training/SessionFormPage";
import { SessionDetailPage } from "@/routes/training/SessionDetailPage";
import { ReportsListPage } from "@/routes/training/ReportsListPage";
import { ReportDetailPage } from "@/routes/training/ReportDetailPage";
import { ProjectProfilePage } from "@/routes/training/ProjectProfilePage";
import { AthleteNewslettersDashboardPage } from "@/routes/training/AthleteNewslettersDashboardPage";
import { AthleteNewsletterStudioPage } from "@/routes/training/AthleteNewsletterStudioPage";
import { ParentSessionsPage } from "@/routes/parents/training/ParentSessionsPage";
import { ParentSessionDetailPage } from "@/routes/parents/training/ParentSessionDetailPage";
import { ParentMonthlyOverviewPage } from "@/routes/parents/training/ParentMonthlyOverviewPage";
import { CalendarPage } from "@/routes/calendar/CalendarPage";
import { EventFormPage } from "@/routes/calendar/EventFormPage";
import { ParentCalendarPage } from "@/routes/parents/calendar/ParentCalendarPage";
import { ParentEventDetailPage } from "@/routes/parents/calendar/ParentEventDetailPage";
import { ParentCompetitionResultsPage } from "@/routes/parents/competitions/ParentCompetitionResultsPage";
import { CompetitionsListPage } from "@/routes/competitions/CompetitionsListPage";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";
import { CompetitionImportPage } from "@/routes/competitions/CompetitionImportPage";
import { UserRole } from "@/types/enums";

// Strava Activity Sync (feature 025) — revisión de actividades, coach/admin only (lazy)
const ActivityReviewPage = lazy(() =>
  import("@/routes/activities/ActivityReviewPage").then((m) => ({
    default: m.ActivityReviewPage,
  })),
);

// Structured Interval Training (feature 026) — plan-vs-actual + biblioteca de
// plantillas, coach/admin only (lazy)
const ActivityMatchPage = lazy(() =>
  import("@/routes/training/ActivityMatchPage").then((m) => ({
    default: m.ActivityMatchPage,
  })),
);
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      // Feature 012: 24 h para que la persistencia conserve datos entre
      // recargas (la persistencia solo guarda queries que el GC no haya
      // evacuado; el default de 5 min haría inútil el restore).
      gcTime: 24 * 60 * 60 * 1000,
      retry: 3,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
    },
  },
});

// Privacy R1: registramos el QueryClient en el singleton para que el
// auth store (Zustand) pueda invocar `queryClient.clear()` en logout()
// y evitar fugas de cache entre cuentas en máquinas compartidas.
setQueryClient(queryClient);

// Feature 012: persister de localStorage (o null si el almacenamiento no
// está disponible — modo privado/cuota → degradamos a in-memory).
const queryPersister = createQueryPersister();

/** Wave B — redirect 301: /training/races/:raceEventId/club-insights
 *  → /competitions/:raceEventId?tab=insights
 *  Wave F sustituirá esto por GonePage (410). */
function ClubInsightsRedirect() {
  const { raceEventId } = useParams<{ raceEventId: string }>();
  return (
    <Navigate to={`/competitions/${raceEventId}?tab=insights`} replace />
  );
}

function RootRedirect() {
  const user = useAuthStore((s) => s.user);
  return <Navigate to={landingPathForRole(user?.role)} replace />;
}

export default function App() {
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const persistOptions = useMemo(
    () =>
      queryPersister
        ? {
            persister: queryPersister,
            maxAge: PERSIST_MAX_AGE,
            buster: buildBuster(userId),
            dehydrateOptions: { shouldDehydrateQuery },
          }
        : null,
    [userId],
  );

  const content = (
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
          path="/my-athletes/:athleteId/bitacora"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <ParentNewsletterListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-athletes/:athleteId/bitacora/:newsletterId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <ParentNewsletterPage />
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
              <Suspense fallback={<RouteFallback label="Cargando asistente IA..." />}>
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
          path="/training/sessions/:id/activity-match/:activityId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando comparación plan vs. real…" />}>
                <ActivityMatchPage />
              </Suspense>
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
              <AthleteNewsletterStudioPage />
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

        {/* ── Resultados de competencia (parent) ── */}
        <Route
          path="/parents/competitions/:raceEventId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <ParentCompetitionResultsPage />
            </ProtectedRoute>
          }
        />

        {/* ── Wave B (D7): /training/races/:id/club-insights → redirect 301.
              Permanece activo durante la transición (Wave B – Wave F);
              en Wave F se sustituirá por GonePage (410). ── */}
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={<ClubInsightsRedirect />}
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

        {/* ── Tombstone: /competitions/insights (hub eliminado en feature 029).
              Sin esta ruta estática explícita, React Router hace match con
              /competitions/:id (id="insights"), que renderiza el guard de
              "ID de competencia inválido" en vez del 404 documentado en
              contracts/removal-and-redirect-manifest.md. Cero enlaces entrantes
              (confirmado en research.md R1) — solo bookmarks viejos. ── */}
        <Route path="/competitions/insights" element={<NotFoundPage />} />

        {/* ── Competidores sin enlazar — reubicado desde el hub ── */}
        <Route
          path="/competitions/unlinked"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando competidores..." />}>
                <UnlinkedCompetitorsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Panorama de temporada — única vista no duplicada del extinto hub IA
              cross-válida (feature 029). RBAC coach/admin (parent → redirect por
              ProtectedRoute; backend devuelve 403). ── */}
        <Route
          path="/competitions/insights/season/:year"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando panorama de temporada..." />}>
                <SeasonInsightsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Wave B (D7): /coach/race-analysis → redirect 301. El hub IA fue
              eliminado en feature 029 (duplicado con las vistas IA en Competencias
              y en el perfil del deportista); ahora apunta a Competencias.
              Permanece activo durante la transición (Wave B – Wave F);
              en Wave F se sustituirá por GonePage (410). ── */}
        <Route
          path="/coach/race-analysis"
          element={<Navigate to="/competitions" replace />}
        />

        {/* ── Revisión de actividades Strava (feature 025) — coach/admin only ── */}
        <Route
          path="/activities"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando actividades…" />}>
                <ActivityReviewPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Perfil de usuario (todos los roles autenticados) ── */}
        <Route
          path="/perfil"
          element={
            <ProtectedRoute>
              <Suspense fallback={<RouteFallback label="Cargando perfil..." />}>
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
      <Toaster />
      </TooltipProvider>
  );

  if (!persistOptions) {
    return (
      <QueryClientProvider client={queryClient}>{content}</QueryClientProvider>
    );
  }

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={persistOptions}
    >
      {content}
    </PersistQueryClientProvider>
  );
}
