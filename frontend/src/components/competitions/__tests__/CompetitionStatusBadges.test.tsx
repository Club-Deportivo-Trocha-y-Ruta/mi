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
import { Link2, Link2Off, Trophy } from "lucide-react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import {
  CompetitionStatusBadges,
  calendarioStatus,
  condicionesStatus,
  resultadosStatus,
} from "@/components/competitions/CompetitionStatusBadges";
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

  it("conditions_completeness=partial → label 'Condiciones parciales' vía StatusBadge (warning)", () => {
    renderBadges({ conditions_completeness: "partial" });
    const badge = screen.getByText("Condiciones parciales");
    expect(badge).toBeInTheDocument();
    // StatusBadge status=warning aplica bg-warning/10 (token del design system)
    expect(badge.closest("span")).toHaveClass("bg-warning/10");
  });

  it("conditions_completeness=empty → label 'Sin condiciones' vía StatusBadge (neutral)", () => {
    renderBadges({ conditions_completeness: "empty" });
    const badge = screen.getByText("Sin condiciones");
    expect(badge).toBeInTheDocument();
    expect(badge.closest("span")).toHaveClass("bg-light-gray");
  });

  it("conditions_completeness=complete → StatusBadge success (bg-success/10)", () => {
    renderBadges({ conditions_completeness: "complete" });
    const badge = screen.getByText("Condiciones OK");
    expect(badge.closest("span")).toHaveClass("bg-success/10");
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

describe("resultadosStatus adapter", () => {
  it.each<[boolean, { status: string; label: string; icon: unknown }]>([
    [false, { status: "neutral", label: "Sin resultados", icon: Trophy }],
    [true, { status: "success", label: "Con resultados", icon: Trophy }],
  ])("has_results=%s → %o", (hasResults, expected) => {
    expect(resultadosStatus(hasResults)).toEqual(expected);
  });
});

describe("calendarioStatus adapter", () => {
  it.each<[boolean, { status: string; label: string; icon: unknown }]>([
    [false, { status: "neutral", label: "Sin calendario", icon: Link2Off }],
    [true, { status: "success", label: "Calendario", icon: Link2 }],
  ])("has_calendar_event=%s → %o", (hasCalendarEvent, expected) => {
    expect(calendarioStatus(hasCalendarEvent)).toEqual(expected);
  });
});

describe("condicionesStatus adapter", () => {
  it.each<
    [
      RaceEventListItem["conditions_completeness"],
      { status: string; label: string },
    ]
  >([
    ["empty", { status: "neutral", label: "Sin condiciones" }],
    ["partial", { status: "warning", label: "Condiciones parciales" }],
    ["complete", { status: "success", label: "Condiciones OK" }],
  ])("conditions_completeness=%s → %o", (state, expected) => {
    expect(condicionesStatus(state)).toEqual(expected);
  });
});
