/**
 * Tests para BarrioCombobox (feature 047, IMDERTY).
 *
 * Casos cubiertos:
 *  - Carga: skeleton mientras isLoading
 *  - Empty: mensaje cuando lista vacía
 *  - Error: alert cuando isError
 *  - Búsqueda fuzzy + diacritic-insensitive ("yumbo" → "YUMBO")
 *  - Muestra la zona junto al nombre del barrio
 *  - Opción fija «Otro municipio» → emite { barrioId: null, otherMunicipality: true }
 *  - Selección de un barrio del catálogo → emite { barrioId, otherMunicipality: false }
 *  - Selección con teclado (ArrowDown + Enter)
 *  - a11y: jest-axe sin violaciones
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, useState, type ReactNode } from "react";

vi.mock("@/api/imderty", () => ({
  getBarrios: vi.fn(),
}));

import * as imdertyApi from "@/api/imderty";
import { BarrioCombobox, type BarrioComboboxValue } from "@/components/imderty/BarrioCombobox";
import type { Barrio } from "@/schemas/imderty";

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

function makeBarrio(overrides: Partial<Barrio> = {}): Barrio {
  return {
    id: 1,
    name: "El Retiro",
    zone: "1",
    is_active: true,
    ...overrides,
  };
}

const baseList: Barrio[] = [
  makeBarrio({ id: 1, name: "El Retiro", zone: "1" }),
  makeBarrio({ id: 2, name: "YUMBO", zone: "2" }),
  makeBarrio({ id: 3, name: "Menga", zone: "ZONA NORTE" }),
];

const NO_SELECTION: BarrioComboboxValue = { barrioId: null, otherMunicipality: false };

/** Wrapper controlado para inspeccionar onChange. */
function Controlled({
  onChangeSpy,
  initial = NO_SELECTION,
  ...rest
}: {
  onChangeSpy: (v: BarrioComboboxValue) => void;
  initial?: BarrioComboboxValue;
  label?: string;
  error?: string;
}) {
  const [value, setValue] = useState<BarrioComboboxValue>(initial);
  return (
    <BarrioCombobox
      value={value}
      onChange={(v) => {
        setValue(v);
        onChangeSpy(v);
      }}
      {...rest}
    />
  );
}

describe("BarrioCombobox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra skeleton mientras carga", async () => {
    vi.mocked(imdertyApi.getBarrios).mockReturnValue(new Promise<Barrio[]>(() => {}));
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    const skeletons = await screen.findAllByTestId(/barrio-combobox-skeleton/);
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("muestra estado vacío si no hay coincidencias", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue([]);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await user.type(screen.getByTestId("barrio-combobox-search"), "zzz");

    await waitFor(() => {
      expect(screen.getByTestId("barrio-combobox-empty")).toBeInTheDocument();
    });
  });

  it("muestra alert si la API falla", async () => {
    vi.mocked(imdertyApi.getBarrios).mockRejectedValue(new Error("boom"));
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await waitFor(() => {
      expect(screen.getByTestId("barrio-combobox-error-state")).toBeInTheDocument();
    });
  });

  it("incluye siempre la opción «Otro municipio» junto al catálogo", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await waitFor(() => {
      expect(screen.getByTestId("barrio-combobox-option-other")).toBeInTheDocument();
      expect(screen.getByTestId("barrio-combobox-option-1")).toBeInTheDocument();
    });
  });

  it("muestra la zona junto al nombre del barrio", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    await waitFor(() => {
      const option = screen.getByTestId("barrio-combobox-option-1");
      expect(within(option).getByText("Comuna 1")).toBeInTheDocument();
    });

    const ruralOption = screen.getByTestId("barrio-combobox-option-3");
    expect(within(ruralOption).getByText("ZONA NORTE")).toBeInTheDocument();
  });

  it("busca sin distinguir mayúsculas ni acentos («yumbo» encuentra «YUMBO»)", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await screen.findByTestId("barrio-combobox-option-2");

    await user.type(screen.getByTestId("barrio-combobox-search"), "yumbo");

    await waitFor(() => {
      const popover = screen.getByTestId("barrio-combobox-popover");
      expect(within(popover).getByTestId("barrio-combobox-option-2")).toBeInTheDocument();
      expect(within(popover).queryByTestId("barrio-combobox-option-1")).not.toBeInTheDocument();
      expect(within(popover).queryByTestId("barrio-combobox-option-3")).not.toBeInTheDocument();
    });
  });

  it("seleccionar un barrio del catálogo emite { barrioId, otherMunicipality: false }", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByTestId("barrio-combobox-option-2"));

    expect(spy).toHaveBeenCalledWith({ barrioId: 2, otherMunicipality: false });
    expect(screen.getByRole("combobox")).toHaveTextContent(/YUMBO/);
  });

  it("seleccionar «Otro municipio» emite { barrioId: null, otherMunicipality: true }", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} initial={{ barrioId: 1, otherMunicipality: false }} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByTestId("barrio-combobox-option-other"));

    expect(spy).toHaveBeenCalledWith({ barrioId: null, otherMunicipality: true });
    expect(screen.getByRole("combobox")).toHaveTextContent(/Otro municipio/);
  });

  it("selección con teclado (ArrowDown + Enter) funciona", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));

    const searchInput = await screen.findByTestId("barrio-combobox-search");
    await waitFor(() => expect(searchInput).toHaveFocus());

    // Item 0 = "Otro municipio", ArrowDown → item 1 = primer barrio (id 1).
    await user.keyboard("{ArrowDown}{Enter}");

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ barrioId: 1, otherMunicipality: false }),
    );
  });

  it("botón de limpiar vuelve a { barrioId: null, otherMunicipality: false }", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} initial={{ barrioId: 1, otherMunicipality: false }} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveTextContent(/El Retiro/);
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId("barrio-combobox-clear"));

    expect(spy).toHaveBeenCalledWith(NO_SELECTION);
  });

  it("muestra el error de validación cuando se pasa la prop error", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    wrap(<Controlled onChangeSpy={spy} error="Selecciona un barrio del catálogo" />);

    expect(screen.getByText(/Selecciona un barrio del catálogo/)).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-invalid", "true");
  });

  it("a11y: sin violaciones serias/críticas en estado cerrado", async () => {
    vi.mocked(imdertyApi.getBarrios).mockResolvedValue(baseList);
    const spy = vi.fn();
    const { container } = wrap(<Controlled onChangeSpy={spy} label="Barrio" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
