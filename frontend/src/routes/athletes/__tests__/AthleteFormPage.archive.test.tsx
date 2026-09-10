/**
 * Tests del flujo de archivo de atleta (feature 041 — gobernanza
 * multi-coach, T048). Contrato:
 * specs/041-multi-coach-governance/contracts/athlete-archive.md §10, §12.6.
 *
 * Mockea `@/api/athletes` (getAthlete/archiveAthlete) y usa MSW real
 * (`auditHandlers`) para `GET /api/audit/reason-codes` — mismo patrón que
 * `ClubHistoryPage.test.tsx`.
 */
import type { ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import { auditHandlers } from "@/test/msw/auditHandlers";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex, UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// Polyfills de jsdom requeridos por Radix Select (no implementa Pointer
// Events); mismo workaround documentado por Radix para entornos de test.
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
// bien el ping-pong de focusin/focusout entre ambos (bucle infinito real,
// no un fallo del componente) — se mockea con un <select> nativo para
// probar la lógica de negocio (validación, mutación) sin ese entorno roto.
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
      data-testid="archive-reason-select"
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
  SelectItem: ({
    value,
    children,
  }: {
    value: string;
    children: ReactNode;
  }) => <option value={value}>{children}</option>,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { user: { club_ids: number[]; role: UserRole } }) => unknown,
  ) => selector({ user: { club_ids: [1], role: UserRole.coach } }),
}));

const mockAthlete: AthleteDetailOut = {
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
  latest_anthropometry: null,
};

const getAthleteMock = vi.fn();
const archiveAthleteMock = vi.fn();

vi.mock("@/api/athletes", () => ({
  getAthlete: (...args: unknown[]) => getAthleteMock(...args),
  archiveAthlete: (...args: unknown[]) => archiveAthleteMock(...args),
  getAthletes: vi.fn(),
  createAthlete: vi.fn(),
  updateAthlete: vi.fn(),
  restoreAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

import { AthleteFormPage } from "@/routes/athletes/AthleteFormPage";

/** Expone la ruta actual para verificar la navegación tras archivar. */
function LocationProbe() {
  const location = useLocation();
  return <span data-testid="current-path">{location.pathname}</span>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/athletes/42/edit"]}>
      <QueryClientProvider client={qc}>
        <LocationProbe />
        <Routes>
          <Route
            path="/athletes/:id/edit"
            element={<AthleteFormPage mode="edit" />}
          />
          <Route path="/athletes" element={<span>lista de atletas</span>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...auditHandlers);
  getAthleteMock.mockResolvedValue(mockAthlete);
});

describe("AthleteFormPage — archivar atleta", () => {
  it("el botón dice 'Archivar atleta', no 'Eliminar atleta'", async () => {
    renderPage();
    expect(await screen.findByTestId("archive-athlete-button")).toHaveTextContent(
      "Archivar atleta",
    );
    expect(screen.queryByText("Eliminar atleta")).not.toBeInTheDocument();
  });

  it("valida que se seleccione un motivo antes de confirmar", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("archive-athlete-button"));
    await screen.findByTestId("archive-athlete-dialog");

    await user.click(screen.getByTestId("archive-confirm-button"));

    expect(
      await screen.findByText("Selecciona un motivo para archivar."),
    ).toBeInTheDocument();
    expect(archiveAthleteMock).not.toHaveBeenCalled();
  });

  it("envía { reason_code } y navega a /athletes al archivar con éxito", async () => {
    archiveAthleteMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("archive-athlete-button"));
    await screen.findByTestId("archive-athlete-dialog");

    await screen.findByText("Se retiró del club");
    await user.selectOptions(
      screen.getByTestId("archive-reason-select"),
      "athlete_left_club",
    );
    await user.click(screen.getByTestId("archive-confirm-button"));

    await waitFor(() => {
      expect(archiveAthleteMock).toHaveBeenCalledWith(42, "athlete_left_club");
    });
    await waitFor(() => {
      expect(screen.getByTestId("current-path")).toHaveTextContent("/athletes");
    });
  });

  it("un 409 muestra 'Este atleta ya está archivado.' y mantiene el diálogo abierto", async () => {
    archiveAthleteMock.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: "Este atleta ya está archivado." } },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("archive-athlete-button"));
    await screen.findByTestId("archive-athlete-dialog");

    await screen.findByText("Se retiró del club");
    await user.selectOptions(
      screen.getByTestId("archive-reason-select"),
      "athlete_left_club",
    );
    await user.click(screen.getByTestId("archive-confirm-button"));

    expect(
      await screen.findByText("Este atleta ya está archivado."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("archive-athlete-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("current-path")).toHaveTextContent("/athletes/42/edit");
  });

  it("tone danger: Cancelar mantiene el foco al abrir", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("archive-athlete-button"));
    await screen.findByTestId("archive-athlete-dialog");

    await waitFor(() => {
      expect(screen.getByText("Cancelar")).toHaveFocus();
    });
    expect(archiveAthleteMock).not.toHaveBeenCalled();
  });

  it("jest-axe: sin violaciones con el diálogo cerrado y abierto", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await screen.findByTestId("archive-athlete-button");

    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByTestId("archive-athlete-button"));
    await screen.findByTestId("archive-athlete-dialog");

    expect(await axe(container)).toHaveNoViolations();
  });
});
