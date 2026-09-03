import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

vi.mock("@/hooks/athletes/useAthleteInsights", () => ({
  useAthleteInsights: vi.fn(),
}));

import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { AnalystPicker } from "@/components/newsletter/studio/AnalystPicker";

function mockInsights(items: Array<{ id: number; headline: string; valida_num: number; series_kind: string | null }>) {
  vi.mocked(useAthleteInsights).mockReturnValue({
    data: { items, total: items.length, limit: 50, offset: 0 },
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useAthleteInsights>);
}

describe("AnalystPicker", () => {
  it("muestra mensaje vacío cuando no hay insights adjuntados", () => {
    mockInsights([]);
    render(<AnalystPicker athleteId={42} selectedInsightIds={[]} onReorder={() => {}} />);
    expect(screen.getByTestId("analyst-picker-empty")).toBeInTheDocument();
  });

  it("renderiza los insights en el orden guardado y marca el primero como usado", () => {
    mockInsights([
      { id: 17, headline: "Frenada más firme en curva", valida_num: 3, series_kind: "cup" },
      { id: 42, headline: "Buen ritmo sostenido", valida_num: 4, series_kind: "cup" },
    ]);
    render(
      <AnalystPicker athleteId={42} selectedInsightIds={[42, 17]} onReorder={() => {}} />,
    );
    const items = screen.getAllByTestId(/analyst-picker-item-/);
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveAttribute("data-testid", "analyst-picker-item-42");
    expect(items[0]).toHaveTextContent("Usado en la bitácora");
    expect(items[1]).not.toHaveTextContent("Usado en la bitácora");
  });

  it("subir el segundo elemento envía una permutación válida vía onReorder", () => {
    mockInsights([
      { id: 17, headline: "Frenada más firme", valida_num: 3, series_kind: "cup" },
      { id: 42, headline: "Buen ritmo", valida_num: 4, series_kind: "cup" },
    ]);
    const onReorder = vi.fn();
    render(
      <AnalystPicker athleteId={42} selectedInsightIds={[17, 42]} onReorder={onReorder} />,
    );
    fireEvent.click(screen.getByLabelText("Subir Buen ritmo"));
    const newOrder = onReorder.mock.calls[0][0] as number[];
    expect(newOrder).toEqual([42, 17]);
    expect([...newOrder].sort()).toEqual([...[17, 42]].sort());
  });

  it("el botón Subir del primer elemento está deshabilitado", () => {
    mockInsights([
      { id: 17, headline: "Frenada más firme", valida_num: 3, series_kind: "cup" },
      { id: 42, headline: "Buen ritmo", valida_num: 4, series_kind: "cup" },
    ]);
    render(
      <AnalystPicker athleteId={42} selectedInsightIds={[17, 42]} onReorder={() => {}} />,
    );
    expect(screen.getByLabelText("Subir Frenada más firme")).toBeDisabled();
    expect(screen.getByLabelText("Bajar Buen ritmo")).toBeDisabled();
  });

  it("usa un rótulo de respaldo cuando el insight no tiene headline cargado aún", () => {
    mockInsights([]);
    render(
      <AnalystPicker athleteId={42} selectedInsightIds={[99]} onReorder={() => {}} />,
    );
    expect(screen.getByText("Insight #99")).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    mockInsights([
      { id: 17, headline: "Frenada más firme", valida_num: 3, series_kind: "cup" },
    ]);
    const { container } = render(
      <AnalystPicker athleteId={42} selectedInsightIds={[17]} onReorder={() => {}} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
