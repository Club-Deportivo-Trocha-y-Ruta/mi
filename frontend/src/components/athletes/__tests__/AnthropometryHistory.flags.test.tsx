import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
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

import { AnthropometryHistory } from "../AnthropometryHistory";
import { PLAUSIBILITY_COPY } from "@/lib/anthropometry/plausibilityCopy";
import { makeAnthropometricRecord } from "@/test/msw/anthropometryHandlers";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

function renderHistory(records: AnthropometricRecord[], mode: "coach" | "parent" = "coach") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnthropometryHistory records={records} isLoading={false} athleteId={17} mode={mode} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const FLAGGED = makeAnthropometricRecord({
  id: 1,
  evaluation_date: "2026-09-20",
  can_modify: false,
  plausibility_flags: ["height_decreased", "sitting_ratio_atypical"],
});
const CLEAN = makeAnthropometricRecord({
  id: 2,
  evaluation_date: "2026-06-15",
  can_modify: false,
  plausibility_flags: [],
});

describe("AnthropometryHistory — marcador «Revisar» (feature 048, T039)", () => {
  it("marca sólo las filas con avisos (tarjeta y tabla)", () => {
    renderHistory([FLAGGED, CLEAN]);
    // Una vez en la lista angosta y otra en la tabla de escritorio.
    const badges = screen.getAllByTestId("history-plausibility-badge");
    expect(badges).toHaveLength(2);
    for (const badge of badges) {
      expect(badge).toHaveTextContent("Revisar");
      expect(badge).toHaveAccessibleName("Revisar: ver los avisos de la medición del 20/09/2026");
    }
  });

  it("al tocar abre el detalle con la copia exacta, sin abrir el detalle de la fila", async () => {
    const user = userEvent.setup();
    const { container } = renderHistory([FLAGGED, CLEAN]);

    const desktop = screen.getByTestId("anthropometry-history-desktop");
    await user.click(within(desktop).getByTestId("history-plausibility-badge"));

    const popover = await screen.findByRole("dialog", {
      name: "Avisos de la medición del 20/09/2026",
    });
    expect(within(popover).getByText(PLAUSIBILITY_COPY.height_decreased)).toBeInTheDocument();
    expect(within(popover).getByText(PLAUSIBILITY_COPY.sitting_ratio_atypical)).toBeInTheDocument();
    // El clic no burbujea a la fila: el modal de detalle no se abrió.
    expect(screen.queryByText("Medición del 20/09/2026")).not.toBeInTheDocument();

    // El popover vive en un portal: se audita aparte del historial.
    expect(await axe(container)).toHaveNoViolations();
    expect(await axe(popover)).toHaveNoViolations();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("en la tarjeta móvil el marcador queda fuera del botón de la tarjeta", async () => {
    const user = userEvent.setup();
    renderHistory([FLAGGED]);
    const list = screen.getByTestId("anthropometry-history");
    const badge = within(list).getByTestId("history-plausibility-badge");
    const card = within(list).getByRole("button", {
      name: "Ver detalle de medición del 20/09/2026",
    });
    expect(card).not.toContainElement(badge);

    await user.click(badge);
    expect(
      await screen.findByRole("dialog", { name: "Avisos de la medición del 20/09/2026" }),
    ).toBeInTheDocument();
  });

  it("modo padre: nunca muestra el marcador", () => {
    renderHistory([FLAGGED], "parent");
    expect(screen.queryByTestId("history-plausibility-badge")).not.toBeInTheDocument();
    expect(screen.queryByText("Revisar")).not.toBeInTheDocument();
  });

  it("sin plausibility_flags (registro antiguo) no hay marcador", () => {
    const legacy = makeAnthropometricRecord({ id: 3 });
    delete (legacy as Partial<AnthropometricRecord>).plausibility_flags;
    renderHistory([legacy]);
    expect(screen.queryByTestId("history-plausibility-badge")).not.toBeInTheDocument();
  });
});
