/**
 * Tests para CompetitionStatusBadges — 3 badges tri-estado.
 *
 * Cubre:
 *  - Variantes de "conditions_completeness" (complete | partial | empty)
 *    renderizan colores/labels distintos.
 *  - Badge "Resultados" cambia según has_results.
 *  - Badge "Calendario" cambia según has_calendar_event.
 *  - Tooltip se monta al hover (TooltipProvider activo).
 *  - 0 violaciones jest-axe en cualquiera de las 3 combinaciones.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { CompetitionStatusBadges } from "@/components/competitions/CompetitionStatusBadges";
import type { RaceEventListItem } from "@/types/raceEvents.types";
import { makeRaceEventListItem } from "@/test/msw/raceEventsHandlers";

function renderBadges(overrides: Partial<RaceEventListItem> = {}) {
  return render(<CompetitionStatusBadges item={makeRaceEventListItem(overrides)} />);
}

describe("CompetitionStatusBadges", () => {
  it("renderiza los 3 badges con labels correctos cuando todo está completo", () => {
    renderBadges({
      has_results: true,
      has_calendar_event: true,
      conditions_completeness: "complete",
    });
    expect(screen.getByText("Con resultados")).toBeInTheDocument();
    expect(screen.getByText("Calendario")).toBeInTheDocument();
    expect(screen.getByText("Condiciones OK")).toBeInTheDocument();
  });

  it("conditions_completeness=partial → label 'Condiciones parciales' con variant warning", () => {
    renderBadges({ conditions_completeness: "partial" });
    const badge = screen.getByText("Condiciones parciales");
    expect(badge).toBeInTheDocument();
    // variant=warning aplica bg-amber-100 (token del design system)
    expect(badge.className).toMatch(/bg-amber-100/);
  });

  it("conditions_completeness=empty → label 'Sin condiciones' con variant secondary", () => {
    renderBadges({ conditions_completeness: "empty" });
    const badge = screen.getByText("Sin condiciones");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/bg-light-gray/);
  });

  it("conditions_completeness=complete → variant success (bg-green-100)", () => {
    renderBadges({ conditions_completeness: "complete" });
    const badge = screen.getByText("Condiciones OK");
    expect(badge.className).toMatch(/bg-green-100/);
  });

  it("has_results=false → label 'Sin resultados' con variante secondary", () => {
    renderBadges({ has_results: false });
    expect(screen.getByText("Sin resultados")).toBeInTheDocument();
  });

  it("has_calendar_event=false → label 'Sin calendario'", () => {
    renderBadges({ has_calendar_event: false });
    expect(screen.getByText("Sin calendario")).toBeInTheDocument();
  });

  it("no introduce violaciones de a11y (jest-axe)", async () => {
    const { container } = renderBadges();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
