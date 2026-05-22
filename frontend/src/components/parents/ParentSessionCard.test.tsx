import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { ParentSessionCard } from "./ParentSessionCard";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { KidAttendance, TrainingSession } from "@/types/trainingSession.types";

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

function makeAttendance(overrides?: Partial<KidAttendance>): KidAttendance {
  return {
    athlete_id: 10,
    status: "presente",
    ...overrides,
  };
}

interface RenderProps {
  session?: TrainingSession;
  kidAttendance?: KidAttendance | null;
  athleteAgeDecimal?: number | null;
}

function renderCard({ session, kidAttendance, athleteAgeDecimal }: RenderProps = {}) {
  return render(
    <MemoryRouter>
      <TooltipProvider delayDuration={0}>
        <ParentSessionCard
          session={session ?? makeSession()}
          kidAttendance={kidAttendance ?? null}
          athleteAgeDecimal={athleteAgeDecimal ?? null}
        />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe("ParentSessionCard", () => {
  describe("estructura básica", () => {
    it("muestra el foco técnico", () => {
      renderCard();
      expect(screen.getByText("Frenada controlada")).toBeInTheDocument();
    });

    it("muestra la fecha formateada", () => {
      renderCard();
      expect(screen.getByText(/10/)).toBeInTheDocument();
    });

    it("muestra el estado de sesión", () => {
      renderCard();
      expect(screen.getByText("Planificada")).toBeInTheDocument();
    });

    it("expone link al detalle", () => {
      const { container } = renderCard();
      const links = container.querySelectorAll("a");
      expect(Array.from(links).some((l) => l.getAttribute("href") === "/parents/training/sessions/1")).toBe(true);
    });
  });

  describe("badge de asistencia", () => {
    it("muestra el estado si se provee", () => {
      renderCard({ kidAttendance: makeAttendance({ status: "presente" }) });
      expect(screen.getByText("Presente")).toBeInTheDocument();
    });

    it("no muestra badge si no se provee", () => {
      renderCard();
      expect(screen.queryByText("Presente")).not.toBeInTheDocument();
      expect(screen.queryByText("Ausente")).not.toBeInTheDocument();
    });
  });

  describe("sesión planificada (planned)", () => {
    it("no muestra zona inline ni rúbrica ni comentario", () => {
      renderCard({
        kidAttendance: makeAttendance({
          rubric_effort: 4,
          rpe_omni: 6,
          individual_feedback: "Buen trabajo",
        }),
        athleteAgeDecimal: 14,
      });
      expect(screen.queryByTestId("parent-session-inline")).not.toBeInTheDocument();
      expect(screen.queryByTestId("inline-rubric")).not.toBeInTheDocument();
      expect(screen.queryByText(/Buen trabajo/)).not.toBeInTheDocument();
    });
  });

  describe("rúbrica inline (diferenciación por edad)", () => {
    const executed = makeSession({ status: "executed" });
    const fullAttendance = makeAttendance({
      status: "presente",
      rubric_effort: 4,
      rubric_attitude: 5,
      rubric_technique: 3,
      rpe_omni: 7,
    });

    it("oculta la rúbrica numérica para atletas <13 años", () => {
      renderCard({
        session: executed,
        kidAttendance: fullAttendance,
        athleteAgeDecimal: 11.5,
      });
      expect(screen.queryByTestId("inline-rubric")).not.toBeInTheDocument();
    });

    it("oculta la rúbrica si age_decimal es null (fallback conservador)", () => {
      renderCard({
        session: executed,
        kidAttendance: fullAttendance,
        athleteAgeDecimal: null,
      });
      expect(screen.queryByTestId("inline-rubric")).not.toBeInTheDocument();
    });

    it("muestra la rúbrica con etiquetas cualitativas para ≥13", () => {
      renderCard({
        session: executed,
        kidAttendance: fullAttendance,
        athleteAgeDecimal: 14,
      });
      const rubric = screen.getByTestId("inline-rubric");
      expect(within(rubric).getByText(/Esfuerzo: Consolidando/)).toBeInTheDocument();
      expect(within(rubric).getByText(/Actitud: Dominando/)).toBeInTheDocument();
      expect(within(rubric).getByText(/Técnica: Avanzando/)).toBeInTheDocument();
      expect(within(rubric).getByText(/RPE 7\/10/)).toBeInTheDocument();
    });

    it("no muestra rúbrica si todos los valores son null aunque atleta sea ≥13", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ status: "presente" }),
        athleteAgeDecimal: 14,
      });
      expect(screen.queryByTestId("inline-rubric")).not.toBeInTheDocument();
    });
  });

  describe("comentario del entrenador", () => {
    const executed = makeSession({ status: "executed" });

    it("muestra comentario corto completo y sin botón expandir", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: "Excelente actitud hoy." }),
      });
      expect(screen.getByText(/Excelente actitud hoy/)).toBeInTheDocument();
      expect(screen.queryByTestId("comment-expand-button")).not.toBeInTheDocument();
    });

    it("muestra preview y botón expandir si comentario es largo", async () => {
      const long = "a".repeat(200);
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: long }),
      });
      const button = screen.getByTestId("comment-expand-button");
      expect(button).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByTestId("inline-comment-preview")).toBeInTheDocument();

      await userEvent.click(button);
      expect(button).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByTestId("inline-comment-full")).toBeInTheDocument();
    });

    it("no muestra bloque de comentario si está vacío o es solo espacios", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: "   " }),
      });
      expect(screen.queryByText(/Nota del entrenador/)).not.toBeInTheDocument();
    });

    it("muestra disclaimer pedagógico arriba con role=note", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: "Atento a su frenada." }),
      });
      // Wave 5: el copy cambió de "para ti, no para tu atleta" a
      // "para acompañarte como familia" y se movió arriba con role=note.
      const note = screen.getByRole("note", { name: /recomendación pedagógica/i });
      expect(note).toHaveTextContent(/acompañarte como familia/i);
      expect(note).toHaveTextContent(/espera al día siguiente/i);
    });

    it("disclaimer aparece ANTES del cuerpo del comentario en el DOM", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: "Atento a su frenada." }),
      });
      const note = screen.getByRole("note", { name: /recomendación pedagógica/i });
      const comment = screen.getByTestId("inline-comment-preview");
      // compareDocumentPosition: 4 = note precede a comment
      // (https://developer.mozilla.org/docs/Web/API/Node/compareDocumentPosition)
      expect(note.compareDocumentPosition(comment) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("el comentario tiene aria-describedby apuntando al disclaimer", () => {
      renderCard({
        session: executed,
        kidAttendance: makeAttendance({ individual_feedback: "Atento a su frenada." }),
      });
      const comment = screen.getByTestId("inline-comment-preview");
      const describedById = comment.getAttribute("aria-describedby");
      expect(describedById).toBeTruthy();
      const note = screen.getByRole("note", { name: /recomendación pedagógica/i });
      expect(note.id).toBe(describedById);
    });
  });

  describe("motivo de ausencia", () => {
    it("muestra excuse_reason cuando hay motivo", () => {
      renderCard({
        session: makeSession({ status: "executed" }),
        kidAttendance: makeAttendance({
          status: "lesionado",
          excuse_reason: "Tendinitis rodilla izquierda",
        }),
      });
      expect(screen.getByTestId("inline-excuse")).toHaveTextContent("Tendinitis rodilla");
    });
  });
});
