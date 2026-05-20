/**
 * Tests para AthleteCombobox.
 *
 * Casos cubiertos:
 *  - Carga: skeleton mientras isLoading
 *  - Empty: mensaje cuando lista vacía
 *  - Error: alert cuando isError
 *  - Búsqueda fuzzy + sin acentos (Sofía → "sofia")
 *  - Selección con click setea el value (number)
 *  - Selección con teclado (ArrowDown + Enter)
 *  - allowAny: item "Cualquier deportista" emite null
 *  - a11y: jest-axe sin violaciones
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, useState, type ReactNode } from "react";

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn(),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as athletesApi from "@/api/athletes";
import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import type { AthleteListOut, AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

expect.extend(toHaveNoViolations);

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function makeAthlete(overrides: Partial<AthleteOut> = {}): AthleteOut {
  return {
    id: 1,
    user_id: 10,
    first_name: "Sofía",
    last_name: "López",
    birth_date: "2013-06-15",
    sex: Sex.F,
    club_join_date: "2024-01-01",
    years_in_club: 2.3,
    age_decimal: 12.8,
    category: "INF_A",
    club_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const baseList: AthleteListOut = {
  items: [
    makeAthlete({ id: 1, first_name: "Sofía", last_name: "López", category: "INF_A" }),
    makeAthlete({ id: 2, first_name: "Tomás", last_name: "García", category: "PRE_A" }),
    makeAthlete({ id: 3, first_name: "Daniela", last_name: "Rodríguez", category: "JUV_B" }),
  ],
  total: 3,
};

/** Wrapper controlado para inspeccionar onChange. */
function Controlled({
  onChangeSpy,
  initial = null,
  ...rest
}: {
  onChangeSpy: (v: number | null) => void;
  initial?: number | null;
  allowAny?: boolean;
  label?: string;
  error?: string;
}) {
  const [value, setValue] = useState<number | null>(initial);
  return (
    <AthleteCombobox
      value={value}
      onChange={(v) => {
        setValue(v);
        onChangeSpy(v);
      }}
      {...rest}
    />
  );
}

describe("AthleteCombobox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra skeleton mientras carga", async () => {
    // never resolves → query queda pending
    vi.mocked(athletesApi.getAthletes).mockReturnValue(
      new Promise<AthleteListOut>(() => {}),
    );
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    const skeletons = await screen.findAllByTestId(/athlete-combobox-skeleton/);
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("muestra estado vacío si no hay coincidencias", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue({ items: [], total: 0 });
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await waitFor(() => {
      expect(screen.getByTestId("athlete-combobox-empty")).toBeInTheDocument();
    });
  });

  it("muestra alert si la API falla", async () => {
    vi.mocked(athletesApi.getAthletes).mockRejectedValue(new Error("boom"));
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await waitFor(() => {
      expect(screen.getByTestId("athlete-combobox-error-state")).toBeInTheDocument();
    });
  });

  it("filtra fuzzy ignorando acentos (sofia → Sofía López)", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    // Espera a que carguen las opciones.
    await waitFor(() => {
      expect(screen.getByTestId("athlete-combobox-option-1")).toBeInTheDocument();
    });

    // Buscar "sofia" (sin acento) debe encontrar a Sofía.
    const searchInput = screen.getByTestId("athlete-combobox-search");
    await user.type(searchInput, "sofia");

    await waitFor(() => {
      const popover = screen.getByTestId("athlete-combobox-popover");
      expect(within(popover).getByTestId("athlete-combobox-option-1")).toBeInTheDocument();
      expect(within(popover).queryByTestId("athlete-combobox-option-2")).not.toBeInTheDocument();
      expect(within(popover).queryByTestId("athlete-combobox-option-3")).not.toBeInTheDocument();
    });
  });

  it("filtra por categoría (case-insensitive)", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await screen.findByTestId("athlete-combobox-option-1");

    await user.type(screen.getByTestId("athlete-combobox-search"), "juv");

    await waitFor(() => {
      const popover = screen.getByTestId("athlete-combobox-popover");
      expect(within(popover).getByTestId("athlete-combobox-option-3")).toBeInTheDocument();
      expect(within(popover).queryByTestId("athlete-combobox-option-1")).not.toBeInTheDocument();
    });
  });

  it("selección con click setea el value y emite onChange con el id (number)", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByTestId("athlete-combobox-option-2"));

    expect(spy).toHaveBeenCalledWith(2);
    // Trigger refleja la selección.
    expect(screen.getByRole("combobox")).toHaveTextContent(/Tomás García/);
  });

  it("selección con teclado (ArrowDown + Enter) funciona", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    // Espera a que las opciones rendericen + auto-foco del input.
    const searchInput = await screen.findByTestId("athlete-combobox-search");
    await waitFor(() => expect(searchInput).toHaveFocus());

    // activeIndex empieza en 0 → primer item. ArrowDown → segundo item.
    await user.keyboard("{ArrowDown}{Enter}");

    await waitFor(() => expect(spy).toHaveBeenCalledWith(2));
  });

  it("allowAny: item 'Cualquier deportista' emite null", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} initial={1} allowAny />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    const anyOption = await screen.findByTestId("athlete-combobox-option-any");
    await user.click(anyOption);

    expect(spy).toHaveBeenCalledWith(null);
  });

  it("muestra el error de validación cuando se pasa la prop error", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(
      <Controlled
        onChangeSpy={spy}
        error="Selecciona un deportista del listado"
      />,
    );

    expect(
      screen.getByText(/Selecciona un deportista del listado/),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-invalid", "true");
  });

  it("a11y: sin violaciones serias/críticas en estado cerrado", async () => {
    vi.mocked(athletesApi.getAthletes).mockResolvedValue(baseList);
    const spy = vi.fn();
    const { container } = wrap(
      <Controlled onChangeSpy={spy} label="Deportista" />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
