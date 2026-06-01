import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
