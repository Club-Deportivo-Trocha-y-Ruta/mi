/**
 * Tests para CategoryMappingTable (feature 044, US1 + US2, T031).
 *
 * Cubre:
 *  - Columnas: encabezado impreso · categoría · tipo · filas · estado.
 *  - Traducción de `mapping_kind` (exact/rename/season_specific/unknown) a
 *    las cuatro etiquetas en español del contrato.
 *  - Categoría `inconsistent`: lista en lenguaje llano ("Falta el puesto 6.")
 *    y botones "Corregir fila"/"Reconocer"; ausentes en `ok`/`acknowledged`.
 *  - Categoría de encabezado no reconocido (`code=null`): aviso de que no
 *    puede confirmarse, sin acción disponible (esta feature no incluye
 *    mapeo manual).
 *  - Aviso de filas ilegibles cuando `unreadableRows` no está vacío.
 *  - Flujo completo: corregir una fila actualiza el badge de "Inconsistente"
 *    a "Completa" y reporta el nuevo conteo de categorías listas.
 *  - Flujo completo: reconocer una categoría la deja "Reconocida".
 *  - a11y: 0 violaciones jest-axe.
 *
 * Estrategia: mockeamos `@/api/raceImports` (mismo patrón que los tests de
 * los dos diálogos y de `ImportWizard`) — los diálogos reales se montan y
 * se ejercitan de punta a punta.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

expect.extend(toHaveNoViolations);

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

vi.mock("@/api/raceImports", () => ({
  addRaceImportRowCorrection: vi.fn(),
  acknowledgeRaceImportCategory: vi.fn(),
  getAcknowledgeReasons: vi.fn(),
}));

import * as raceImportsApi from "@/api/raceImports";
import { CategoryMappingTable } from "@/components/competitions/import/CategoryMappingTable";
import type { ParsedCategory, ParsedResultsRow } from "@/types/raceImports.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function makeRow(position: number): ParsedResultsRow {
  return {
    position,
    bib: String(100 + position),
    name: `Corredora Ficticia ${position}`,
    city: "Cali",
    club: "Club Ficticio",
    time_raw: "00:40:00",
    points: 0,
  };
}

const CATEGORY_OK: ParsedCategory = {
  header_raw: "PREJUVENIL A DAMAS",
  code: "PREJ_A_F",
  mapping_kind: "exact",
  rows: [makeRow(1), makeRow(2)],
  completeness: { status: "ok", missing: [], duplicated: [] },
};

const CATEGORY_INCONSISTENT: ParsedCategory = {
  header_raw: "INFANTIL A DAMAS",
  code: "INF_A_F",
  mapping_kind: "rename",
  rows: [makeRow(1), makeRow(2), makeRow(3), makeRow(4), makeRow(5), makeRow(7)],
  completeness: { status: "inconsistent", missing: [6], duplicated: [] },
};

const CATEGORY_UNKNOWN: ParsedCategory = {
  header_raw: "CATEGORIA RARA",
  code: null,
  mapping_kind: "unknown",
  rows: [makeRow(1)],
  completeness: { status: "ok", missing: [], duplicated: [] },
};

const REASON_OPTIONS = [
  { code: "source_missing_ordinal", label: "El acta oficial salta un puesto" },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(raceImportsApi.getAcknowledgeReasons).mockResolvedValue({
    options: REASON_OPTIONS,
  });
});

describe("CategoryMappingTable — columnas", () => {
  it("renderiza encabezado impreso, categoría, tipo, filas y estado", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_OK]}
        unreadableRows={[]}
      />,
    );

    const row = screen.getByTestId(`category-row-${CATEGORY_OK.header_raw}`);
    expect(within(row).getByText("PREJUVENIL A DAMAS")).toBeInTheDocument();
    expect(within(row).getByText("PREJ_A_F")).toBeInTheDocument();
    expect(within(row).getByText("Exacta")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument();
    expect(within(row).getByTestId("completeness-badge-ok")).toHaveTextContent(
      "Completa",
    );
  });

  it("traduce cada mapping_kind a su etiqueta en español", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_INCONSISTENT, CATEGORY_UNKNOWN]}
        unreadableRows={[]}
      />,
    );

    expect(
      within(screen.getByTestId(`category-row-${CATEGORY_INCONSISTENT.header_raw}`)).getByText(
        "Renombrada",
      ),
    ).toBeInTheDocument();
    // "Sin reconocer" aparece dos veces en esta fila: la columna Categoría
    // (código null) y la columna Tipo (mapping_kind "unknown").
    expect(
      within(screen.getByTestId(`category-row-${CATEGORY_UNKNOWN.header_raw}`)).getAllByText(
        "Sin reconocer",
      ),
    ).toHaveLength(2);
  });

  it("no renderiza nada cuando no hay categorías", () => {
    const { container } = wrap(
      <CategoryMappingTable parseId="42" categories={[]} unreadableRows={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("CategoryMappingTable — categoría inconsistente", () => {
  it("lista los puestos faltantes/repetidos en lenguaje llano", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_INCONSISTENT]}
        unreadableRows={[]}
      />,
    );

    expect(screen.getByText("Falta el puesto 6.")).toBeInTheDocument();
  });

  it("muestra los botones Corregir fila / Reconocer solo si es inconsistente", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_OK, CATEGORY_INCONSISTENT]}
        unreadableRows={[]}
      />,
    );

    expect(
      screen.getByTestId(`correct-row-${CATEGORY_INCONSISTENT.header_raw}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`acknowledge-${CATEGORY_INCONSISTENT.header_raw}`),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(`correct-row-${CATEGORY_OK.header_raw}`),
    ).not.toBeInTheDocument();
  });
});

describe("CategoryMappingTable — categoría sin reconocer", () => {
  it("advierte que no puede confirmarse, sin ofrecer una acción", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_UNKNOWN]}
        unreadableRows={[]}
      />,
    );

    expect(
      screen.getByText(/no se puede confirmar hasta que el catálogo la reconozca/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(`correct-row-${CATEGORY_UNKNOWN.header_raw}`),
    ).not.toBeInTheDocument();
  });
});

describe("CategoryMappingTable — aviso de filas ilegibles", () => {
  it("muestra el aviso cuando hay filas no legibles", () => {
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_OK]}
        unreadableRows={[{ page: 3, ordinal: null }, { page: 3, ordinal: 9 }]}
      />,
    );

    const notice = screen.getByTestId("unreadable-rows-notice");
    expect(notice).toHaveTextContent(/2 filas/i);
    expect(notice).toHaveTextContent(/página 3/i);
  });

  it("no muestra el aviso cuando no hay filas ilegibles", () => {
    wrap(
      <CategoryMappingTable parseId="42" categories={[CATEGORY_OK]} unreadableRows={[]} />,
    );
    expect(screen.queryByTestId("unreadable-rows-notice")).not.toBeInTheDocument();
  });
});

describe("CategoryMappingTable — conteo de categorías listas", () => {
  it("reporta ready/total al montar", () => {
    const onReadyCountChange = vi.fn();
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_OK, CATEGORY_INCONSISTENT, CATEGORY_UNKNOWN]}
        unreadableRows={[]}
        onReadyCountChange={onReadyCountChange}
      />,
    );

    // Solo CATEGORY_OK está lista (ok + reconocida por el catálogo).
    expect(onReadyCountChange).toHaveBeenLastCalledWith(1, 3);
  });
});

describe("CategoryMappingTable — corregir una fila", () => {
  it("corregir la fila faltante deja la categoría Completa y actualiza el conteo", async () => {
    vi.mocked(raceImportsApi.addRaceImportRowCorrection).mockResolvedValue({
      category_header: CATEGORY_INCONSISTENT.header_raw,
      completeness: { status: "ok", missing: [], duplicated: [] },
    });

    const user = userEvent.setup();
    const onReadyCountChange = vi.fn();
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_INCONSISTENT]}
        unreadableRows={[]}
        onReadyCountChange={onReadyCountChange}
      />,
    );

    await user.click(
      screen.getByTestId(`correct-row-${CATEGORY_INCONSISTENT.header_raw}`),
    );

    // El diálogo precarga "Agregar" con el puesto faltante (6).
    expect(await screen.findByLabelText(/puesto/i)).toHaveValue(6);
    await user.type(screen.getByLabelText(/^nombre$/i), "Corredora Nueva");
    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() =>
      expect(
        screen.getByTestId(`completeness-badge-ok`),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Falta el puesto 6.")).not.toBeInTheDocument();
    await waitFor(() => expect(onReadyCountChange).toHaveBeenLastCalledWith(1, 1));
  });
});

describe("CategoryMappingTable — reconocer una categoría", () => {
  it("reconocer deja la categoría en estado Reconocida", async () => {
    vi.mocked(raceImportsApi.acknowledgeRaceImportCategory).mockResolvedValue({
      category_header: CATEGORY_INCONSISTENT.header_raw,
      completeness: { status: "acknowledged", missing: [6], duplicated: [] },
    });

    const user = userEvent.setup();
    wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_INCONSISTENT]}
        unreadableRows={[]}
      />,
    );

    await user.click(
      screen.getByTestId(`acknowledge-${CATEGORY_INCONSISTENT.header_raw}`),
    );
    await waitFor(() => expect(raceImportsApi.getAcknowledgeReasons).toHaveBeenCalled());

    await user.click(screen.getByRole("combobox", { name: /motivo/i }));
    await user.click(
      await screen.findByRole("option", { name: "El acta oficial salta un puesto" }),
    );
    await user.click(screen.getByRole("button", { name: /^Reconocer$/i }));

    await waitFor(() =>
      expect(screen.getByTestId("completeness-badge-acknowledged")).toBeInTheDocument(),
    );
  });
});

describe("CategoryMappingTable — accesibilidad", () => {
  it("0 violaciones axe con una categoría inconsistente visible", async () => {
    const { container } = wrap(
      <CategoryMappingTable
        parseId="42"
        categories={[CATEGORY_OK, CATEGORY_INCONSISTENT, CATEGORY_UNKNOWN]}
        unreadableRows={[{ page: 2, ordinal: 5 }]}
      />,
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
