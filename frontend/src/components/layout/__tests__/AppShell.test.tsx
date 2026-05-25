import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "../AppShell";
import { UserRole } from "@/types/enums";

// Mock useMyAthletes para no disparar fetch real en tests del AppShell
// (Wave 4 introdujo AthleteSwitcher que consume useMyAthletes para parent).
vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(() => ({
    data: [],
    isLoading: false,
    isError: false,
  })),
}));

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockStoreWithRole(role: UserRole | "admin") {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({
      user: {
        id: 1,
        email: "test@example.com",
        first_name: "Test",
        last_name: "User",
        role,
        is_active: true,
        can_login: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshSession: vi.fn(),
      fetchMe: vi.fn(),
    } as any),
  );
}

function renderShell(role: UserRole | "admin") {
  mockStoreWithRole(role as UserRole);
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AppShell>
          <div>Contenido</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AppShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Rol: coach
  // -------------------------------------------------------------------------
  describe("cuando el rol es coach", () => {
    it("debería mostrar el NavLink 'Atletas'", () => {
      renderShell(UserRole.coach);
      expect(screen.getByRole("link", { name: "Atletas" })).toBeInTheDocument();
    });

    it("debería mostrar el NavLink 'Padres'", () => {
      renderShell(UserRole.coach);
      expect(screen.getByRole("link", { name: "Padres" })).toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.coach);
      expect(
        screen.queryByRole("link", { name: "Mis Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("debería mostrar el NavLink 'Boletines Mensuales'", () => {
      renderShell(UserRole.coach);
      expect(screen.getByRole("link", { name: "Boletines Mensuales" })).toBeInTheDocument();
    });

    it("'Boletines Mensuales' debería apuntar a /training/athlete-newsletters", () => {
      renderShell(UserRole.coach);
      const link = screen.getByRole("link", { name: "Boletines Mensuales" });
      expect(link).toHaveAttribute("href", "/training/athlete-newsletters");
    });
  });

  // -------------------------------------------------------------------------
  // Rol: parent
  // -------------------------------------------------------------------------
  describe("cuando el rol es parent", () => {
    it("debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.parent);
      expect(screen.getByRole("link", { name: "Mis Atletas" })).toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Atletas'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Padres'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Padres" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Boletines Mensuales'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Boletines Mensuales" }),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Rol: admin
  // -------------------------------------------------------------------------
  describe("cuando el rol es admin", () => {
    it("NO debería mostrar el NavLink 'Atletas'", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Padres'", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Padres" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Mis Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("debería mostrar el NavLink 'Salud IA'", () => {
      renderShell(UserRole.admin);
      expect(screen.getByRole("link", { name: "Salud IA" })).toBeInTheDocument();
    });

    it("'Salud IA' debería apuntar a /admin/ai", () => {
      renderShell(UserRole.admin);
      const link = screen.getByRole("link", { name: "Salud IA" });
      expect(link).toHaveAttribute("href", "/admin/ai");
    });

    it("debería mostrar el NavLink 'Boletines Mensuales'", () => {
      renderShell(UserRole.admin);
      expect(screen.getByRole("link", { name: "Boletines Mensuales" })).toBeInTheDocument();
    });
  });
});
