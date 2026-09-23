import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/api/auth", () => ({
  login: vi.fn(),
  refreshToken: vi.fn(),
  getMe: vi.fn(),
}));

import { LoginPage } from "../LoginPage";
import { useAuthStore } from "@/store/auth.store";
import type { MeResponse } from "@/types/auth.types";
import { UserRole } from "@/types/enums";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
        <Route path="/my-athletes" element={<div>My athletes page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/**
 * Simula llegar a /login vía el redirect de `ProtectedRoute`
 * (`state={{ from: location.pathname }}`) — mismo `state` que produce un
 * deep link de email de insight de carrera sin sesión activa.
 */
function renderLoginWithFrom(from: string) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
        <Route path="/my-athletes" element={<div>My athletes page</div>} />
        <Route
          path="/athletes/:athleteId/race-analysis/insights/:insightId"
          element={<div>Deep link destino</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function setSession(role: UserRole) {
  const user = { id: 1, email: "u@trochyruta.com", role } as MeResponse;
  useAuthStore.setState({
    accessToken: "tok",
    refreshToken: "ref",
    user,
    isAuthenticated: true,
    isLoading: false,
  });
}

describe("LoginPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("muestra el formulario cuando no hay sesión válida", () => {
    renderLogin();
    expect(screen.getByLabelText("Correo")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toBeInTheDocument();
  });

  it("redirige al Dashboard cuando un coach ya tiene sesión válida", () => {
    setSession(UserRole.coach);
    renderLogin();
    expect(screen.getByText("Dashboard page")).toBeInTheDocument();
    expect(screen.queryByLabelText("Correo")).not.toBeInTheDocument();
  });

  it("redirige a 'Mis atletas' cuando un padre ya tiene sesión válida", () => {
    setSession(UserRole.parent);
    renderLogin();
    expect(screen.getByText("My athletes page")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------
  // 2026-09-23: deep link de email de insight de carrera sin sesión —
  // ProtectedRoute manda a /login con state.from; el login debe volver
  // ahí (no al landing genérico del rol) una vez autenticado.
  // -------------------------------------------------------------------
  it("con sesión ya válida y state.from, redirige al deep link en vez del landing del rol", () => {
    setSession(UserRole.coach);
    renderLoginWithFrom("/athletes/42/race-analysis/insights/7");
    expect(screen.getByText("Deep link destino")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard page")).not.toBeInTheDocument();
  });

  it("tras un login exitoso con state.from, navega al deep link en vez del landing del rol", async () => {
    // Mockeamos la acción `login` del store directamente (mismo dato que
    // `setSession` deja al terminar) en vez de la API completa — evita
    // depender de fetchMe/prefetchLandingData, que no son lo que este test
    // cubre (el redirect post-login hacia `state.from`).
    useAuthStore.setState({
      login: vi.fn(async () => {
        useAuthStore.setState({
          accessToken: "tok",
          refreshToken: "ref",
          user: { id: 1, email: "u@trochyruta.com", role: UserRole.parent } as MeResponse,
          isAuthenticated: true,
        });
      }),
    });
    const user = userEvent.setup();

    renderLoginWithFrom("/athletes/42/race-analysis/insights/7");
    await user.type(screen.getByLabelText("Correo"), "u@trochyruta.com");
    await user.type(screen.getByLabelText("Contraseña"), "password123");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    expect(await screen.findByText("Deep link destino")).toBeInTheDocument();
  });
});
