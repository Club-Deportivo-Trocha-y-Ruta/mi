import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LastSessionCard } from "@/components/parents/home/LastSessionCard";
import type { TrainingSession } from "@/types/trainingSession.types";

function mkSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 100,
    club_id: 1,
    created_by_user_id: 2,
    status: "executed",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Pedaleo de pie",
    description: "—",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-10T10:00:00Z",
    executed_at: "2026-05-10T10:00:00Z",
    kid_attendances: [
      { athlete_id: 7, status: "presente" },
    ],
    ...overrides,
  };
}

function renderCard(props: Parameters<typeof LastSessionCard>[0]) {
  return render(
    <MemoryRouter>
      <LastSessionCard {...props} />
    </MemoryRouter>,
  );
}

describe("LastSessionCard", () => {
  it("muestra skeleton accesible cuando isLoading", () => {
    renderCard({ session: null, isLoading: true, athleteId: 7 });
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "Cargando última sesión");
  });

  it("muestra empty state cuando no hay sesión", () => {
    renderCard({ session: null, isLoading: false, athleteId: 7 });
    expect(screen.getByTestId("last-empty")).toBeInTheDocument();
  });

  it("muestra el foco técnico y badge de asistencia 'presente'", () => {
    renderCard({ session: mkSession(), isLoading: false, athleteId: 7 });
    expect(screen.getByText("Pedaleo de pie")).toBeInTheDocument();
    // Badge attendance
    expect(screen.getByLabelText("Asistencia: Presente")).toBeInTheDocument();
  });

  it("usa lead copy celebratorio cuando atleta estuvo presente", () => {
    renderCard({
      session: mkSession(),
      isLoading: false,
      athleteId: 7,
      athleteName: "Santiago",
    });
    expect(
      screen.getByText(/Santiago estuvo en el último entrenamiento/i),
    ).toBeInTheDocument();
  });

  it("usa lead copy neutro cuando atleta estuvo justificado", () => {
    renderCard({
      session: mkSession({
        kid_attendances: [{ athlete_id: 7, status: "justificado" }],
      }),
      isLoading: false,
      athleteId: 7,
      athleteName: "Santiago",
    });
    expect(screen.getByText(/no asistió \(con justificación\)/i)).toBeInTheDocument();
  });

  it("link apunta a /parents/training/sessions/:id", () => {
    renderCard({
      session: mkSession({ id: 55 }),
      isLoading: false,
      athleteId: 7,
    });
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/parents/training/sessions/55");
  });

  it("muestra mensaje de error cuando isError=true", () => {
    renderCard({ session: null, isLoading: false, isError: true, athleteId: 7 });
    expect(screen.getByText(/No fue posible cargar/i)).toBeInTheDocument();
  });
});
