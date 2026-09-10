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
import { LoginPage } from "@/routes/auth/LoginPage";
import { OnboardingPage } from "@/routes/auth/OnboardingPage";
import { ForgotPasswordPage } from "@/routes/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "@/routes/auth/ResetPasswordPage";
import { PrivacyPage } from "@/routes/PrivacyPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { UserRole } from "@/types/enums";

// Dashboard (coach/admin) — lazy: evita cargarlo para padres.
const DashboardPage = lazy(() =>
  import("@/routes/dashboard/DashboardPage").then((m) => ({
    default: m.DashboardPage,
  })),
);

// Deportistas (coach) — lazy.
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

// Padres (coach) — lazy.
const ParentsListPage = lazy(() =>
  import("@/routes/parents/ParentsListPage").then((m) => ({
    default: m.ParentsListPage,
  })),
);
const ParentDetailPage = lazy(() =>
  import("@/routes/parents/ParentDetailPage").then((m) => ({
    default: m.ParentDetailPage,
  })),
);

// Padre (rol parent) — lazy.
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
const ParentNewsletterListPage = lazy(() =>
  import("@/routes/parents/newsletters/ParentNewsletterListPage").then(
    (m) => ({ default: m.ParentNewsletterListPage }),
  ),
);
const ParentNewsletterPage = lazy(() =>
  import("@/routes/parents/newsletters/ParentNewsletterPage").then((m) => ({
    default: m.ParentNewsletterPage,
  })),
);

// Admin — lazy.
const AIHealthPage = lazy(() =>
  import("@/routes/admin/AIHealthPage").then((m) => ({
    default: m.AIHealthPage,
  })),
);
const ArchivedAthletesPage = lazy(() =>
  import("@/routes/admin/ArchivedAthletesPage").then((m) => ({
    default: m.ArchivedAthletesPage,
  })),
);
const StaffPage = lazy(() =>
  import("@/routes/admin/StaffPage").then((m) => ({
    default: m.StaffPage,
  })),
);
const ClubHistoryPage = lazy(() =>
  import("@/routes/admin/ClubHistoryPage").then((m) => ({
    default: m.ClubHistoryPage,
  })),
);

// Entrenamiento (coach/admin) — lazy.
const SessionsListPage = lazy(() =>
  import("@/routes/training/SessionsListPage").then((m) => ({
    default: m.SessionsListPage,
  })),
);
const SessionFormPage = lazy(() =>
  import("@/routes/training/SessionFormPage").then((m) => ({
    default: m.SessionFormPage,
  })),
);
const SessionDetailPage = lazy(() =>
  import("@/routes/training/SessionDetailPage").then((m) => ({
    default: m.SessionDetailPage,
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
const ProjectProfilePage = lazy(() =>
  import("@/routes/training/ProjectProfilePage").then((m) => ({
    default: m.ProjectProfilePage,
  })),
);
const AthleteNewslettersDashboardPage = lazy(() =>
  import("@/routes/training/AthleteNewslettersDashboardPage").then((m) => ({
    default: m.AthleteNewslettersDashboardPage,
  })),
);
const AthleteNewsletterStudioPage = lazy(() =>
  import("@/routes/training/AthleteNewsletterStudioPage").then((m) => ({
    default: m.AthleteNewsletterStudioPage,
  })),
);

// Entrenamiento (rol parent) — lazy.
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

// Calendario (coach/admin) — lazy: saca los 6 paquetes @fullcalendar/* del
// chunk de entrada (nadie debería pagar ese peso sin abrir el calendario).
const CalendarPage = lazy(() =>
  import("@/routes/calendar/CalendarPage").then((m) => ({
    default: m.CalendarPage,
  })),
);
const EventFormPage = lazy(() =>
  import("@/routes/calendar/EventFormPage").then((m) => ({
    default: m.EventFormPage,
  })),
);

// Calendario (rol parent) — lazy.
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

// Resultados de competencia (rol parent) — lazy.
const ParentCompetitionResultsPage = lazy(() =>
  import("@/routes/parents/competitions/ParentCompetitionResultsPage").then(
    (m) => ({ default: m.ParentCompetitionResultsPage }),
  ),
);

// Competencias (coach/admin) — lazy.
const CompetitionsListPage = lazy(() =>
  import("@/routes/competitions/CompetitionsListPage").then((m) => ({
    default: m.CompetitionsListPage,
  })),
);
const CompetitionFormPage = lazy(() =>
  import("@/routes/competitions/CompetitionFormPage").then((m) => ({
    default: m.CompetitionFormPage,
  })),
);
const CompetitionDetailPage = lazy(() =>
  import("@/routes/competitions/CompetitionDetailPage").then((m) => ({
    default: m.CompetitionDetailPage,
  })),
);
const CompetitionImportPage = lazy(() =>
  import("@/routes/competitions/CompetitionImportPage").then((m) => ({
    default: m.CompetitionImportPage,
  })),
);

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
              <Suspense fallback={<RouteFallback label="Cargando panel..." />}>
                <DashboardPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/athletes"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando deportistas..." />}>
                <AthletesListPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/athletes/new"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de deportista..." />}>
                <AthleteFormPage mode="create" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/athletes/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando deportista..." />}>
                <AthleteDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/athletes/:id/edit"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de deportista..." />}>
                <AthleteFormPage mode="edit" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando padres..." />}>
                <ParentsListPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando padre..." />}>
                <ParentDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-athletes"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando mis deportistas..." />}>
                <ParentDashboardPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-athletes/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando deportista..." />}>
                <MyAthleteDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-athletes/:athleteId/bitacora"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando bitácoras..." />}>
                <ParentNewsletterListPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-athletes/:athleteId/bitacora/:newsletterId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando bitácora..." />}>
                <ParentNewsletterPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/ai"
          element={
            <ProtectedRoute allowedRoles={[UserRole.admin, UserRole.coach]}>
              <Suspense fallback={<RouteFallback label="Cargando estado de IA..." />}>
                <AIHealthPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/atletas-archivados"
          element={
            <ProtectedRoute allowedRoles={[UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando atletas archivados..." />}>
                <ArchivedAthletesPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/usuarios"
          element={
            <ProtectedRoute allowedRoles={[UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando personal..." />}>
                <StaffPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/club/historial"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando historial del club..." />}>
                <ClubHistoryPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/sessions"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando sesiones..." />}>
                <SessionsListPage />
              </Suspense>
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
              <Suspense fallback={<RouteFallback label="Cargando formulario de sesión..." />}>
                <SessionFormPage mode="create" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/sessions/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando sesión..." />}>
                <SessionDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/sessions/:id/edit"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de sesión..." />}>
                <SessionFormPage mode="edit" />
              </Suspense>
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
              <Suspense fallback={<RouteFallback label="Cargando informes..." />}>
                <ReportsListPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/reports/project-profile"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando perfil de proyección..." />}>
                <ProjectProfilePage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/reports/:year/:month"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando informe..." />}>
                <ReportDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/athlete-newsletters"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando bitácoras..." />}>
                <AthleteNewslettersDashboardPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/training/athlete-newsletters/:athleteId/:newsletterId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando editor de bitácora..." />}>
                <AthleteNewsletterStudioPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents/training/sessions"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando sesiones..." />}>
                <ParentSessionsPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents/training/sessions/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando sesión..." />}>
                <ParentSessionDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents/training/overview"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando resumen mensual..." />}>
                <ParentMonthlyOverviewPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        {/* ── Calendar routes (coach/admin) ── */}
        <Route
          path="/calendar"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando calendario..." />}>
                <CalendarPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/calendar/events/new"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de evento..." />}>
                <EventFormPage mode="create" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/calendar/events/:id/edit"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de evento..." />}>
                <EventFormPage mode="edit" />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Calendar routes (parent) ── */}
        <Route
          path="/parents/calendar"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando calendario..." />}>
                <ParentCalendarPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/parents/calendar/events/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando evento..." />}>
                <ParentEventDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />

        {/* ── Resultados de competencia (parent) ── */}
        <Route
          path="/parents/competitions/:raceEventId"
          element={
            <ProtectedRoute allowedRoles={[UserRole.parent]}>
              <Suspense fallback={<RouteFallback label="Cargando resultados..." />}>
                <ParentCompetitionResultsPage />
              </Suspense>
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
              <Suspense fallback={<RouteFallback label="Cargando competencias..." />}>
                <CompetitionsListPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/new"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de competencia..." />}>
                <CompetitionFormPage mode="create" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/import"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando importación..." />}>
                <CompetitionImportPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando competencia..." />}>
                <CompetitionDetailPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id/edit"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando formulario de competencia..." />}>
                <CompetitionFormPage mode="edit" />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions/:id/import"
          element={
            <ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>
              <Suspense fallback={<RouteFallback label="Cargando importación..." />}>
                <CompetitionImportPage />
              </Suspense>
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
