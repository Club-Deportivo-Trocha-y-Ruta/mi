import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ParentSessionCard } from "./ParentSessionCard";
import type { TrainingSession } from "@/types/trainingSession.types";

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 2,
    status: "planned",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Frenada controlada",
    description: "Sesión de técnica básica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function renderCard(session: TrainingSession, kidAttendanceStatus = undefined) {
  return render(
    <MemoryRouter>
      <ParentSessionCard session={session} kidAttendanceStatus={kidAttendanceStatus} />
    </MemoryRouter>,
  );
}

describe("ParentSessionCard", () => {
  it("muestra el foco técnico", () => {
    renderCard(makeSession());
    expect(screen.getByText("Frenada controlada")).toBeInTheDocument();
  });

  it("muestra la fecha formateada", () => {
    renderCard(makeSession());
    // Intl.DateTimeFormat es-CO: "dom. 10 may." or similar short form
    expect(screen.getByText(/10/)).toBeInTheDocument();
  });

  it("muestra el estado de sesión", () => {
    renderCard(makeSession());
    expect(screen.getByText("Planificada")).toBeInTheDocument();
  });

  it("muestra el estado de asistencia del atleta si se provee", () => {
    renderCard(makeSession(), "presente" as any);
    expect(screen.getByText("Presente")).toBeInTheDocument();
  });

  it("no muestra badge de asistencia si no se provee", () => {
    renderCard(makeSession());
    expect(screen.queryByText("Presente")).not.toBeInTheDocument();
    expect(screen.queryByText("Ausente")).not.toBeInTheDocument();
  });

  it("el link apunta a la ruta correcta", () => {
    const { container } = renderCard(makeSession());
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/parents/training/sessions/1");
  });
});
