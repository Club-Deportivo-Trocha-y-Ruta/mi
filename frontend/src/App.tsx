import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { useAuthStore } from "@/store/auth.store";
import { LoginPage } from "@/routes/auth/LoginPage";
import { DashboardPage } from "@/routes/dashboard/DashboardPage";
import { AthletesListPage } from "@/routes/athletes/AthletesListPage";
import { AthleteDetailPage } from "@/routes/athletes/AthleteDetailPage";
import { AthleteFormPage } from "@/routes/athletes/AthleteFormPage";
import { ParentsListPage } from "@/routes/parents/ParentsListPage";
import { ParentDetailPage } from "@/routes/parents/ParentDetailPage";
import { ParentDashboardPage } from "@/routes/parents/ParentDashboardPage";
import { MyAthleteDetailPage } from "@/routes/parents/MyAthleteDetailPage";
import { ParentRegisterPage } from "@/routes/auth/ParentRegisterPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { UserRole } from "@/types/enums";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
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
        <Route path="/registro-padre" element={<ParentRegisterPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </QueryClientProvider>
  );
}
