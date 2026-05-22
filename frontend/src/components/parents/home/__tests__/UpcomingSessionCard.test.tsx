import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { UpcomingSessionCard } from "@/components/parents/home/UpcomingSessionCard";
import type { TrainingSession } from "@/types/trainingSession.types";

function mkSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 100,
    club_id: 1,
    created_by_user_id: 2,
    status: "planned",
    scheduled_date: "2030-12-31",
    scheduled_start_time: "16:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Frenada controlada",
    description: "—",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderCard(props: Parameters<typeof UpcomingSessionCard>[0]) {
  return render(
    <MemoryRouter>
      <UpcomingSessionCard {...props} />
    </MemoryRouter>,
  );
}

describe("UpcomingSessionCard", () => {
  it("muestra skeleton accesible cuando isLoading", () => {
    renderCard({ session: null, isLoading: true });
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "Cargando próximo entrenamiento");
  });

  it("muestra empty state cuando no hay sesión y no carga", () => {
    renderCard({ session: null, isLoading: false });
    expect(screen.getByTestId("upcoming-empty")).toBeInTheDocument();
    expect(screen.getByText(/No hay entrenamientos programados/i)).toBeInTheDocument();
  });

  it("muestra el foco técnico y el lugar cuando hay sesión", () => {
    renderCard({ session: mkSession(), isLoading: false });
    expect(screen.getByText("Frenada controlada")).toBeInTheDocument();
    expect(screen.getByText("Parque del Café")).toBeInTheDocument();
  });

  it("link apunta a /parents/training/sessions/:id", () => {
    renderCard({ session: mkSession({ id: 42 }), isLoading: false });
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/parents/training/sessions/42");
  });

  it("incluye el nombre del atleta en aria-label cuando se provee", () => {
    renderCard({
      session: mkSession({ id: 42 }),
      isLoading: false,
      athleteName: "Santiago",
    });
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toMatch(/Santiago/);
  });

  it("muestra mensaje de error cuando isError=true", () => {
    renderCard({ session: null, isLoading: false, isError: true });
    expect(screen.getByText(/No fue posible cargar/i)).toBeInTheDocument();
  });
});
