/**
 * Tests para CompetitionFiltersBar.
 *
 * Cubre:
 *  - Cambio en chip de estado dispara onChange con value correcto.
 *  - Temporada se controla con selector y propaga number.
 *  - Sede dispara onChange con la sede seleccionada.
 *  - Chip "Próxima" activa localFilters.upcoming + status=scheduled.
 *  - Chip "Con resultados" activa localFilters.hasResults y limpia status.
 *  - Toggle de chip activo lo apaga.
 *  - 0 violaciones a11y.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import {
  CompetitionFiltersBar,
  type LocalFilters,
} from "@/components/competitions/CompetitionFiltersBar";
import type { RaceEventListFilters } from "@/types/raceEvents.types";

function setup(
  value: RaceEventListFilters = { season: 2026 },
  localFilters: LocalFilters = {},
) {
  const onChange = vi.fn();
  const onLocalFiltersChange = vi.fn();
  const utils = render(
    <CompetitionFiltersBar
      value={value}
      onChange={onChange}
      localFilters={localFilters}
      onLocalFiltersChange={onLocalFiltersChange}
    />,
  );
  return { onChange, onLocalFiltersChange, ...utils };
}

describe("CompetitionFiltersBar", () => {
  it("cambio en chip 'Cancelada' dispara onChange con status=cancelled", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ season: 2026 });
    await user.click(screen.getByRole("button", { name: "Cancelada" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ season: 2026, status: "cancelled" }),
    );
  });

  it("temporada cambia a number y propaga", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ season: 2026 });
    await user.selectOptions(screen.getByLabelText("Temporada"), "2027");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ season: 2027 }),
    );
  });

  it("seleccion de sede propaga el nombre del lugar", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ season: 2026 });
    await user.selectOptions(screen.getByLabelText("Sede"), "Cali");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ location: "Cali" }),
    );
  });

  it("chip 'Próxima' activa localFilters.upcoming y fija status=scheduled", async () => {
    const user = userEvent.setup();
    const { onChange, onLocalFiltersChange } = setup({ season: 2026 });
    await user.click(screen.getByRole("button", { name: "Próxima" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "scheduled" }),
    );
    expect(onLocalFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({ upcoming: true }),
    );
  });

  it("chip 'Con resultados' activa localFilters.hasResults y limpia status", async () => {
    const user = userEvent.setup();
    const { onChange, onLocalFiltersChange } = setup({ season: 2026 });
    await user.click(screen.getByRole("button", { name: "Con resultados" }));
    expect(onLocalFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({ hasResults: true }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: undefined }),
    );
  });

  it("chip activo (aria-pressed=true) al click se apaga", async () => {
    const user = userEvent.setup();
    const { onChange, onLocalFiltersChange } = setup(
      { season: 2026, status: "cancelled" },
      {},
    );
    const chip = screen.getByRole("button", { name: "Cancelada" });
    expect(chip).toHaveAttribute("aria-pressed", "true");
    await user.click(chip);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: undefined }),
    );
    expect(onLocalFiltersChange).toHaveBeenCalledWith({});
  });

  it("no introduce violaciones de a11y", async () => {
    const { container } = setup();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
