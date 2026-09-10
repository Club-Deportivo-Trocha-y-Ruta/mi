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
import { render, screen, within } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

// Feature 041 (T066) — StepGeneral ahora renderiza SessionCoachesField, que
// usa TanStack Query (useClubCoaches → GET /api/users). Se fija una
// respuesta estable para no depender de MSW en este archivo (idioma de test
// ya establecido aquí: mock plano de `@/api/client`).
vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      data: {
        items: [
          { id: 7, first_name: "Laura", last_name: "Méndez", is_active: true, role: "coach" },
          { id: 8, first_name: "Ana", last_name: "Rivera", is_active: true, role: "coach" },
        ],
        total: 2,
      },
    }),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

// Entrenador autenticado fijo (id 7) — coincide con `coach_user_ids: [7]` en
// los defaultValues de abajo, así SessionCoachesField no dispara su efecto
// de prellenado automático y el resto de estos tests (marcadores IA) no se
// ve afectado por una carga asíncrona adicional. `accessToken` es
// obligatorio en el mock: `useClubCoaches` solo dispara la query cuando
// existe (`enabled: !!accessToken`), igual que el resto de hooks de
// TanStack Query del proyecto.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: {
      user: { id: number; first_name: string; last_name: string };
      accessToken: string;
    }) => unknown,
  ) =>
    selector({
      user: { id: 7, first_name: "Laura", last_name: "Méndez" },
      accessToken: "test-token",
    }),
}));

import { StepGeneral } from "./StepGeneral";
import {
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";

// ---------------------------------------------------------------------------
// Wrapper component to provide RHF + TanStack Query context
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
      coach_user_ids: [7],
    },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <StepGeneral
        register={register}
        control={control}
        errors={errors}
        aiSeededFields={aiSeededFields}
      />
    </QueryClientProvider>
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
        aiSeededFields={new Set(["technical_focus", "description", "location", "objectives"])}
      />,
    );
    const markers = screen.getAllByTestId("ai-marker");
    // At least 4 fields have markers (technical_focus, description, location, objectives)
    expect(markers.length).toBeGreaterThanOrEqual(4);
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

// ---------------------------------------------------------------------------
// SessionCoachesField wiring (feature 041, T066)
// ---------------------------------------------------------------------------

describe("StepGeneral — campo de entrenadores a cargo (T066)", () => {
  it("renderiza SessionCoachesField con el entrenador autenticado preseleccionado", async () => {
    render(<StepGeneralWrapper />);
    expect(await screen.findByText("Laura Méndez")).toBeInTheDocument();
    expect(screen.getByText("Entrenadores a cargo")).toBeInTheDocument();
  });

  it("permite agregar a otro entrenador del club desde el paso General", async () => {
    render(<StepGeneralWrapper />);
    const checkbox = await screen.findByRole("checkbox", { name: /Agregar a Ana Rivera/i });
    checkbox.click();
    const chipList = await screen.findByTestId("selected-coach-chips");
    expect(within(chipList).getByText("Ana Rivera")).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad con el campo de entrenadores cargado", async () => {
    const { container } = render(<StepGeneralWrapper />);
    await screen.findByText("Laura Méndez");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
