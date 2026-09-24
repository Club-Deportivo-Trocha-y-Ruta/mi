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
 *
 * Hotfix multicopa — identidad de válida (2026-09-16):
 *   - Fila "Prioridad": A/B/C, "Sin prioridad", y "CD" fija en campeonato.
 *   - Fila "Serie": prefiere `seriesShortName` sobre `seriesName` (chip).
 *   - Botón "Editar nombre corto de la copa" solo en válidas de copa (no
 *     campeonato), abre `EditSeriesShortNameDialog` (montaje perezoso —
 *     requiere `QueryClientProvider` solo en los tests que lo abren).
 */
import type { ReactElement } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { mswServer } from "@/test/setup";
import { makeRaceEventRead } from "@/test/msw/raceEventsHandlers";
import {
  raceSeriesHandlers,
  raceSeriesUpdateConflictHandler,
} from "@/test/msw/raceSeriesHandlers";
import { UserRole } from "@/types/enums";

// Espía toast.success/toast.error sin renderizar toasts reales — el
// `<Toaster />` solo se monta en App.tsx, no en estos tests unitarios.
// Mismo patrón de CompetitionDetailPage.associate.test.tsx.
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));
import { toast } from "sonner";

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

function renderWithClient(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  mswServer.use(...raceSeriesHandlers);
});

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

describe("InfoTab — fila Serie", () => {
  it("con seriesName resuelto, muestra el nombre de la serie (no el id crudo)", () => {
    const event = makeRaceEventRead({ series_id: 9 });
    render(<InfoTab event={event} seriesName="Copa Valle 2026" />);

    expect(screen.getByText("Serie")).toBeInTheDocument();
    expect(screen.getByText("Copa Valle 2026")).toBeInTheDocument();
    expect(screen.queryByText("Serie ID")).not.toBeInTheDocument();
    expect(screen.queryByText("9")).not.toBeInTheDocument();
  });

  it("sin seriesName (cargando o no resuelto), muestra '—' en vez del id", () => {
    const event = makeRaceEventRead({ series_id: 9 });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Serie")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("9")).not.toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// Hotfix multicopa — identidad de válida (2026-09-16)
// ---------------------------------------------------------------------------

describe("InfoTab — fila Prioridad", () => {
  it("válida sin prioridad (null) muestra 'Sin prioridad'", () => {
    const event = makeRaceEventRead({ is_championship: false, priority: null });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Prioridad")).toBeInTheDocument();
    expect(screen.getByText("Sin prioridad")).toBeInTheDocument();
  });

  it("válida con priority='A' muestra «A · Objetivo principal» (nunca la letra suelta) sin ninguna nota de correo", () => {
    const event = makeRaceEventRead({ is_championship: false, priority: "A" });
    render(<InfoTab event={event} />);

    expect(screen.getByText("A · Objetivo principal")).toBeInTheDocument();
    expect(screen.queryByText("A")).not.toBeInTheDocument();
    // 2026-09-23: aprobar un insight ya nunca envía correo, sin importar
    // la prioridad — la nota se eliminó de la fila "Prioridad".
    expect(screen.queryByText(/correo/i)).not.toBeInTheDocument();
  });

  it("válida con priority='B' muestra «B · Secundaria» sin ninguna nota de correo", () => {
    const event = makeRaceEventRead({ is_championship: false, priority: "B" });
    render(<InfoTab event={event} />);

    expect(screen.getByText("B · Secundaria")).toBeInTheDocument();
    expect(screen.queryByText(/correo/i)).not.toBeInTheDocument();
  });

  it("válida con priority='C' muestra «C · Diagnóstica»", () => {
    const event = makeRaceEventRead({ is_championship: false, priority: "C" });
    render(<InfoTab event={event} />);

    expect(screen.getByText("C · Diagnóstica")).toBeInTheDocument();
  });

  it("campeonato siempre muestra «Campeonato» (nunca el código 'CD') sin ninguna nota de correo, sin importar event.priority", () => {
    const event = makeRaceEventRead({ is_championship: true, priority: null });
    render(<InfoTab event={event} />);

    expect(screen.getByText("Campeonato")).toBeInTheDocument();
    expect(screen.queryByText("CD")).not.toBeInTheDocument();
    expect(screen.queryByText(/correo/i)).not.toBeInTheDocument();
  });
});

describe("InfoTab — nombre corto de la copa (chip)", () => {
  it("con seriesShortName resuelto, la fila Serie muestra el nombre corto, no el completo", () => {
    const event = makeRaceEventRead({ is_championship: false });
    render(
      <InfoTab
        event={event}
        seriesName="Copa Let's Go Interdepartamental XCO"
        seriesShortName="Let's GO"
      />,
    );

    expect(screen.getByText("Let's GO")).toBeInTheDocument();
    expect(
      screen.queryByText("Copa Let's Go Interdepartamental XCO"),
    ).not.toBeInTheDocument();
  });

  it("sin seriesShortName, la fila Serie cae al nombre completo", () => {
    const event = makeRaceEventRead({ is_championship: false });
    render(<InfoTab event={event} seriesName="Copa Valle 2026" />);

    expect(screen.getByText("Copa Valle 2026")).toBeInTheDocument();
  });

  it("el botón 'Editar nombre corto de la copa' no aparece en campeonatos", () => {
    const event = makeRaceEventRead({ is_championship: true });
    render(<InfoTab event={event} seriesName="Campeonato Departamental 2026" />);

    expect(
      screen.queryByLabelText("Editar nombre corto de la copa"),
    ).not.toBeInTheDocument();
  });
});

describe("InfoTab — diálogo de edición de nombre corto", () => {
  it("abre el diálogo, guarda un nombre corto nuevo y lo cierra (éxito)", async () => {
    const user = userEvent.setup();
    const event = makeRaceEventRead({ series_id: 2, is_championship: false });
    renderWithClient(
      <InfoTab event={event} seriesName="Copa Valle de Ciclomontañismo" />,
    );

    await user.click(
      screen.getByLabelText("Editar nombre corto de la copa"),
    );

    await screen.findByRole("dialog");
    const input = screen.getByRole("textbox", { name: /^Nombre corto/i });
    await user.type(input, "Copa Valle");
    await user.click(
      screen.getByTestId("edit-series-short-name-submit"),
    );

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(toast.success).toHaveBeenCalled();
  });

  it("error 409 (nombre duplicado) muestra el toast de error y mantiene el diálogo abierto", async () => {
    mswServer.use(raceSeriesUpdateConflictHandler);
    const user = userEvent.setup();
    const event = makeRaceEventRead({ series_id: 2, is_championship: false });
    renderWithClient(
      <InfoTab event={event} seriesName="Copa Valle de Ciclomontañismo" />,
    );

    await user.click(
      screen.getByLabelText("Editar nombre corto de la copa"),
    );
    await screen.findByRole("dialog");
    await user.type(screen.getByRole("textbox", { name: /^Nombre corto/i }), "Duplicado");
    await user.click(screen.getByTestId("edit-series-short-name-submit"));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(vi.mocked(toast.error).mock.calls.at(-1)?.[0]).toMatch(
      /Ya existe una serie con ese nombre para la temporada/i,
    );
    // El diálogo sigue abierto — el error se reporta vía toast, no cierra el form.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("validación Zod: más de 40 caracteres muestra error inline y no envía", async () => {
    const user = userEvent.setup();
    const event = makeRaceEventRead({ series_id: 2, is_championship: false });
    renderWithClient(
      <InfoTab event={event} seriesName="Copa Valle de Ciclomontañismo" />,
    );

    await user.click(
      screen.getByLabelText("Editar nombre corto de la copa"),
    );
    const input = await screen.findByRole("textbox", { name: /^Nombre corto/i });
    await user.type(input, "x".repeat(41));
    await user.click(screen.getByTestId("edit-series-short-name-submit"));

    expect(
      await screen.findByText(/Máximo 40 caracteres/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("0 violaciones a11y con el diálogo abierto", async () => {
    const user = userEvent.setup();
    const event = makeRaceEventRead({ series_id: 2, is_championship: false });
    renderWithClient(
      <InfoTab event={event} seriesName="Copa Valle de Ciclomontañismo" />,
    );

    await user.click(
      screen.getByLabelText("Editar nombre corto de la copa"),
    );
    await screen.findByRole("dialog");

    // El Dialog de Radix monta su contenido en un portal bajo document.body.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
