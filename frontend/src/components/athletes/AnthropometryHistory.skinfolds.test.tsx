/**
 * Tests — AnthropometryHistory, marcador "Pliegues" y acción de fila
 * "Agregar/Editar pliegues" (feature 046, US1, T031). Sólo coach.
 * Datos sintéticos; sin nombres.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnthropometryHistory } from "./AnthropometryHistory";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { SkinfoldSetOut } from "@/types/bodyComposition.types";
import { MaturationStatus } from "@/types/enums";

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: 7,
    evaluation_date: "2026-05-10",
    weight_kg: 40,
    standing_height_cm: 150,
    arm_span_cm: null,
    sitting_height_cm: 75,
    leg_length_cm: 75,
    leg_sitting_ratio: 1,
    maturity_offset: -1.5,
    age_at_phv: 13.5, // edad en la evaluación = 12.0
    maturation_status: MaturationStatus.PrePHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-05-10T00:00:00Z",
    notes: null,
    skinfolds: null,
    ...overrides,
  };
}

const withSet = makeRecord({
  id: 2,
  evaluation_date: "2026-08-10",
  skinfolds: { record_id: 2 } as SkinfoldSetOut,
});
const withoutSet = makeRecord({ id: 1, evaluation_date: "2026-05-10" });
const tooYoung = makeRecord({
  id: 3,
  evaluation_date: "2026-01-10",
  age_at_phv: 9.5,
  maturity_offset: -1.5, // edad = 8.0
});

describe("AnthropometryHistory — pliegues (T031)", () => {
  it("muestra el marcador 'Pliegues' sólo en evaluaciones con set", () => {
    render(
      <AnthropometryHistory records={[withSet, withoutSet]} isLoading={false} mode="coach" />,
    );
    // Vista móvil + tabla de escritorio → un marcador por vista.
    expect(screen.getAllByTestId("history-skinfolds-marker")).toHaveLength(2);
  });

  it("ofrece 'Editar pliegues' con set y 'Agregar pliegues' sin set, y avisa al llamador", async () => {
    const onSkinfoldsAction = vi.fn();
    render(
      <AnthropometryHistory
        records={[withSet, withoutSet]}
        isLoading={false}
        mode="coach"
        onSkinfoldsAction={onSkinfoldsAction}
      />,
    );
    const desktop = screen.getByTestId("anthropometry-history-desktop");
    await userEvent.click(within(desktop).getByRole("button", { name: /^Editar pliegues/ }));
    expect(onSkinfoldsAction).toHaveBeenCalledWith(withSet);

    await userEvent.click(within(desktop).getByRole("button", { name: /^Agregar pliegues/ }));
    expect(onSkinfoldsAction).toHaveBeenCalledWith(withoutSet);
    // La acción no abre el detalle de la medición (no propaga el clic de la fila).
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("no ofrece 'Agregar pliegues' cuando el deportista tenía menos de 9 años", () => {
    render(
      <AnthropometryHistory
        records={[tooYoung]}
        isLoading={false}
        mode="coach"
        onSkinfoldsAction={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Agregar pliegues/ })).not.toBeInTheDocument();
  });

  it("en modo familia no hay marcador ni acción", () => {
    render(
      <AnthropometryHistory
        records={[withSet, withoutSet]}
        isLoading={false}
        mode="parent"
        onSkinfoldsAction={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("history-skinfolds-marker")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pliegues/i })).not.toBeInTheDocument();
  });
});
