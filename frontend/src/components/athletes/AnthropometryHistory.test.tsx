import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnthropometryHistory } from "./AnthropometryHistory";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    weight_kg: 46.0,
    standing_height_cm: 157.0,
    arm_span_cm: null,
    sitting_height_cm: 74.0,
    leg_length_cm: 83.0,
    leg_sitting_ratio: 1.1216,
    maturity_offset: -0.3,
    age_at_phv: 13.0,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

const record1 = makeRecord({
  id: 1,
  evaluation_date: "2025-06-01",
  weight_kg: 43.0,
  standing_height_cm: 152.0,
  maturity_offset: -1.5,
  maturation_status: MaturationStatus.PrePHV,
  training_implications: "Habilidades, juego, coordinacion.",
  notes: "Primera medición",
});

const record2 = makeRecord({
  id: 2,
  evaluation_date: "2026-01-15",
  weight_kg: 46.0,
  standing_height_cm: 157.0,
  maturity_offset: -0.3,
  maturation_status: MaturationStatus.CircaPHV,
  arm_span_cm: 158.0,
});

const record3 = makeRecord({
  id: 3,
  evaluation_date: "2026-04-01",
  weight_kg: 48.5,
  standing_height_cm: 160.0,
  maturity_offset: 1.2,
  maturation_status: MaturationStatus.PostPHV,
  arm_span_cm: 162.0,
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AnthropometryHistory", () => {
  // -------------------------------------------------------------------------
  // Estado de carga
  // -------------------------------------------------------------------------
  describe("cuando isLoading = true", () => {
    it("debería mostrar skeletons animados en lugar de la tabla", () => {
      const { container } = render(
        <AnthropometryHistory records={[]} isLoading={true} />
      );
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("no debería renderizar la tabla cuando está cargando", () => {
      render(<AnthropometryHistory records={[]} isLoading={true} />);
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Sin registros
  // -------------------------------------------------------------------------
  describe("cuando no hay registros", () => {
    it("debería mostrar mensaje de 'No hay mediciones registradas'", () => {
      render(<AnthropometryHistory records={[]} isLoading={false} />);
      expect(
        screen.getByText(/No hay mediciones registradas aún/i)
      ).toBeInTheDocument();
    });

    it("no debería renderizar tabla cuando no hay registros", () => {
      render(<AnthropometryHistory records={[]} isLoading={false} />);
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Tabla con registros
  // -------------------------------------------------------------------------
  describe("cuando hay registros", () => {
    it("debería renderizar la tabla con encabezados", () => {
      render(<AnthropometryHistory records={[record1, record2]} isLoading={false} />);
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText("Fecha")).toBeInTheDocument();
      expect(screen.getByText("Peso")).toBeInTheDocument();
      expect(screen.getByText("Talla")).toBeInTheDocument();
      expect(screen.getByText("Estado PHV")).toBeInTheDocument();
    });

    it("debería mostrar una fila por cada registro", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // 1 encabezado + 3 filas de datos
      expect(rows.length).toBe(4);
    });

    it("debería formatear la fecha como DD/MM/YYYY", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // record1.evaluation_date = "2025-06-01" → "01/06/2025" (aparece en mobile y desktop)
      const matches = screen.getAllByText("01/06/2025");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar el peso con unidad 'kg'", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("43 kg");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar la talla con unidad 'cm'", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("152 cm");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar la envergadura en la columna cuando existe", () => {
      render(<AnthropometryHistory records={[record2]} isLoading={false} />);
      // Aparece en card mobile y tabla desktop
      const matches = screen.getAllByText("158 cm");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar '-' cuando arm_span_cm es null", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // Al menos un '-' en la tabla desktop
      const dashes = screen.getAllByText("-");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });

    it("debería formatear maturity_offset negativo sin signo extra", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      // record1.maturity_offset = -1.5 → "-1.50" (aparece en card mobile y desktop)
      const matches = screen.getAllByText("-1.50");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería formatear maturity_offset positivo con signo '+'", () => {
      render(<AnthropometryHistory records={[record3]} isLoading={false} />);
      // record3.maturity_offset = 1.2 → "+1.20" (aparece en card mobile y desktop)
      const matches = screen.getAllByText("+1.20");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });

  // -------------------------------------------------------------------------
  // Orden de registros (más reciente primero)
  // -------------------------------------------------------------------------
  describe("ordenamiento de registros", () => {
    it("debería mostrar el registro más reciente primero", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // Fila 1 (índice 1 = primera data row) debe tener la fecha más reciente
      // record3 = "2026-04-01" → "01/04/2026"
      expect(rows[1]).toHaveTextContent("01/04/2026");
    });

    it("debería mostrar el registro más antiguo al final", () => {
      render(
        <AnthropometryHistory records={[record1, record2, record3]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      // Última fila data = record1 = "2025-06-01" → "01/06/2025"
      expect(rows[rows.length - 1]).toHaveTextContent("01/06/2025");
    });
  });

  // -------------------------------------------------------------------------
  // Modal de detalle al hacer clic
  // -------------------------------------------------------------------------
  describe("modal de detalle", () => {
    it("no debería mostrar modal al inicio", () => {
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería mostrar el modal al hacer clic en una fila", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]); // primera fila de datos
      expect(screen.getByText(/Medición del 01\/06\/2025/i)).toBeInTheDocument();
    });

    it("debería mostrar el peso del registro en el modal", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/Peso: 43 kg/)).toBeInTheDocument();
    });

    it("debería mostrar implicaciones de entrenamiento si existen", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(
        screen.getByText("Habilidades, juego, coordinacion.")
      ).toBeInTheDocument();
    });

    it("debería mostrar notas si existen", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText("Primera medición")).toBeInTheDocument();
    });

    it("debería mostrar 'No registrada' para envergadura nula", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/No registrada/)).toBeInTheDocument();
    });

    it("debería cerrar el modal al hacer clic en el botón 'x'", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record1]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      // Confirmar que el modal está abierto
      expect(screen.getByText(/Medición del/i)).toBeInTheDocument();
      // Cerrar con el botón x
      await user.click(screen.getByRole("button", { name: "✕" }));
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería cerrar el modal al hacer clic en el backdrop", async () => {
      const user = userEvent.setup();
      const { container } = render(
        <AnthropometryHistory records={[record1]} isLoading={false} />
      );
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      expect(screen.getByText(/Medición del/i)).toBeInTheDocument();
      // El backdrop es el div fixed con bg-black/40
      const backdrop = container.querySelector(".fixed.inset-0");
      expect(backdrop).not.toBeNull();
      await user.click(backdrop!);
      expect(screen.queryByText(/Medición del/i)).not.toBeInTheDocument();
    });

    it("debería mostrar la envergadura cuando existe", async () => {
      const user = userEvent.setup();
      render(<AnthropometryHistory records={[record3]} isLoading={false} />);
      const rows = screen.getAllByRole("row");
      await user.click(rows[1]);
      // record3.arm_span_cm = 162.0 — aparece en la columna de la tabla y dentro del modal
      expect(screen.getByText(/Envergadura: 162/)).toBeInTheDocument();
    });
  });
});
