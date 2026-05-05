import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/parents", () => ({
  getParentAthletes: vi.fn(),
  getParentInvites: vi.fn(),
}));

import * as parentsApi from "@/api/parents";
import { LinkedParentsCard } from "../LinkedParentsCard";
import type {
  ParentAthleteOut,
  ParentInviteOut,
} from "@/types/parent.types";
import { FamilyRelationship } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderCard(athleteId = 1, defaultExpanded = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <LinkedParentsCard
          athleteId={athleteId}
          defaultExpanded={defaultExpanded}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function makeParent(overrides: Partial<ParentAthleteOut>): ParentAthleteOut {
  return {
    id: 100,
    parent_id: 10,
    athlete_id: 1,
    relationship: FamilyRelationship.padre,
    parent_name: "Carlos García",
    parent_email: "carlos@example.com",
    parent_phone: "+57 300 123 4567",
    athlete_name: "Sebastián",
    ...overrides,
  };
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

describe("LinkedParentsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando hay padres vinculados y no hay invitación pendiente", () => {
    it("debería mostrar el enlace 'Invitar acudiente →'", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [makeParent({})],
        total: 1,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([]);
      renderCard();

      expect(await screen.findByText("Carlos García")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /invitar acudiente/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/Invitación pendiente/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando existe una invitación pendiente para el atleta", () => {
    it("debería mostrar el hint 'Invitación pendiente · enviada a <email>' y ocultar el enlace", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [makeParent({})],
        total: 1,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({ email: "nuevo@example.com" }),
      ]);
      renderCard();

      expect(await screen.findByText(/Invitación pendiente/i)).toBeInTheDocument();
      expect(screen.getByText("nuevo@example.com")).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: /invitar acudiente/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando una invitación está consumida (used=true)", () => {
    it("debería tratarla como NO pendiente y mostrar el enlace", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [makeParent({})],
        total: 1,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({ used: true, email: "registrado@example.com" }),
      ]);
      renderCard();

      expect(await screen.findByText("Carlos García")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /invitar acudiente/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/Invitación pendiente/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando una invitación está vencida", () => {
    it("debería tratarla como NO pendiente y mostrar el enlace", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [makeParent({})],
        total: 1,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({ expires_at: "2020-01-01T00:00:00Z" }),
      ]);
      renderCard();

      expect(await screen.findByText("Carlos García")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /invitar acudiente/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/Invitación pendiente/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando hay 3 padres vinculados", () => {
    it("no debería mostrar enlace ni hint, aunque haya invitación pendiente", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [
          makeParent({ id: 1, parent_id: 1, parent_name: "Padre 1" }),
          makeParent({ id: 2, parent_id: 2, parent_name: "Padre 2" }),
          makeParent({ id: 3, parent_id: 3, parent_name: "Padre 3" }),
        ],
        total: 3,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([
        makeInvite({ email: "extra@example.com" }),
      ]);
      renderCard();

      expect(await screen.findByText("Padre 1")).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: /invitar acudiente/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Invitación pendiente/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("cuando la tarjeta inicia colapsada", () => {
    it("no debería disparar las queries hasta que el usuario la expanda", async () => {
      vi.mocked(parentsApi.getParentAthletes).mockResolvedValue({
        items: [],
        total: 0,
      });
      vi.mocked(parentsApi.getParentInvites).mockResolvedValue([]);
      renderCard(1, false);

      // Sin expandir: ninguna query
      expect(parentsApi.getParentAthletes).not.toHaveBeenCalled();
      expect(parentsApi.getParentInvites).not.toHaveBeenCalled();

      const toggle = screen.getByRole("button", {
        name: /padres \/ acudientes/i,
      });
      await userEvent.click(toggle);

      // Tras expandir: ambas queries se disparan
      expect(parentsApi.getParentAthletes).toHaveBeenCalledTimes(1);
      expect(parentsApi.getParentInvites).toHaveBeenCalledTimes(1);
    });
  });
});
