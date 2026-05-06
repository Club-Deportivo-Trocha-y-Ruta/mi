import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { AnthropometryForm } from "./AnthropometryForm";
import { Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { MaturationStatus } from "@/types/enums";

// ---------------------------------------------------------------------------
// Mocks — deben ir antes de importar el componente
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  createAnthropometry: vi.fn(),
  getAnthropometry: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {},
  registerAuthHandlers: vi.fn(),
}));

import * as athletesApi from "@/api/athletes";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockRecord: AnthropometricRecord = {
  id: 1,
  athlete_id: 1,
  evaluation_date: "2026-01-15",
  weight_kg: 45.0,
  standing_height_cm: 155.0,
  arm_span_cm: null,
  sitting_height_cm: 73.0,
  leg_length_cm: 82.0,
  leg_sitting_ratio: 1.1233,
  maturity_offset: -0.5,
  age_at_phv: 13.5,
  maturation_status: MaturationStatus.CircaPHV,
  training_implications: "Enfoca en habilidades técnicas.",
  evaluated_by: 1,
  created_at: "2026-01-15T00:00:00Z",
  notes: null,
};

const defaultProps = {
  athleteId: 1,
  athleteSex: Sex.M,
  athleteBirthDate: "2013-06-15",
  onSuccess: vi.fn(),
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function renderForm(props = defaultProps) {
  const wrapper = createWrapper();
  return render(
    createElement(wrapper, null, createElement(AnthropometryForm, props)),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AnthropometryForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onSuccess.mockReset?.();
  });

  // -------------------------------------------------------------------------
  // Renderizado inicial
  // -------------------------------------------------------------------------
  describe("renderizado inicial", () => {
    it("debería mostrar el campo 'Fecha de evaluacion'", () => {
      renderForm();
      expect(screen.getByText(/Fecha de evaluación/i)).toBeInTheDocument();
    });

    it("debería mostrar el campo 'Peso (kg)'", () => {
      renderForm();
      expect(screen.getByText(/Peso \(kg\)/i)).toBeInTheDocument();
    });

    it("debería mostrar el campo 'Talla de pie (cm)'", () => {
      renderForm();
      expect(screen.getByText(/Talla de pie/i)).toBeInTheDocument();
    });

    it("debería mostrar el campo 'Envergadura (cm)'", () => {
      renderForm();
      expect(screen.getByText(/Envergadura/i)).toBeInTheDocument();
    });

    it("debería mostrar el campo 'Talla sentado (cm)'", () => {
      renderForm();
      expect(screen.getByText(/Talla sentado/i)).toBeInTheDocument();
    });

    it("debería mostrar el botón 'Guardar medicion'", () => {
      renderForm();
      expect(
        screen.getByRole("button", { name: /Guardar medición/i }),
      ).toBeInTheDocument();
    });

    it("debería mostrar el panel 'Calculo PHV (en tiempo real)'", () => {
      renderForm();
      expect(screen.getByText(/Cálculo PHV/i)).toBeInTheDocument();
    });

    it("debería mostrar el mensaje de placeholder del PHV cuando faltan datos", () => {
      renderForm();
      expect(
        screen.getByText(/Completa los campos para ver el cálculo/i),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Estado isPending del botón
  // -------------------------------------------------------------------------
  describe("estado de envío", () => {
    it("el botón debería estar habilitado inicialmente", () => {
      renderForm();
      const btn = screen.getByRole("button", { name: /Guardar medición/i });
      expect(btn).not.toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Validación de campos numéricos
  // -------------------------------------------------------------------------
  describe("validación de campos numéricos", () => {
    it("debería mostrar error si peso es menor a 20 kg", async () => {
      renderForm();
      const inputs = document.querySelectorAll("input[type='number']");
      // índice 0 = peso
      const weightInput = inputs[0] as HTMLInputElement;
      fireEvent.change(weightInput, { target: { valueAsNumber: 10 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(screen.getByText(/Min 20 kg/i)).toBeInTheDocument();
      });
    });

    it("debería mostrar error si talla de pie es menor a 100 cm", async () => {
      renderForm();
      const inputs = document.querySelectorAll("input[type='number']");
      // índice 1 = standing_height
      const heightInput = inputs[1] as HTMLInputElement;
      fireEvent.change(heightInput, { target: { valueAsNumber: 50 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(screen.getByText(/Min 100 cm/i)).toBeInTheDocument();
      });
    });

    it("debería mostrar error si talla sentado es menor a 50 cm", async () => {
      renderForm();
      const inputs = document.querySelectorAll("input[type='number']");
      // índice 3 = sitting_height
      const sittingInput = inputs[3] as HTMLInputElement;
      fireEvent.change(sittingInput, { target: { valueAsNumber: 30 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(screen.getByText(/Min 50 cm/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Panel PHV en tiempo real
  // -------------------------------------------------------------------------
  describe("panel PHV en tiempo real", () => {
    it("debería calcular y mostrar el PHV cuando todos los campos están completos", async () => {
      renderForm();

      // Rellenar fecha
      const dateInput = document.querySelector(
        "input[type='date']",
      ) as HTMLInputElement;
      fireEvent.change(dateInput, { target: { value: "2026-01-15" } });

      // Rellenar campos numéricos: peso (0), standing (1), arm_span (2), sitting (3)
      const numInputs = document.querySelectorAll("input[type='number']");
      fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } }); // peso
      fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } }); // standing
      fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } }); // sitting

      await waitFor(() => {
        expect(screen.getByText(/Longitud pierna:/i)).toBeInTheDocument();
      });
    });

    it("debería mostrar 'Longitud pierna', 'Ratio', 'Maturity Offset' y 'Edad al PHV'", async () => {
      renderForm();

      const dateInput = document.querySelector(
        "input[type='date']",
      ) as HTMLInputElement;
      fireEvent.change(dateInput, { target: { value: "2026-01-15" } });

      const numInputs = document.querySelectorAll("input[type='number']");
      fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } });
      fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } });
      fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } });

      await waitFor(() => {
        expect(screen.getByText(/Longitud pierna:/i)).toBeInTheDocument();
        expect(screen.getByText(/Ratio pierna\/sentado:/i)).toBeInTheDocument();
        expect(screen.getByText(/Maturity Offset:/i)).toBeInTheDocument();
        expect(screen.getByText(/Edad al PHV:/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Envío exitoso
  // -------------------------------------------------------------------------
  describe("cuando el formulario se envía correctamente", () => {
    it("debería llamar a la API con los datos correctos", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(mockRecord);
      const onSuccess = vi.fn();
      const wrapper = createWrapper();
      render(
        createElement(
          wrapper,
          null,
          createElement(AnthropometryForm, { ...defaultProps, onSuccess }),
        ),
      );

      const dateInput = document.querySelector(
        "input[type='date']",
      ) as HTMLInputElement;
      fireEvent.change(dateInput, { target: { value: "2026-01-15" } });

      const numInputs = document.querySelectorAll("input[type='number']");
      fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } });
      fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } });
      fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(athletesApi.createAnthropometry).toHaveBeenCalledWith(
          1,
          expect.objectContaining({
            evaluation_date: "2026-01-15",
            weight_kg: 45,
            standing_height_cm: 155,
            sitting_height_cm: 73,
          }),
        );
      });
    });

    it("debería llamar a onSuccess tras el guardado exitoso", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(mockRecord);
      const onSuccess = vi.fn();
      const wrapper = createWrapper();
      render(
        createElement(
          wrapper,
          null,
          createElement(AnthropometryForm, { ...defaultProps, onSuccess }),
        ),
      );

      const dateInput = document.querySelector(
        "input[type='date']",
      ) as HTMLInputElement;
      fireEvent.change(dateInput, { target: { value: "2026-01-15" } });

      const numInputs = document.querySelectorAll("input[type='number']");
      fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } });
      fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } });
      fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalledOnce();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Error de envío
  // -------------------------------------------------------------------------
  describe("cuando el envío falla", () => {
    it("debería mostrar el mensaje de error cuando la API rechaza", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockRejectedValue(
        new Error("Error de red"),
      );
      renderForm();

      const dateInput = document.querySelector(
        "input[type='date']",
      ) as HTMLInputElement;
      fireEvent.change(dateInput, { target: { value: "2026-01-15" } });

      const numInputs = document.querySelectorAll("input[type='number']");
      fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } });
      fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } });
      fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } });

      await userEvent.click(
        screen.getByRole("button", { name: /Guardar medición/i }),
      );

      await waitFor(() => {
        expect(
          screen.getByText(/No se pudo guardar la medición/i),
        ).toBeInTheDocument();
      });
    });
  });
});
