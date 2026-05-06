import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GrowthCharts } from "./GrowthCharts";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// Mock html-to-image para no ejecutar conversiones reales en jsdom.
// Usamos una variable externa para poder hacer assertions en los tests.
const mockToPng = vi.fn().mockResolvedValue("data:image/png;base64,AAAA");
vi.mock("html-to-image", () => ({ toPng: mockToPng }));

// Recharts usa ResizeObserver y SVG que jsdom no implementa completamente.
// Mockeamos los componentes de Recharts para evitar errores de resize y SVG.
// El Tooltip mock invoca labelFormatter y formatter para ejercer las funciones
// helper internas del componente (formatDateLabel, formatDateTooltip).
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 800, height: 300 }}>
        {children}
      </div>
    ),
    LineChart: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="line-chart">{children}</div>
    ),
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Line: () => null,
    ReferenceLine: () => null,
    // Tooltip mock que invoca labelFormatter y formatter para cubrir las funciones
    // helper privadas formatDateLabel y formatDateTooltip del componente.
    Tooltip: ({
      formatter,
      labelFormatter,
    }: {
      formatter?: (value: unknown) => unknown;
      labelFormatter?: (label: string, payload: { payload: { date: string } }[]) => string;
    }) => {
      const mockPayload = [{ payload: { date: "2026-01-15" } }];
      // Invocar los callbacks para instrumentar las líneas de cobertura
      if (formatter) formatter(155);
      if (labelFormatter) labelFormatter("01/2026", mockPayload);
      return null;
    },
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
    athlete_id: 1,
    evaluation_date: "2026-01-01",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 73.0,
    leg_length_cm: 82.0,
    leg_sitting_ratio: 1.1233,
    maturity_offset: -0.5,
    age_at_phv: 13.5,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-01T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

const recordA = makeRecord({ id: 1, evaluation_date: "2025-06-01", weight_kg: 43.0, standing_height_cm: 152.0, maturity_offset: -1.5, maturation_status: MaturationStatus.PrePHV });
const recordB = makeRecord({ id: 2, evaluation_date: "2026-01-15", weight_kg: 46.0, standing_height_cm: 157.0, maturity_offset: -0.3, maturation_status: MaturationStatus.CircaPHV });
const recordC = makeRecord({ id: 3, evaluation_date: "2026-04-01", weight_kg: 48.5, standing_height_cm: 160.0, maturity_offset: 0.8, maturation_status: MaturationStatus.CircaPHV });

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GrowthCharts", () => {
  // -------------------------------------------------------------------------
  // Caso con menos de 2 registros
  // -------------------------------------------------------------------------
  describe("cuando hay menos de 2 registros", () => {
    it("debería mostrar mensaje explicativo con 0 registros", () => {
      render(<GrowthCharts records={[]} />);
      expect(
        screen.getByText(/Se necesitan al menos 2 mediciones/i)
      ).toBeInTheDocument();
    });

    it("debería mostrar mensaje explicativo con exactamente 1 registro", () => {
      render(<GrowthCharts records={[recordA]} />);
      expect(
        screen.getByText(/Se necesitan al menos 2 mediciones/i)
      ).toBeInTheDocument();
    });

    it("no debería renderizar gráficas con 0 registros", () => {
      render(<GrowthCharts records={[]} />);
      expect(screen.queryByText("Talla vs Tiempo")).not.toBeInTheDocument();
    });

    it("no debería renderizar gráficas con 1 registro", () => {
      render(<GrowthCharts records={[recordA]} />);
      expect(screen.queryByText("Talla vs Tiempo")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Caso con 2 o más registros
  // -------------------------------------------------------------------------
  describe("cuando hay 2 o más registros", () => {
    it("debería renderizar el título 'Talla vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar el título 'Peso vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Peso vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar el título 'Maturity Offset vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Maturity Offset vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar las 3 gráficas con 3 registros", () => {
      render(<GrowthCharts records={[recordA, recordB, recordC]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
      expect(screen.getByText("Peso vs Tiempo")).toBeInTheDocument();
      expect(screen.getByText("Maturity Offset vs Tiempo")).toBeInTheDocument();
    });

    it("no debería mostrar el mensaje de 'al menos 2 mediciones' cuando hay suficientes registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(
        screen.queryByText(/Se necesitan al menos 2 mediciones/i)
      ).not.toBeInTheDocument();
    });

    it("debería renderizar los contenedores responsivos para cada gráfica", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      const containers = screen.getAllByTestId("responsive-container");
      // 3 gráficas → 3 contenedores
      expect(containers.length).toBe(3);
    });
  });

  // -------------------------------------------------------------------------
  // Exactamente en el límite: 2 registros
  // -------------------------------------------------------------------------
  describe("en el límite de exactamente 2 registros", () => {
    it("debería mostrar gráficas con exactamente 2 registros (límite mínimo)", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
      expect(
        screen.queryByText(/Se necesitan al menos 2 mediciones/i)
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Visibilidad de pestaña Peso según ageDecimal (regla OMS weight_for_age ≤10y)
  // -------------------------------------------------------------------------
  describe("pestaña Peso — regla OMS weight_for_age ≤10 años", () => {
    /** Helper: busca los pill-buttons dentro de la sección de percentiles.
     *  Los pills son los únicos buttons con texto exacto "Talla", "IMC" o "Peso".
     *  Los botones de vista ("Longitudinal", "Curvas de percentiles") tienen texto distinto.
     */
    async function switchToPercentiles() {
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: "Curvas de percentiles" }));
      });
    }

    it("ageDecimal=8 → 3 tabs visibles (Talla, IMC, Peso)", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2017-06-01"
          ageDecimal={8}
        />,
      );
      await switchToPercentiles();

      expect(screen.getByRole("button", { name: "Talla" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "IMC" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Peso" })).toBeInTheDocument();
    });

    it("ageDecimal=11 → solo 2 tabs (Talla, IMC), sin tab Peso", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2014-06-01"
          ageDecimal={11}
        />,
      );
      await switchToPercentiles();

      expect(screen.getByRole("button", { name: "Talla" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "IMC" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Peso" })).not.toBeInTheDocument();
    });

    it("ageDecimal=undefined → 3 tabs visibles (comportamiento legacy/safe)", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentiles();

      expect(screen.getByRole("button", { name: "Talla" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "IMC" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Peso" })).toBeInTheDocument();
    });

    it("ageDecimal=11 → indicador activo hace fallback a height_for_age (no aparece pill Peso)", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2014-06-01"
          ageDecimal={11}
        />,
      );
      await switchToPercentiles();

      // La tab Peso no existe — el fallback a height_for_age fue aplicado
      expect(screen.queryByRole("button", { name: "Peso" })).not.toBeInTheDocument();
      // El pill Talla sí existe y tiene la clase activa
      const tallaPill = screen.getByRole("button", { name: "Talla" });
      expect(tallaPill).toBeInTheDocument();
      expect(tallaPill.className).toContain("bg-charcoal");
    });
  });

  // -------------------------------------------------------------------------
  // Boton "Descargar PNG"
  // -------------------------------------------------------------------------
  describe("boton Descargar PNG", () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    async function switchToPercentilesFull() {
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: "Curvas de percentiles" }));
      });
    }

    it("no aparece en vista longitudinal (default)", () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      expect(screen.queryByTestId("export-png-button")).not.toBeInTheDocument();
    });

    it("no aparece en vista percentiles cuando no hay registros con sex/birthDate", () => {
      // Sin sex ni birthDate no se muestra la tab "Curvas de percentiles"
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.queryByTestId("export-png-button")).not.toBeInTheDocument();
    });

    it("aparece en vista percentiles con registros y sex/birthDate provistos", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentilesFull();

      expect(screen.getByTestId("export-png-button")).toBeInTheDocument();
      expect(screen.getByTestId("export-png-button")).toHaveTextContent("Descargar PNG");
    });

    it("el boton esta habilitado cuando hay registros en vista percentiles", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentilesFull();

      expect(screen.getByTestId("export-png-button")).not.toBeDisabled();
    });

    it("al hacer click llama a toPng de html-to-image", async () => {
      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentilesFull();

      // Mock de document.createElement para interceptar el link de descarga
      const createElementSpy = vi.spyOn(document, "createElement");
      const mockLink = { href: "", download: "", click: vi.fn() };
      createElementSpy.mockImplementation((tag: string) => {
        if (tag === "a") return mockLink as unknown as HTMLElement;
        return document.createElement.call(document, tag) as HTMLElement;
      });

      await act(async () => {
        await userEvent.click(screen.getByTestId("export-png-button"));
      });

      expect(mockToPng).toHaveBeenCalledOnce();
      expect(mockLink.click).toHaveBeenCalledOnce();
      expect(mockLink.download).toMatch(/^crecimiento-height_for_age-\d+\.png$/);

      createElementSpy.mockRestore();
    });

    it("no aparece cuando records=[] aun con sex/birthDate provistos", async () => {
      render(
        <GrowthCharts records={[]} sex="M" birthDate="2015-06-01" />,
      );
      // Vista longitudinal: muestra mensaje de "se necesitan al menos 2".
      // Cambio a percentiles si la tab existe.
      const tab = screen.queryByRole("button", { name: "Curvas de percentiles" });
      if (tab) {
        await act(async () => {
          await userEvent.click(tab);
        });
      }
      // Sin records el boton no debe estar presente.
      expect(screen.queryByTestId("export-png-button")).not.toBeInTheDocument();
    });

    it("durante export muestra estado 'Exportando...' y boton disabled", async () => {
      // Hacemos que toPng quede pendiente para inspeccionar el estado intermedio.
      let resolveToPng!: (value: string) => void;
      mockToPng.mockImplementationOnce(
        () => new Promise<string>((resolve) => {
          resolveToPng = resolve;
        }),
      );

      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentilesFull();

      const btn = screen.getByTestId("export-png-button");
      // Disparar click sin esperar la resolucion
      void userEvent.click(btn);

      // Esperar a que React aplique el setState de isExporting=true
      await screen.findByText(/Exportando/i);
      expect(screen.getByTestId("export-png-button")).toBeDisabled();

      // Resolver el toPng para limpiar
      await act(async () => {
        resolveToPng("data:image/png;base64,abc");
      });
    });

    it("error en toPng no crashea y restaura estado del boton", async () => {
      const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockToPng.mockRejectedValueOnce(new Error("export-fail"));

      render(
        <GrowthCharts
          records={[recordA, recordB]}
          sex="M"
          birthDate="2015-06-01"
        />,
      );
      await switchToPercentilesFull();

      await act(async () => {
        await userEvent.click(screen.getByTestId("export-png-button"));
      });

      // Boton vuelve a estar habilitado tras el error
      expect(screen.getByTestId("export-png-button")).not.toBeDisabled();
      expect(screen.getByTestId("export-png-button")).toHaveTextContent("Descargar PNG");
      // Error logeado
      expect(consoleErrorSpy).toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });
  });
});
