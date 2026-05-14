import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ─── Mock useAthletes ─────────────────────────────────────────────────────────
vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({
    data: {
      items: [
        { id: 1, first_name: "Sebastián", last_name: "García", age_decimal: 13.2, category: "Pre-juvenil A" },
        { id: 2, first_name: "Laura", last_name: "Pérez", age_decimal: 11.5, category: "Infantil B" },
      ],
    },
    isLoading: false,
  }),
}));

import { AudienceSelector } from "./AudienceSelector";
import type { Audience } from "@/types/calendar.types";

function renderSelector(
  value: Audience[] = [],
  onChange = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AudienceSelector value={value} onChange={onChange} />
    </QueryClientProvider>,
  );
}

describe("AudienceSelector", () => {
  it("renders audience type options", () => {
    renderSelector();
    expect(screen.getByText("Todo el club")).toBeInTheDocument();
    expect(screen.getByText("Categoría")).toBeInTheDocument();
    expect(screen.getByText("Lista de atletas")).toBeInTheDocument();
    expect(screen.getByText("Atleta individual")).toBeInTheDocument();
  });

  it("shows category selector when 'Categoría' is selected", async () => {
    const user = userEvent.setup();
    renderSelector();

    const catButton = screen.getByText("Categoría");
    await user.click(catButton);

    expect(screen.getByLabelText(/Categoría FCC/i)).toBeInTheDocument();
  });

  it("shows athlete multi-select when 'Lista de atletas' is selected", async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText("Lista de atletas"));
    expect(screen.getByText("Atletas")).toBeInTheDocument();
  });

  it("shows individual athlete selector when 'Atleta individual' is selected", async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText("Atleta individual"));
    // The label "Atleta" is rendered for the individual selector
    const select = screen.getByRole("combobox", { name: /Atleta/i });
    expect(select).toBeInTheDocument();
  });

  it("calls onChange with all_club audience when adding all_club", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderSelector([], onChange);

    await user.click(screen.getByText("+ Agregar audiencia"));

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ audience_type: "all_club" }),
    ]);
  });

  it("calls onChange with category audience when adding category", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderSelector([], onChange);

    await user.click(screen.getByText("Categoría"));

    // FCC_CATEGORIES[0] = "Pre-Infantil A" is selected by default
    await user.click(screen.getByText("+ Agregar audiencia"));

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        audience_type: "category",
        audience_value: expect.objectContaining({ category: expect.any(String) }),
      }),
    ]);
  });

  it("renders existing audiences in the list", () => {
    const audiences: Audience[] = [
      { audience_type: "all_club", audience_value: {} as Record<string, never> },
      {
        audience_type: "category",
        audience_value: { category: "Infantil A" },
      },
    ];
    renderSelector(audiences);
    // "Todo el club" appears in the radio group AND in the audience list
    const todoClubeItems = screen.getAllByText("Todo el club");
    expect(todoClubeItems.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Categoría: Infantil A")).toBeInTheDocument();
  });

  it("calls onChange minus removed item when Eliminar is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const audiences: Audience[] = [
      { audience_type: "all_club", audience_value: {} as Record<string, never> },
    ];
    renderSelector(audiences, onChange);

    await user.click(screen.getByText("Eliminar"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("resets audience_value fields when audience_type changes", async () => {
    const user = userEvent.setup();
    renderSelector();

    // Select athlete_list
    await user.click(screen.getByText("Lista de atletas"));
    expect(screen.getByText("Atletas")).toBeInTheDocument();

    // Switch to all_club — athlete multi-select should disappear
    await user.click(screen.getByText("Todo el club"));
    expect(screen.queryByText("Atletas")).not.toBeInTheDocument();
  });

  it("does not add audience when athlete_list is selected but no athletes chosen", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderSelector([], onChange);

    await user.click(screen.getByText("Lista de atletas"));
    await user.click(screen.getByText("+ Agregar audiencia"));

    // onChange not called because selectedAthleteIds is empty
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows error message when error prop is provided", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AudienceSelector value={[]} onChange={vi.fn()} error="Campo requerido" />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Campo requerido")).toBeInTheDocument();
  });
});
