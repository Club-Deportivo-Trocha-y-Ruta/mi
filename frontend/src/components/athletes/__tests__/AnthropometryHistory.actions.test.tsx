import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/hooks/ai/useMeasurementExplanation", () => ({
  useMeasurementExplanationCached: vi.fn(() => ({ data: null })),
}));
vi.mock("@/components/ai/AnthropometricRecordExplanationCard", () => ({
  AnthropometricRecordExplanationCard: () => <div>mock explanation</div>,
}));
vi.mock("@/api/athletes", () => ({
  deleteAnthropometry: vi.fn(),
  updateAnthropometry: vi.fn(),
  checkPlausibility: vi.fn(),
  createAnthropometry: vi.fn(),
  getAnthropometry: vi.fn(),
}));

import { AnthropometryHistory } from "../AnthropometryHistory";
import * as api from "@/api/athletes";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

function makeRecord(id: number, overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id,
    athlete_id: 7,
    evaluation_date: "2026-01-15",
    weight_kg: 46,
    standing_height_cm: 157,
    arm_span_cm: null,
    sitting_height_cm: 74,
    leg_length_cm: 83,
    leg_sitting_ratio: 1.12,
    maturity_offset: -0.3,
    age_at_phv: 13,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

function renderHistory(
  records: AnthropometricRecord[],
  mode: "coach" | "parent" = "coach",
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnthropometryHistory records={records} isLoading={false} athleteId={7} mode={mode} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AnthropometryHistory — acciones de fila (feature 048)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("muestra Editar/Eliminar sólo en filas con can_modify", () => {
    renderHistory([
      makeRecord(1, { evaluation_date: "2026-01-15", can_modify: true }),
      makeRecord(2, { evaluation_date: "2026-02-15", can_modify: false }),
      makeRecord(3, { evaluation_date: "2026-03-15" }),
    ]);
    expect(screen.getAllByRole("link", { name: /Editar la medición/ })).toHaveLength(1);
    expect(
      screen.getByRole("link", { name: "Editar la medición del 15/01/2026" }),
    ).toHaveAttribute("href", "/athletes/7/anthropometry/1/edit");
    expect(screen.getAllByRole("button", { name: /Eliminar la medición/ })).toHaveLength(1);
  });

  it("modo padre no muestra acciones aunque can_modify llegue true", () => {
    renderHistory([makeRecord(1, { can_modify: true })], "parent");
    expect(screen.queryByRole("link", { name: /Editar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Eliminar/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Acciones")).not.toBeInTheDocument();
  });

  it("Eliminar abre la confirmación y Cancelar no borra", async () => {
    const user = userEvent.setup();
    renderHistory([makeRecord(1, { can_modify: true })]);
    await user.click(screen.getByRole("button", { name: /Eliminar la medición del 15\/01\/2026/ }));

    const dialog = await screen.findByRole("alertdialog");
    expect(
      within(dialog).getByText("¿Eliminar la medición del 15/01/2026?"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Se eliminarán también los pliegues cutáneos y la explicación de IA/),
    ).toBeInTheDocument();
    expect(await axe(dialog)).toHaveNoViolations();

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(api.deleteAnthropometry).not.toHaveBeenCalled();
  });

  it("confirmar elimina la medición y cierra el diálogo", async () => {
    vi.mocked(api.deleteAnthropometry).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderHistory([makeRecord(5, { can_modify: true })]);
    await user.click(screen.getByRole("button", { name: /Eliminar la medición/ }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Eliminar" }));

    await waitFor(() => expect(api.deleteAnthropometry).toHaveBeenCalledWith(7, 5));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("un 403 se muestra en el diálogo sin cerrarlo", async () => {
    const error = Object.assign(new Error("forbidden"), {
      isAxiosError: true,
      response: { status: 403 },
    });
    vi.mocked(api.deleteAnthropometry).mockRejectedValue(error);
    const user = userEvent.setup();
    renderHistory([makeRecord(5, { can_modify: true })]);
    await user.click(screen.getByRole("button", { name: /Eliminar la medición/ }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Eliminar" }));

    expect(
      await within(dialog).findByText(
        "Solo quien tomó esta medición o un administrador puede eliminarla.",
      ),
    ).toBeInTheDocument();
  });

  it("en el detalle (angosto) las acciones también están disponibles", async () => {
    const user = userEvent.setup();
    renderHistory([makeRecord(1, { can_modify: true })]);
    const mobileList = screen.getByTestId("anthropometry-history");
    await user.click(within(mobileList).getByRole("button", { name: /Ver detalle/ }));
    const detail = await screen.findByRole("dialog");
    expect(within(detail).getByRole("link", { name: /Editar la medición/ })).toBeInTheDocument();
    await user.click(within(detail).getByRole("button", { name: /Eliminar la medición/ }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
  });
});
