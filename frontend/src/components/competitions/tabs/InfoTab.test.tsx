/**
 * InfoTab — tests unitarios.
 *
 * Cubre (feature 023 — Campeonato Nacional):
 *   - Válida regular: badge "Válida {n}" (sin cambios).
 *   - Campeonato con `seriesLevel="departmental"` → "Campeonato Departamental".
 *   - Campeonato con `seriesLevel="national"` → "Campeonato Nacional".
 *   - Campeonato sin `seriesLevel` (ausente/loading, snapshot pre-023) →
 *     fallback "Campeonato Departamental" (comportamiento previo).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { makeRaceEventRead } from "@/test/msw/raceEventsHandlers";
import { InfoTab } from "@/components/competitions/tabs/InfoTab";

describe("InfoTab — tipo de evento", () => {
  it("una válida regular muestra 'Válida {n}'", () => {
    const event = makeRaceEventRead({
      is_championship: false,
      sequence_number: 3,
    });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Válida 3")).toBeInTheDocument();
  });

  it("un campeonato con seriesLevel='departmental' muestra 'Campeonato Departamental'", () => {
    const event = makeRaceEventRead({
      is_championship: true,
      series_id: 9,
    });
    render(<InfoTab event={event} seriesLevel="departmental" />);

    expect(screen.getByText("Campeonato Departamental")).toBeInTheDocument();
  });

  it("un campeonato con seriesLevel='national' muestra 'Campeonato Nacional'", () => {
    const event = makeRaceEventRead({
      is_championship: true,
      series_id: 20,
      name: "Campeonato Nacional MTB · Pereira",
      location: "Pereira",
    });
    render(<InfoTab event={event} seriesLevel="national" />);

    expect(screen.getByText("Campeonato Nacional")).toBeInTheDocument();
    expect(
      screen.queryByText("Campeonato Departamental"),
    ).not.toBeInTheDocument();
  });

  it("un campeonato sin seriesLevel (loading / snapshot pre-023) usa el fallback 'Campeonato Departamental'", () => {
    const event = makeRaceEventRead({
      is_championship: true,
      series_id: 9,
    });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Campeonato Departamental")).toBeInTheDocument();
  });
});
