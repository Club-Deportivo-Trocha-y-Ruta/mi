/**
 * StepGeneral AI-seeded marker tests (Feature 006, Task T036).
 *
 * Verifies:
 *   - AI-seeded fields show the "IA" marker when aiSeededFields contains them.
 *   - The marker is not shown for non-seeded fields.
 *   - (Marker clearing on edit is handled by the SessionWizard via dirtyFields;
 *     this test verifies the rendering path by passing/not-passing the field.)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

import { StepGeneral } from "./StepGeneral";
import {
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";

// ---------------------------------------------------------------------------
// Wrapper component to provide RHF context
// ---------------------------------------------------------------------------

function StepGeneralWrapper({
  aiSeededFields,
}: {
  aiSeededFields?: Set<string>;
}) {
  const {
    register,
    control,
    formState: { errors },
  } = useForm<TrainingSessionFormValues>({
    resolver: zodResolver(trainingSessionCreateSchema),
    mode: "onTouched",
    defaultValues: {
      scheduled_date: "2026-12-01",
      scheduled_start_time: "08:00",
      duration_min: 90,
      location: "La Cumbre",
      technical_focus: "Técnica de frenada",
      description: "Sesión de prueba",
      session_kind: "entrenamiento",
      objectives: "Objetivo de prueba",
      route_text: "",
      strava_url: "",
      coach_notes: "",
      convocados_athlete_ids: [],
    },
  });
  return (
    <StepGeneral
      register={register}
      control={control}
      errors={errors}
      aiSeededFields={aiSeededFields}
    />
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("StepGeneral — marcadores IA (T036)", () => {
  it("no muestra marcadores IA cuando aiSeededFields está vacío", () => {
    render(<StepGeneralWrapper aiSeededFields={new Set()} />);
    expect(screen.queryAllByTestId("ai-marker")).toHaveLength(0);
  });

  it("no muestra marcadores IA cuando la prop no se pasa", () => {
    render(<StepGeneralWrapper />);
    expect(screen.queryAllByTestId("ai-marker")).toHaveLength(0);
  });

  it("muestra marcador IA en 'Foco técnico' cuando está en aiSeededFields", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["technical_focus"])} />,
    );
    const markers = screen.getAllByTestId("ai-marker");
    expect(markers.length).toBeGreaterThanOrEqual(1);
    // The label for technical_focus should contain the marker
    const label = screen.getByText(/Foco técnico/i).closest("label");
    expect(label).toBeInTheDocument();
    expect(label?.querySelector("[data-testid='ai-marker']")).toBeInTheDocument();
  });

  it("muestra marcador IA en 'Descripción' cuando está en aiSeededFields", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["description"])} />,
    );
    // The textarea id="description-input" — find its label via htmlFor
    const label = document.querySelector("label[for='description-input']");
    expect(label).toBeInTheDocument();
    expect(label?.querySelector("[data-testid='ai-marker']")).toBeInTheDocument();
  });

  it("muestra marcador IA en 'Lugar' cuando está en aiSeededFields", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["location"])} />,
    );
    const label = document.querySelector("label[for='location-input']");
    expect(label).toBeInTheDocument();
    expect(label?.querySelector("[data-testid='ai-marker']")).toBeInTheDocument();
  });

  it("muestra marcador IA en 'Objetivos' cuando está en aiSeededFields", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["objectives"])} />,
    );
    const label = document.querySelector("label[for='objectives-input']");
    expect(label).toBeInTheDocument();
    expect(label?.querySelector("[data-testid='ai-marker']")).toBeInTheDocument();
  });

  it("muestra múltiples marcadores cuando múltiples campos están sembrados", () => {
    render(
      <StepGeneralWrapper
        aiSeededFields={new Set(["technical_focus", "description", "location", "objectives", "session_kind"])}
      />,
    );
    const markers = screen.getAllByTestId("ai-marker");
    // At least 5 fields have markers (technical_focus, description, location, objectives, session_kind)
    expect(markers.length).toBeGreaterThanOrEqual(5);
  });

  it("solo el campo sembrado tiene marcador cuando un solo campo está en el set", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["technical_focus"])} />,
    );
    // Only technical_focus should have the marker
    const markers = screen.getAllByTestId("ai-marker");
    expect(markers).toHaveLength(1);
  });

  it("el marcador tiene aria-label descriptivo", () => {
    render(
      <StepGeneralWrapper aiSeededFields={new Set(["technical_focus"])} />,
    );
    const marker = screen.getByTestId("ai-marker");
    expect(marker).toHaveAttribute("aria-label", "Sugerido por IA");
  });

  it("simula edición: campo quitado del set ya no muestra marcador", () => {
    // This tests the rendering path: when the parent removes a field from the
    // set (after RHF dirtyFields triggers clearDirtySeeds), the marker disappears.
    const { rerender } = render(
      <StepGeneralWrapper
        aiSeededFields={new Set(["technical_focus", "description"])}
      />,
    );
    expect(screen.getAllByTestId("ai-marker")).toHaveLength(2);

    // Simulate wizard removing technical_focus from the seeded set (after edit)
    rerender(
      <StepGeneralWrapper aiSeededFields={new Set(["description"])} />,
    );
    expect(screen.getAllByTestId("ai-marker")).toHaveLength(1);

    // Simulate all edits done
    rerender(<StepGeneralWrapper aiSeededFields={new Set()} />);
    expect(screen.queryAllByTestId("ai-marker")).toHaveLength(0);
  });

  it("sin violaciones de accesibilidad con marcadores IA", async () => {
    const { container } = render(
      <StepGeneralWrapper
        aiSeededFields={new Set(["technical_focus", "description", "location"])}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad sin marcadores", async () => {
    const { container } = render(<StepGeneralWrapper />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
