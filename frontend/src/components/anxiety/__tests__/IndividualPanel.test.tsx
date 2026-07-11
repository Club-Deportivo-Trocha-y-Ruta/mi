/**
 * Tests para IndividualPanel (US5): puntajes + línea base, nota de
 * no-comparabilidad, flags, y gráfico de evolución (Recharts, lazy) montado.
 * También cubre AnalyzeButton + InterpretationPanel (US4) integrados:
 * estados idle/pending/success(llm|rule)/error, y a11y en ambos estados.
 *
 * Recharts se mockea (igual que el resto del proyecto) para que
 * ResponsiveContainer renderice con tamaño fijo en jsdom.
 *
 * interpretAssessment (API real haría HTTP) se mockea; mapAnxietyError se
 * mantiene con su implementación real vía vi.importActual para que el copy
 * de error mostrado en pantalla sea el mismo que en producción.
 */
import { describe, it, expect, vi } from "vitest";
import { screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { IndividualPanel } from "../IndividualPanel";
import { interpretAssessment } from "@/api/anxiety";
import type { AthleteSeries, InterpretationResponse } from "@/types/anxiety.types";

expect.extend(toHaveNoViolations);

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 600, height: 200 }}>
        {children}
      </div>
    ),
    LineChart: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="line-chart">{children}</div>
    ),
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    ReferenceLine: () => null,
  };
});

vi.mock("@/api/anxiety", async () => {
  const actual = await vi.importActual<typeof import("@/api/anxiety")>("@/api/anxiety");
  return { ...actual, interpretAssessment: vi.fn() };
});

const SERIES: AthleteSeries = {
  athlete_id: 100,
  instrument_type: "csai2r",
  baseline_cognitive: 20,
  baseline_somatic: 22,
  baseline_selfconfidence: 30,
  note: null,
  points: [
    {
      assessment_id: 1,
      scheduled_at: "2026-04-19T12:00:00Z",
      event_id: null,
      cognitive: 20,
      somatic: 22,
      selfconfidence: 30,
      flags: [],
    },
    {
      assessment_id: 2,
      scheduled_at: "2026-05-17T12:00:00Z",
      event_id: 5,
      cognitive: 30,
      somatic: 28,
      selfconfidence: 18,
      flags: ["Atención: conversación individual."],
    },
  ],
};

const INTERPRETATION_RESPONSE: InterpretationResponse = {
  assessment_id: 2,
  interpretation: {
    resumen: "El atleta muestra un nivel de ansiedad cognitiva moderado.",
    por_dimension: {
      cognitiva: "Preocupación moderada antes de la competencia.",
      somatica: "Activación física dentro de lo esperado.",
      autoconfianza: "Confianza en descenso respecto a la línea base.",
    },
    estrategias: [
      "Practicar respiración diafragmática antes de la salida.",
      "Reforzar rutina de calentamiento mental.",
    ],
    mensaje_para_el_atleta:
      "Es normal sentir nervios antes de competir; enfócate en tu proceso, no en el resultado.",
    banderas: [],
  },
  source: "llm",
  model: "claude-sonnet-5",
};

describe("IndividualPanel", () => {
  it("muestra puntajes del último punto y la línea base", () => {
    renderWithProviders(<IndividualPanel series={SERIES} />);
    // Fila "Cognitiva": último = 30, línea base = 20.
    const row = screen.getByText("Cognitiva").closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText("30")).toBeInTheDocument();
    expect(cells.getByText("20")).toBeInTheDocument();
  });

  it("renderiza las flags del último punto", () => {
    renderWithProviders(<IndividualPanel series={SERIES} />);
    expect(
      screen.getByText("Atención: conversación individual."),
    ).toBeInTheDocument();
  });

  it("monta el gráfico de evolución (Recharts) lazy-loaded", async () => {
    renderWithProviders(<IndividualPanel series={SERIES} />);
    expect(
      await screen.findByLabelText(
        "Gráfico de evolución de subescalas de ansiedad",
      ),
    ).toBeInTheDocument();
  });

  it("muestra la nota de no-comparabilidad cuando está presente", () => {
    renderWithProviders(
      <IndividualPanel series={{ ...SERIES, note: "Instrumentos distintos." }} />,
    );
    expect(screen.getByText("Instrumentos distintos.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderWithProviders(<IndividualPanel series={SERIES} />);
    // Espera a que el chart lazy se monte antes de auditar.
    await screen.findByLabelText(
      "Gráfico de evolución de subescalas de ansiedad",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  describe("AnalyzeButton (US4)", () => {
    it("se renderiza cuando el último punto tiene cognitive !== null", () => {
      renderWithProviders(<IndividualPanel series={SERIES} />);
      expect(
        screen.getByRole("button", { name: /Analizar con IA/i }),
      ).toBeInTheDocument();
    });

    it("no se renderiza cuando series.points está vacío", () => {
      renderWithProviders(<IndividualPanel series={{ ...SERIES, points: [] }} />);
      expect(
        screen.queryByRole("button", { name: /Analizar con IA/i }),
      ).not.toBeInTheDocument();
    });

    it("no se renderiza cuando el cognitive del último punto es null", () => {
      const seriesNullCognitive: AthleteSeries = {
        ...SERIES,
        points: [
          SERIES.points[0],
          { ...SERIES.points[1], cognitive: null },
        ],
      };
      renderWithProviders(<IndividualPanel series={seriesNullCognitive} />);
      expect(
        screen.queryByRole("button", { name: /Analizar con IA/i }),
      ).not.toBeInTheDocument();
    });

    it("muestra el estado de carga (botón deshabilitado, copy de cold-start) mientras se resuelve la promesa", async () => {
      const user = userEvent.setup();
      let resolveFn: (value: InterpretationResponse) => void = () => {};
      vi.mocked(interpretAssessment).mockImplementation(
        () =>
          new Promise<InterpretationResponse>((res) => {
            resolveFn = res;
          }),
      );

      renderWithProviders(<IndividualPanel series={SERIES} />);
      const button = screen.getByRole("button", { name: /Analizar con IA/i });
      await user.click(button);

      const pendingButton = await screen.findByRole("button", {
        name: /Analizando… \(puede tardar\)/i,
      });
      expect(pendingButton).toBeDisabled();
      expect(screen.getByText(/puede tardar ~50 s/i)).toBeInTheDocument();

      resolveFn(INTERPRETATION_RESPONSE);

      await waitFor(() => {
        expect(
          screen.queryByRole("button", { name: /Analizando… \(puede tardar\)/i }),
        ).not.toBeInTheDocument();
      });
    });

    it("renderiza InterpretationPanel con badge IA tras una interpretación exitosa (source=llm)", async () => {
      const user = userEvent.setup();
      vi.mocked(interpretAssessment).mockResolvedValueOnce(INTERPRETATION_RESPONSE);

      renderWithProviders(<IndividualPanel series={SERIES} />);
      await user.click(screen.getByRole("button", { name: /Analizar con IA/i }));

      expect(
        await screen.findByText(INTERPRETATION_RESPONSE.interpretation.resumen),
      ).toBeInTheDocument();
      expect(screen.getByText("IA")).toBeInTheDocument();
      expect(
        screen.getByText(INTERPRETATION_RESPONSE.interpretation.mensaje_para_el_atleta),
      ).toBeInTheDocument();
      const estrategiasHeading = screen.getByText("Estrategias");
      const estrategiasList = estrategiasHeading.parentElement as HTMLElement;
      expect(within(estrategiasList).getAllByRole("listitem").length).toBeGreaterThan(0);
    });

    it("renderiza InterpretationPanel con badge Reglas tras una interpretación exitosa (source=rule)", async () => {
      const user = userEvent.setup();
      const ruleResponse: InterpretationResponse = {
        ...INTERPRETATION_RESPONSE,
        source: "rule",
        model: null,
      };
      vi.mocked(interpretAssessment).mockResolvedValueOnce(ruleResponse);

      renderWithProviders(<IndividualPanel series={SERIES} />);
      await user.click(screen.getByRole("button", { name: /Analizar con IA/i }));

      const badge = await screen.findByText("Reglas");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveAttribute("title", "Generada por reglas (respaldo)");
      // El único role="alert" presente es el de las flags del punto (no un error
      // de AnalyzeButton): no debe existir el mensaje de error rojo.
      expect(screen.queryByText(/Ocurrió un error inesperado/i)).not.toBeInTheDocument();
      const alerts = screen.getAllByRole("alert");
      for (const el of alerts) {
        expect(el).not.toHaveClass("text-red-600");
      }
    });

    it("muestra el copy de consentimiento faltante cuando la interpretación falla con 409", async () => {
      const user = userEvent.setup();
      vi.mocked(interpretAssessment).mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 409 },
      });

      renderWithProviders(<IndividualPanel series={SERIES} />);
      await user.click(screen.getByRole("button", { name: /Analizar con IA/i }));

      const errorText =
        "Falta el consentimiento de la familia para la evaluación psicológica. " +
        "Solicítalo antes de crear la evaluación.";
      const alert = await screen.findByText(errorText);
      expect(alert).toHaveAttribute("role", "alert");
    });

    it("no tiene violaciones de accesibilidad con AnalyzeButton e InterpretationPanel montados", async () => {
      const user = userEvent.setup();
      vi.mocked(interpretAssessment).mockResolvedValueOnce(INTERPRETATION_RESPONSE);

      const { container } = renderWithProviders(<IndividualPanel series={SERIES} />);
      await screen.findByLabelText(
        "Gráfico de evolución de subescalas de ansiedad",
      );
      await user.click(screen.getByRole("button", { name: /Analizar con IA/i }));
      await screen.findByText(INTERPRETATION_RESPONSE.interpretation.resumen);

      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
