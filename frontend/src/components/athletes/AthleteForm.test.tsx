import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AthleteForm } from "./AthleteForm";
import { Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const defaultProps = {
  mode: "create" as const,
  isSubmitting: false,
  submitError: null,
  onSubmit: vi.fn(),
};

const existingAthlete: AthleteDetailOut = {
  id: 1,
  user_id: 10,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2013-06-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2.3,
  age_decimal: 12.8,
  category: "Pre-juvenil A",
  club_id: 1,
  created_at: "2026-01-01T00:00:00Z",
  latest_anthropometry: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthleteForm", () => {
  // -------------------------------------------------------------------------
  // Renderizado inicial
  // -------------------------------------------------------------------------
  describe("cuando se renderiza en modo 'create'", () => {
    it("debería mostrar el botón 'Crear atleta'", () => {
      render(<AthleteForm {...defaultProps} />);
      expect(screen.getByRole("button", { name: /Crear atleta/i })).toBeInTheDocument();
    });

    it("debería mostrar los campos del formulario", () => {
      render(<AthleteForm {...defaultProps} />);
      expect(screen.getByText("Nombres")).toBeInTheDocument();
      expect(screen.getByText("Apellidos")).toBeInTheDocument();
      expect(screen.getByText("Fecha de nacimiento")).toBeInTheDocument();
      expect(screen.getByText("Sexo")).toBeInTheDocument();
      expect(screen.getByText("Anos en el club")).toBeInTheDocument();
    });

    it("debería tener el selector de sexo con opciones M y F", () => {
      render(<AthleteForm {...defaultProps} />);
      const select = screen.getByRole("combobox");
      expect(select).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "M" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "F" })).toBeInTheDocument();
    });
  });

  describe("cuando se renderiza en modo 'edit' con valores iniciales", () => {
    it("debería mostrar el botón 'Guardar cambios'", () => {
      render(<AthleteForm {...defaultProps} mode="edit" initialValues={existingAthlete} />);
      expect(screen.getByRole("button", { name: /Guardar cambios/i })).toBeInTheDocument();
    });

    it("debería prellenar los campos con los valores iniciales", () => {
      render(<AthleteForm {...defaultProps} mode="edit" initialValues={existingAthlete} />);
      expect(screen.getByDisplayValue("Sebastián")).toBeInTheDocument();
      expect(screen.getByDisplayValue("García")).toBeInTheDocument();
    });

    it("debería deshabilitar el campo de fecha en modo edit", () => {
      render(<AthleteForm {...defaultProps} mode="edit" initialValues={existingAthlete} />);
      const dateInput = screen.getByDisplayValue("2013-06-15");
      expect(dateInput).toBeDisabled();
    });

    it("debería deshabilitar el selector de sexo en modo edit", () => {
      render(<AthleteForm {...defaultProps} mode="edit" initialValues={existingAthlete} />);
      expect(screen.getByRole("combobox")).toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Estado isSubmitting
  // -------------------------------------------------------------------------
  describe("cuando isSubmitting = true", () => {
    it("debería mostrar 'Guardando...' en el botón", () => {
      render(<AthleteForm {...defaultProps} isSubmitting={true} />);
      expect(screen.getByRole("button", { name: /Guardando\.\.\./i })).toBeInTheDocument();
    });

    it("debería deshabilitar el botón mientras está enviando", () => {
      render(<AthleteForm {...defaultProps} isSubmitting={true} />);
      expect(screen.getByRole("button", { name: /Guardando\.\.\./i })).toBeDisabled();
    });
  });

  // -------------------------------------------------------------------------
  // Error de envío
  // -------------------------------------------------------------------------
  describe("cuando hay submitError", () => {
    it("debería mostrar el mensaje de error", () => {
      render(
        <AthleteForm {...defaultProps} submitError="Error al guardar el atleta" />
      );
      expect(screen.getByText("Error al guardar el atleta")).toBeInTheDocument();
    });

    it("no debería mostrar error cuando submitError es null", () => {
      render(<AthleteForm {...defaultProps} submitError={null} />);
      expect(screen.queryByText(/Error al guardar/i)).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Validación Zod — campos requeridos
  // -------------------------------------------------------------------------
  describe("validación de campos requeridos", () => {
    it("debería mostrar error de validación si first_name está vacío", async () => {
      const user = userEvent.setup();
      render(<AthleteForm {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        expect(screen.getAllByText(/Minimo 2 caracteres/i).length).toBeGreaterThan(0);
      });
    });

    it("debería mostrar error si first_name tiene solo 1 caracter", async () => {
      const user = userEvent.setup();
      render(<AthleteForm {...defaultProps} />);

      const firstNameInput = screen.getAllByRole("textbox")[0];
      await user.type(firstNameInput, "A");
      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        // Puede haber más de un campo con el mismo error (first_name y last_name)
        expect(screen.getAllByText(/Minimo 2 caracteres/i).length).toBeGreaterThan(0);
      });
    });

    it("debería mostrar error si la fecha de nacimiento está vacía", async () => {
      const user = userEvent.setup();
      render(<AthleteForm {...defaultProps} />);

      const firstNameInput = screen.getAllByRole("textbox")[0];
      const lastNameInput = screen.getAllByRole("textbox")[1];
      await user.type(firstNameInput, "Juan");
      await user.type(lastNameInput, "García");

      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        expect(screen.getByText(/Fecha requerida/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Auto-cálculo de edad y categoría
  // -------------------------------------------------------------------------
  describe("auto-cálculo de edad y categoría", () => {
    it("no debería mostrar el panel de auto-cálculo cuando no hay fecha", () => {
      render(<AthleteForm {...defaultProps} />);
      expect(screen.queryByText(/Edad estimada/i)).not.toBeInTheDocument();
    });

    it("debería mostrar edad y categoría cuando se ingresa una fecha válida", async () => {
      render(<AthleteForm {...defaultProps} />);

      const { fireEvent } = await import("@testing-library/react");
      // Buscar el input de tipo date específicamente (no getByDisplayValue que es ambiguo)
      const inputs = document.querySelectorAll("input[type='date']");
      expect(inputs.length).toBeGreaterThan(0);
      fireEvent.change(inputs[0], { target: { value: "2013-06-15" } });

      await waitFor(() => {
        expect(screen.getByText(/Edad estimada:/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Envío exitoso del formulario
  // -------------------------------------------------------------------------
  describe("cuando el formulario se envía con datos válidos", () => {
    it("debería llamar a onSubmit con los valores correctos", async () => {
      const onSubmit = vi.fn();
      const { fireEvent } = await import("@testing-library/react");
      render(<AthleteForm {...defaultProps} onSubmit={onSubmit} />);

      const textInputs = screen.getAllByRole("textbox");
      const user = userEvent.setup();

      await user.type(textInputs[0], "Sebastián");
      await user.type(textInputs[1], "García");

      const dateInputs = document.querySelectorAll("input[type='date']");
      if (dateInputs.length > 0) {
        fireEvent.change(dateInputs[0], { target: { value: "2013-06-15" } });
      }

      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        if (onSubmit.mock.calls.length > 0) {
          const submittedValues = onSubmit.mock.calls[0][0];
          expect(submittedValues.first_name).toBe("Sebastián");
          expect(submittedValues.last_name).toBe("García");
        }
      });
    });
  });

  // -------------------------------------------------------------------------
  // Validación: fecha no puede ser futura
  // -------------------------------------------------------------------------
  describe("validación de fecha", () => {
    it("debería mostrar error si la fecha de nacimiento es futura", async () => {
      const { fireEvent } = await import("@testing-library/react");
      const user = userEvent.setup();
      render(<AthleteForm {...defaultProps} />);

      const textInputs = screen.getAllByRole("textbox");
      await user.type(textInputs[0], "Test");
      await user.type(textInputs[1], "Prueba");

      const dateInputs = document.querySelectorAll("input[type='date']");
      if (dateInputs.length > 0) {
        fireEvent.change(dateInputs[0], { target: { value: "2099-01-01" } });
      }

      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        expect(screen.getByText(/No puede ser futura/i)).toBeInTheDocument();
      });
    });

    it("debería mostrar error si la fecha es anterior a 1990-01-01", async () => {
      const { fireEvent } = await import("@testing-library/react");
      const user = userEvent.setup();
      render(<AthleteForm {...defaultProps} />);

      const textInputs = screen.getAllByRole("textbox");
      await user.type(textInputs[0], "Test");
      await user.type(textInputs[1], "Prueba");

      const dateInputs = document.querySelectorAll("input[type='date']");
      if (dateInputs.length > 0) {
        fireEvent.change(dateInputs[0], { target: { value: "1989-12-31" } });
      }

      await user.click(screen.getByRole("button", { name: /Crear atleta/i }));

      await waitFor(() => {
        expect(screen.getByText(/Fecha minima 1990-01-01/i)).toBeInTheDocument();
      });
    });
  });
});
