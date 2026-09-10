/**
 * InfoTab — tests unitarios.
 *
 * Cubre (feature 023 — Campeonato Nacional):
 *   - Válida regular: badge "Válida {n}" (sin cambios).
 *   - Campeonato con `seriesLevel="departmental"` → "Campeonato Departamental".
 *   - Campeonato con `seriesLevel="national"` → "Campeonato Nacional".
 *   - Campeonato sin `seriesLevel` (ausente/loading, snapshot pre-023) →
 *     fallback "Campeonato Departamental" (comportamiento previo).
 *
 * Y (feature 041 — gobernanza multi-coach, T085, contrato
 * coach-activity-report.md §7.3): la tarjeta de auditoría ya no imprime
 * "Creado por usuario ID" con el id crudo — usa `ActorChip`. `useStaff` se
 * mockea (mismo patrón de `ActorChip.test.tsx`) para no requerir un
 * `QueryClientProvider` en estos tests, que no lo tenían.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { makeRaceEventRead } from "@/test/msw/raceEventsHandlers";
import { UserRole } from "@/types/enums";

const useStaffMock = vi.fn(() => ({
  data: {
    items: [
      {
        id: 10,
        email: "ana.coach@example.org",
        first_name: "Ana",
        last_name: "Coach",
        phone: null,
        role: UserRole.coach,
        is_active: true,
        can_login: true,
        created_at: "2026-01-01T00:00:00",
        created_by_display_name: null,
      },
    ],
    total: 1,
  },
  isLoading: false,
}));
vi.mock("@/hooks/admin/useStaff", () => ({
  useStaff: () => useStaffMock(),
}));

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

describe("InfoTab — auditoría (feature 041, T085)", () => {
  it("ya no muestra 'Creado por usuario ID' ni el id crudo", () => {
    const event = makeRaceEventRead({ created_by_user_id: 10 });
    render(<InfoTab event={event} />);

    expect(screen.queryByText("Creado por usuario ID")).not.toBeInTheDocument();
    expect(screen.queryByText("10")).not.toBeInTheDocument();
  });

  it("muestra el nombre resuelto vía ActorChip bajo 'Creado por'", () => {
    const event = makeRaceEventRead({ created_by_user_id: 10 });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Creado por")).toBeInTheDocument();
    expect(screen.getByText("Ana Coach")).toBeInTheDocument();
  });
});
