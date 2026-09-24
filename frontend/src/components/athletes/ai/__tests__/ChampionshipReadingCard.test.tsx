/**
 * Tests de ChampionshipReadingCard (feature 045, T076 / T079).
 *
 * - FR-017: la tarjeta enlaza a su competencia — coach al detalle interno,
 *   familia a su vista de resultados — con un destino táctil de 48 px
 *   (FR-063).
 * - US2/AC3 / FR-020: un valor ausente se lee «sin dato», nunca «—».
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ReactElement } from "react";

import { ChampionshipReadingCard } from "@/components/athletes/ai/ChampionshipReadingCard";
import type { EvolutionPoint } from "@/types/athleteRaceAnalysis.types";

const GROUP = { label: "Campeonato Departamental" };

function makePoint(overrides: Partial<EvolutionPoint> = {}): EvolutionPoint {
  return {
    valida_num: 1,
    event_id: 60,
    event_date: "2025-11-16",
    value: 4,
    unit: "rank",
    series_kind: "championship",
    label: "Campeonato Departamental",
    series_id: 9,
    series_name: "Campeonato Departamental",
    field_size: 15,
    percentile: 78.4,
    position: 4,
    gap_to_median_pct: -3.2,
    gap_pct: 9.4,
    ...overrides,
  } as EvolutionPoint;
}

function renderCard(ui: ReactElement) {
  return render(ui, { wrapper: MemoryRouter });
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

describe("ChampionshipReadingCard — enlace a la competencia (FR-017)", () => {
  it("coach: enlaza al detalle interno de la competencia", () => {
    renderCard(
      <ChampionshipReadingCard point={makePoint()} group={GROUP} audience="coach" />,
    );
    expect(
      screen.getByRole("link", { name: "Ver competencia: Campeonato Departamental" }),
    ).toHaveAttribute("href", "/competitions/60");
  });

  it("familia: enlaza a la vista de resultados de la familia", () => {
    renderCard(
      <ChampionshipReadingCard point={makePoint()} group={GROUP} audience="family" />,
    );
    expect(
      screen.getByRole("link", { name: "Ver competencia: Campeonato Departamental" }),
    ).toHaveAttribute("href", "/parents/competitions/60");
  });

  it("sin `audience` se asume coach", () => {
    renderCard(<ChampionshipReadingCard point={makePoint()} group={GROUP} />);
    expect(screen.getByTestId("championship-reading-card-link")).toHaveAttribute(
      "href",
      "/competitions/60",
    );
  });

  it("el enlace es visible («Ver competencia») y su destino mide al menos 48 px", () => {
    renderCard(<ChampionshipReadingCard point={makePoint()} group={GROUP} />);
    const link = screen.getByTestId("championship-reading-card-link");
    expect(link).toHaveTextContent("Ver competencia");
    expect(link.className).toMatch(/min-h-12/);
    expect(link.className).toMatch(/min-w-12/);
  });

  it("un DNF también enlaza a su competencia", () => {
    renderCard(
      <ChampionshipReadingCard
        point={makePoint({ value: null, position: null })}
        group={GROUP}
        audience="coach"
      />,
    );
    expect(screen.getByText(/no completó la prueba/i)).toBeInTheDocument();
    expect(screen.getByTestId("championship-reading-card-link")).toHaveAttribute(
      "href",
      "/competitions/60",
    );
  });

  it("se activa por teclado (Tab + Enter) y navega", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/atleta"]}>
        <ChampionshipReadingCard point={makePoint()} group={GROUP} audience="family" />
        <LocationProbe />
      </MemoryRouter>,
    );
    await user.tab();
    expect(screen.getByTestId("championship-reading-card-link")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/parents/competitions/60",
    );
  });

  it.each(["coach", "family"] as const)(
    "sin violaciones de accesibilidad (%s)",
    async (audience) => {
      const { container } = renderCard(
        <ChampionshipReadingCard point={makePoint()} group={GROUP} audience={audience} />,
      );
      expect(await axe(container)).toHaveNoViolations();
    },
  );
});

describe("ChampionshipReadingCard — «sin dato» en lugar de «—» (US2/AC3, FR-020)", () => {
  it("posición, parrilla y percentil ausentes se leen «sin dato», nunca «—»", () => {
    renderCard(
      <ChampionshipReadingCard
        point={makePoint({
          // `value` con dato para que NO sea la rama «No completó la prueba».
          value: 1,
          position: null,
          field_size: null,
          percentile: null,
          gap_to_median_pct: null,
          gap_pct: null,
        })}
        group={GROUP}
        audience="coach"
      />,
    );
    const card = screen.getByTestId("championship-reading-card");
    for (const label of [
      "Posición",
      "Parrilla",
      "Brecha vs. mediana",
      "Brecha vs. 1.ª posición",
      "Percentil",
    ]) {
      const tile = within(card).getByText(label).closest("div") as HTMLElement;
      expect(tile).toHaveTextContent("sin dato");
    }
    expect(card).not.toHaveTextContent("—");
  });

  it("un campo chico (< 5 con tiempo): percentil «sin dato» y la posición sigue visible", () => {
    renderCard(
      <ChampionshipReadingCard
        point={makePoint({ percentile: null, gap_to_median_pct: null })}
        group={GROUP}
        audience="family"
      />,
    );
    const card = screen.getByTestId("championship-reading-card");
    expect(within(card).getByText("Percentil").closest("div")).toHaveTextContent(
      "sin dato",
    );
    expect(within(card).getByText("Posición").closest("div")).toHaveTextContent("P4");
    expect(card).not.toHaveTextContent("—");
  });

  it("con todos los datos no aparece «sin dato»", () => {
    renderCard(<ChampionshipReadingCard point={makePoint()} group={GROUP} />);
    const card = screen.getByTestId("championship-reading-card");
    expect(card).not.toHaveTextContent("sin dato");
    expect(card).toHaveTextContent("P4");
    expect(card).toHaveTextContent("15 corredores");
    expect(card).toHaveTextContent("78");
  });
});
