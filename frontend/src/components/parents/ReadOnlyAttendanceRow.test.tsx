import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ReadOnlyAttendanceRow } from "./ReadOnlyAttendanceRow";
import type { Attendance } from "@/types/trainingSession.types";

function makeAttendance(overrides?: Partial<Attendance>): Attendance {
  return {
    id: 1,
    session_id: 10,
    athlete_id: 42,
    athlete_name: "Sofía López",
    status: "presente",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    rpe_omni: 7,
    rubric_effort: 4,
    rubric_attitude: 5,
    rubric_technique: 3,
    individual_feedback: "Buen trabajo hoy",
    ...overrides,
  };
}

describe("ReadOnlyAttendanceRow", () => {
  it("muestra el nombre y estado del atleta", () => {
    render(<ReadOnlyAttendanceRow attendance={makeAttendance()} />);
    expect(screen.getByText("Sofía López")).toBeInTheDocument();
    expect(screen.getByText("Presente")).toBeInTheDocument();
  });

  it("muestra la rúbrica cuando hay datos", () => {
    render(<ReadOnlyAttendanceRow attendance={makeAttendance()} />);
    expect(screen.getByText("7/10")).toBeInTheDocument();
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("5/5")).toBeInTheDocument();
    expect(screen.getByText("3/5")).toBeInTheDocument();
  });

  it("muestra el comentario cuando existe", () => {
    render(<ReadOnlyAttendanceRow attendance={makeAttendance()} />);
    expect(screen.getByText("Buen trabajo hoy")).toBeInTheDocument();
  });

  it("muestra 'Sin comentario aún' cuando no hay feedback", () => {
    render(
      <ReadOnlyAttendanceRow
        attendance={makeAttendance({ individual_feedback: null })}
      />,
    );
    expect(screen.getByText("Sin comentario aún.")).toBeInTheDocument();
  });

  it("muestra 'Sin evaluación' cuando no hay rúbrica", () => {
    render(
      <ReadOnlyAttendanceRow
        attendance={makeAttendance({
          status: "ausente",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
        })}
      />,
    );
    expect(
      screen.getByText(/Aún no se ha registrado evaluación/i),
    ).toBeInTheDocument();
  });

  it("muestra la razón de ausencia cuando existe", () => {
    render(
      <ReadOnlyAttendanceRow
        attendance={makeAttendance({
          status: "ausente",
          excuse_reason: "Enfermedad",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
        })}
      />,
    );
    expect(screen.getByText("Enfermedad")).toBeInTheDocument();
  });

  it("expone data-athlete-id para uso en tests de privacidad", () => {
    const { container } = render(<ReadOnlyAttendanceRow attendance={makeAttendance()} />);
    const row = container.querySelector("[data-athlete-id='42']");
    expect(row).toBeInTheDocument();
  });

  it("no tiene inputs editables", () => {
    const { container } = render(<ReadOnlyAttendanceRow attendance={makeAttendance()} />);
    expect(container.querySelectorAll("input")).toHaveLength(0);
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("select")).toHaveLength(0);
  });
});
