import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/parents", () => ({
  getParentInvites: vi.fn(),
  createParentInvite: vi.fn(),
}));

import * as parentsApi from "@/api/parents";
import { ParentInviteManager } from "../ParentInviteManager";
import type { ParentInviteOut } from "@/types/parent.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderManager(athleteId = 1) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ParentInviteManager athleteId={athleteId} athleteName="Sebastián" />
    </QueryClientProvider>,
  );
}

function makeInvite(overrides: Partial<ParentInviteOut>): ParentInviteOut {
  return {
    id: 1,
    athlete_id: 1,
    email: "padre@example.com",
    expires_at: "2099-12-31T00:00:00Z",
    used: false,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ParentInviteManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando no hay invitaciones previas", () => {
    it("debería mostrar el formulario de envío y la descripción", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([]);
      renderManager();

      expect(
        await screen.findByRole("button", { name: /enviar invitacion/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Invita al padre\/madre\/acudiente/i),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Cuenta activada/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Invitacion activa/i)).not.toBeInTheDocument();
    });
  });

  describe("cuando existe una invitación pendiente", () => {
    it("debería mostrar el panel ámbar con botón Reenviar y ocultar el formulario", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({ id: 10, email: "pending@example.com" }),
      ]);
      renderManager();

      expect(await screen.findByText(/Invitacion activa/i)).toBeInTheDocument();
      // Email aparece en el panel y en el historial — sólo nos importa que
      // esté presente al menos una vez.
      expect(
        screen.getAllByText("pending@example.com").length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.getByRole("button", { name: /reenviar/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /enviar invitacion/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando hay una invitación pendiente y otra más reciente expirada", () => {
    it("debería seguir mostrando el panel pendiente (no la última)", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({
          id: 1,
          email: "vieja-pending@example.com",
          created_at: "2026-01-01T00:00:00Z",
          expires_at: "2099-12-31T00:00:00Z",
          used: false,
        }),
        makeInvite({
          id: 2,
          email: "reciente-expired@example.com",
          created_at: "2026-02-01T00:00:00Z",
          expires_at: "2020-01-01T00:00:00Z",
          used: false,
        }),
      ]);
      renderManager();

      expect(await screen.findByText(/Invitacion activa/i)).toBeInTheDocument();
      expect(
        screen.getAllByText("vieja-pending@example.com").length,
      ).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText(/Cuenta activada/i)).not.toBeInTheDocument();
    });
  });

  describe("cuando la invitación ya fue consumida (used=true)", () => {
    it("debería mostrar el panel verde 'Cuenta activada' sin formulario ni reenviar", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({
          id: 5,
          email: "registrado@example.com",
          used: true,
        }),
      ]);
      renderManager();

      expect(await screen.findByText(/Cuenta activada/i)).toBeInTheDocument();
      expect(
        screen.getAllByText("registrado@example.com").length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.queryByRole("button", { name: /enviar invitacion/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /reenviar/i }),
      ).not.toBeInTheDocument();
      // La descripción inicial también se oculta cuando la cuenta ya fue activada
      expect(
        screen.queryByText(/Invita al padre\/madre\/acudiente/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando coexisten una invitación usada y otra pendiente posterior", () => {
    it("'used' es terminal y gana sobre la pendiente", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({
          id: 1,
          email: "usada@example.com",
          used: true,
          created_at: "2026-01-01T00:00:00Z",
        }),
        makeInvite({
          id: 2,
          email: "nueva-pending@example.com",
          used: false,
          created_at: "2026-02-01T00:00:00Z",
          expires_at: "2099-12-31T00:00:00Z",
        }),
      ]);
      renderManager();

      expect(await screen.findByText(/Cuenta activada/i)).toBeInTheDocument();
      expect(
        screen.getAllByText("usada@example.com").length,
      ).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText(/Cuenta activada/i)).toBeInTheDocument();
      expect(screen.queryByText(/Invitacion activa/i)).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /enviar invitacion/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando solo hay invitaciones expiradas", () => {
    it("debería mostrar el formulario para crear una nueva", async () => {
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({
          id: 1,
          email: "vencida@example.com",
          used: false,
          expires_at: "2020-01-01T00:00:00Z",
        }),
      ]);
      renderManager();

      expect(
        await screen.findByRole("button", { name: /enviar invitacion/i }),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Invitacion activa/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Cuenta activada/i)).not.toBeInTheDocument();
    });
  });
});
