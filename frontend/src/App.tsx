import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProtectedRoute } from "@/routes/ProtectedRoute";
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
import { PrivacyPage } from "@/routes/PrivacyPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { SessionsListPage } from "@/routes/training/SessionsListPage";
import { SessionFormPage } from "@/routes/training/SessionFormPage";
import { SessionDetailPage } from "@/routes/training/SessionDetailPage";
import { ReportsListPage } from "@/routes/training/ReportsListPage";
import { ReportDetailPage } from "@/routes/training/ReportDetailPage";
import { ParentSessionsPage } from "@/routes/parents/training/ParentSessionsPage";
import { ParentSessionDetailPage } from "@/routes/parents/training/ParentSessionDetailPage";
import { ParentMonthlyOverviewPage } from "@/routes/parents/training/ParentMonthlyOverviewPage";
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

function RootRedirect() {
  const user = useAuthStore((s) => s.user);
  const to = user?.role === UserRole.parent ? "/my-athletes" : "/dashboard";
  return <Navigate to={to} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
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
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/privacidad" element={<PrivacyPage />} />
        <Route
          path="/registro-padre"
          element={<Navigate to="/onboarding" replace />}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </QueryClientProvider>
  );
}
