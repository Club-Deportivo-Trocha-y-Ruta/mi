/**
 * Tests de ArchivedAthletesPage (feature 041 — gobernanza multi-coach, T049).
 * Contrato: specs/041-multi-coach-governance/contracts/athlete-archive.md §11, §12.6.
 *
 * `@/hooks/admin/useArchivedAthletes` y `@/hooks/athletes/useRestoreAthlete`
 * se mockean; `GET /api/audit/reason-codes` corre contra MSW real
 * (`auditHandlers`), mismo patrón que `ClubHistoryPage.test.tsx`.
 */
import type { ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import { auditHandlers } from "@/test/msw/auditHandlers";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

expect.extend(toHaveNoViolations);

// Polyfills de jsdom requeridos por Radix Select — ver AthleteFormPage.archive.test.tsx.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
Error.stackTraceLimit = 10;

// Radix Select + Radix AlertDialog anidan dos FocusScope; jsdom no soporta
// bien el ping-pong de focusin/focusout entre ambos (bucle infinito real
// del entorno, no del componente) — se mockea con un <select> nativo. Ver
// AthleteFormPage.archive.test.tsx.
vi.mock("@/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: ReactNode;
  }) => (
    <select
      data-testid="restore-reason-select"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    >
      <option value="">Selecciona un motivo</option>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

const useArchivedAthletesMock = vi.fn();
vi.mock("@/hooks/admin/useArchivedAthletes", () => ({
  useArchivedAthletes: () => useArchivedAthletesMock(),
}));

const restoreMutateMock = vi.fn();
vi.mock("@/hooks/athletes/useRestoreAthlete", () => ({
  useRestoreAthlete: () => ({ mutate: restoreMutateMock, isPending: false }),
}));

import { ArchivedAthletesPage } from "@/routes/admin/ArchivedAthletesPage";

const archivedAthlete: AthleteOut = {
  id: 42,
  user_id: 142,
  first_name: "Sebastián",
  last_name: "García Ficticio",
  birth_date: "2013-03-01",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 13.4,
  category: "sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
  deleted_at: "2026-09-01T10:00:00",
  deleted_reason_code: "athlete_left_club",
  deleted_by: { user_id: 3, display_name: "Ana Coach" },
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ArchivedAthletesPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...auditHandlers);
});

describe("ArchivedAthletesPage", () => {
  it("muestra la tabla con motivo, actor y fecha", async () => {
    useArchivedAthletesMock.mockReturnValue({
      items: [archivedAthlete],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(await screen.findByTestId("archived-athletes-table")).toBeInTheDocument();
    expect(screen.getByText("Sebastián García Ficticio")).toBeInTheDocument();
    expect(await screen.findByText("Se retiró del club")).toBeInTheDocument();
    expect(screen.getByText("Ana Coach")).toBeInTheDocument();
  });

  it("empty state: 'No hay atletas archivados.'", () => {
    useArchivedAthletesMock.mockReturnValue({
      items: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("No hay atletas archivados.")).toBeInTheDocument();
  });

  it("restaura: pide motivo, llama a la mutación y no lanza si se cancela", async () => {
    useArchivedAthletesMock.mockReturnValue({
      items: [archivedAthlete],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    // `auditReasonCodesHandler` (auditHandlers) solo trae el catálogo
    // `athlete_archive`; el motivo de restauración necesita `athlete_restore`.
    mswServer.use(
      http.get("*/api/audit/reason-codes", () =>
        HttpResponse.json({
          items: [
            {
              code: "restore_mistaken_archive",
              group: "athlete_restore",
              label: "Archivado por error",
            },
            {
              code: "restore_returned_to_club",
              group: "athlete_restore",
              label: "Regresó al club",
            },
          ],
        }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("restore-athlete-button"));
    await screen.findByTestId("restore-athlete-dialog");

    await screen.findByText("Archivado por error");
    await user.selectOptions(
      screen.getByTestId("restore-reason-select"),
      "restore_mistaken_archive",
    );
    await user.click(screen.getByTestId("restore-confirm-button"));

    await waitFor(() => {
      expect(restoreMutateMock).toHaveBeenCalledWith(
        { id: 42, reasonCode: "restore_mistaken_archive" },
        expect.any(Object),
      );
    });
  });

  it("error state: ErrorState con reintentar", () => {
    const refetch = vi.fn();
    useArchivedAthletesMock.mockReturnValue({
      items: [],
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      refetch,
    });

    renderPage();

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("jest-axe: sin violaciones, vacío y poblado", async () => {
    useArchivedAthletesMock.mockReturnValue({
      items: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { container, unmount } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
    unmount();

    useArchivedAthletesMock.mockReturnValue({
      items: [archivedAthlete],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { container: populatedContainer } = renderPage();
    await screen.findByTestId("archived-athletes-table");
    expect(await axe(populatedContainer)).toHaveNoViolations();
  });
});
