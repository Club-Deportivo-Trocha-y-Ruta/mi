/**
 * Tests vitest para DistributionChart (FE-3).
 *
 * Cubre:
 *  - Selects season + valida.
 *  - Render chart + reference line cuando hay curve.
 *  - Disclaimer + tabla simple si confidence==="low" (n<5).
 *  - Reference lines de extremos: display_name real (coach) o pseudónimo (parent).
 *  - Empty state cuando athlete_time_ms===null.
 *  - Loading/error.
 *  - [T009] Estados amigables no-data y error: sin texto de excepción crudo.
 *  - [T009] a11y axe en estados no-data y error.
 *  - [T009/US1 TDD-red] prop defaultEventId y query por event_id.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  AreaChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: unknown[];
  }) => (
    <div data-testid="area-chart" data-points={data.length}>
      {children}
    </div>
  ),
  Area: () => <div data-testid="recharts-area" />,
  // T032: capturamos stroke/strokeDasharray para poder afirmar que la
  // grilla es un hairline sólido — contracts/chart-style.md prohíbe
  // strokeDasharray en <CartesianGrid> (anti-patrón "grilla punteada").
  CartesianGrid: (props: { stroke?: string; strokeDasharray?: string }) => (
    <div
      data-testid="recharts-grid"
      data-stroke={props.stroke}
      data-stroke-dasharray={props.strokeDasharray ?? ""}
    />
  ),
  XAxis: ({ domain }: { domain?: unknown }) => (
    <div data-testid="recharts-x" data-domain={JSON.stringify(domain)} />
  ),
  YAxis: () => <div data-testid="recharts-y" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ReferenceLine: ({ label }: { label?: { value?: string } }) => (
    <div
      data-testid="recharts-ref-line"
      data-label={typeof label === "object" ? label?.value : undefined}
    />
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="recharts-line" />,
}));

import { mswServer } from "@/test/setup";
import {
  coachHighConfidenceDistributionHandler,
  emptyRacesListHandler,
  errorRacesListHandler,
  lowConfidenceDistributionHandler,
  mockDistribution,
  racesListHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import {
  SEASON_AGGREGATE,
  aggregateLabel,
  raceOptionValue,
} from "@/lib/raceOptionLabel";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { DistributionChart } from "@/components/athletes/ai/DistributionChart";

describe("DistributionChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza selectores de season y válida", async () => {
    mswServer.use(racesListHandler);
    renderWithProviders(<DistributionChart athleteId={42} />);
    expect(screen.getByTestId("distribution-season-select")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("distribution-valida-select")).toBeInTheDocument();
    });
  });

  it("renderiza chart + reference lines con confidence high (curve presente)", async () => {
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    // Hay al menos 1 reference line ("Tú" + extremos min/max)
    expect(screen.getAllByTestId("recharts-ref-line").length).toBeGreaterThanOrEqual(1);
    // Stats summary muestra Media, Desv, etc.
    expect(screen.getByText(/media/i)).toBeInTheDocument();
    expect(screen.getByText(/desv/i)).toBeInTheDocument();
  });

  it("muestra tabla simple y disclaimer cuando confidence==='low'", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/muestra insuficiente.*n<5/i),
    ).toBeInTheDocument();
    // Tabla con pseudónimos
    expect(screen.getAllByText(/C000\d/).length).toBeGreaterThan(0);
    // El chart NO se renderiza en este caso
    expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
  });

  it("empty state cuando el deportista no corrió la válida", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        () =>
          HttpResponse.json(
            mockDistribution({
              athlete_time_ms: null,
              athlete_z_score: null,
              athlete_percentile: null,
            }),
          ),
      ),
    );
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(
        screen.getByText(/el deportista no corrió esta válida/i),
      ).toBeInTheDocument();
    });
  });

  it("muestra error cuando la query falla (T039: ErrorState con Reintentar)", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(
        screen.getByText(/no pudimos cargar la distribución/i),
      ).toBeInTheDocument();
    });
    // ErrorState compartido (T039) — antes era un párrafo rojo sin acción.
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reintentar/i }),
    ).toBeInTheDocument();
  });

  it("Reintentar en el error de distribución vuelve a pedir la distribución (T039)", async () => {
    let calls = 0;
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/distribution", () => {
        calls += 1;
        return new HttpResponse(null, { status: 500 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <DistributionChart athleteId={42} defaultEventId={100} />,
    );

    await screen.findByText(/no pudimos cargar la distribución/i);
    expect(calls).toBe(1);

    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    await waitFor(() => expect(calls).toBe(2));
  });

  it("un fallo de red (forma cold-start) en la distribución muestra la copy calmada (T039)", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/distribution", () =>
        HttpResponse.error(),
      ),
    );
    renderWithProviders(
      <DistributionChart athleteId={42} defaultEventId={100} />,
    );

    const coldStartMessage = await screen.findByText(
      /la aplicación está iniciando/i,
    );
    expect(coldStartMessage).toBeInTheDocument();
    expect(
      screen.queryByText(/no pudimos cargar la distribución/i),
    ).not.toBeInTheDocument();
    // ErrorState en variante cold-start usa role="status" (tono calmado,
    // no de error) — se verifica en el contenedor específico del mensaje,
    // no con getByRole("status") a secas: el picker de carreras de este
    // componente puede tener su propio spinner "Cargando carreras" con el
    // mismo role simultáneamente (query /races sin handler en este test).
    expect(coldStartMessage.closest('[role="status"]')).not.toBeNull();
  });

  it("con defaultEventId la query envía event_id (no valida_num) al backend", async () => {
    const calls: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        ({ request }) => {
          const url = new URL(request.url);
          calls.push(url.search);
          return HttpResponse.json(mockDistribution());
        },
      ),
    );
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => expect(screen.getByTestId("area-chart")).toBeInTheDocument());

    // La query debe usar event_id, nunca valida_num
    expect(calls.some((s) => s.includes("event_id=100"))).toBe(true);
    expect(calls.some((s) => s.includes("valida_num"))).toBe(false);
  });

  it("destaca al atleta en la tabla low-confidence con is_self=true", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByText(/C0002/)).toBeInTheDocument();
    });
    // El row con is_self=true debería mostrar "Tú"
    expect(screen.getByText(/· tú/i)).toBeInTheDocument();
  });

  it("no tiene violaciones a11y (high confidence)", async () => {
    const { container } = renderWithProviders(
      <DistributionChart athleteId={42} defaultEventId={100} />,
    );
    await waitFor(() => expect(screen.getByTestId("area-chart")).toBeInTheDocument());
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (low confidence / tabla)", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    const { container } = renderWithProviders(
      <DistributionChart athleteId={42} defaultEventId={100} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("reference lines muestran TODAS las corredoras con display_name (coach)", async () => {
    mswServer.use(coachHighConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const refLines = screen.getAllByTestId("recharts-ref-line");
    const labels = refLines.map((el) => el.getAttribute("data-label")).filter(Boolean);
    // Labels usan SOLO el primer nombre (display compacto).
    // self ("Diego Gómez") NO debe estar — usa la línea "Tú" separada.
    expect(labels).toContain("Luciana");   // mejor
    expect(labels).toContain("Sofía");     // peor
    expect(labels).toContain("Carlos");    // intermedia
    expect(labels).toContain("Andrés");
    expect(labels).toContain("Valentina");
    expect(labels).toContain("Mateo");
    expect(labels).toContain("Isabela");
    // Diego es self → no aparece en RiderReferenceLines (aparece como "P67 · Tú")
    expect(labels).not.toContain("Diego");
  });

  it("reference lines muestran TODOS los pseudónimos cuando display_name es null (parent)", async () => {
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const refLines = screen.getAllByTestId("recharts-ref-line");
    const labels = refLines.map((el) => el.getAttribute("data-label")).filter(Boolean);
    // Todos los no-self deben tener su pseudónimo. self=C0003 → no aparece aquí.
    expect(labels).toContain("C0001");
    expect(labels).toContain("C0002");
    expect(labels).toContain("C0004");
    expect(labels).toContain("C0005");
    expect(labels).toContain("C0006");
    expect(labels).toContain("C0007");
    expect(labels).toContain("C0008");
    expect(labels).not.toContain("C0003"); // self → fuera
    // No debe haber ningún nombre real
    expect(labels.some((l) => /[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+/.test(l ?? ""))).toBe(false);
  });

  it("el XAxis recibe un dominio más amplio que el rango raw de la curva (padding 8%)", async () => {
    // mockDistribution default: curve xs = [1_700_000, 1_800_000, 1_900_000, 2_000_000, 2_100_000]
    // rango raw = 400_000 ms → pad = 32_000 ms (8%)
    // domain esperado = [1_668_000, 2_132_000]
    renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const xAxisEl = screen.getByTestId("recharts-x");
    const raw = xAxisEl.getAttribute("data-domain");
    expect(raw).not.toBeNull();
    const domain = JSON.parse(raw!) as [number, number];
    // El dominio debe ser un array de dos números
    expect(Array.isArray(domain)).toBe(true);
    expect(domain).toHaveLength(2);
    const [lo, hi] = domain;
    // El extremo izquierdo debe ser menor que el mínimo de la curva (1_700_000)
    expect(lo).toBeLessThan(1_700_000);
    // El extremo derecho debe ser mayor que el máximo de la curva (2_100_000)
    expect(hi).toBeGreaterThan(2_100_000);
    // El padding debe ser al menos 1 s (1_000 ms) a cada lado
    expect(1_700_000 - lo).toBeGreaterThanOrEqual(1_000);
    expect(hi - 2_100_000).toBeGreaterThanOrEqual(1_000);
  });

  // ---------------------------------------------------------------------------
  // T009 — Estados amigables: no-data y error sin texto crudo de excepción
  // ---------------------------------------------------------------------------

  describe("T009 — estado no-data amigable (athlete_time_ms=null, curve=[], confidence=low)", () => {
    it("muestra mensaje amigable en español neutro sin texto de excepción crudo", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () =>
            HttpResponse.json(
              mockDistribution({
                athlete_time_ms: null,
                athlete_z_score: null,
                athlete_percentile: null,
                curve: [],
                confidence: "low",
                mean_ms: null,
                stddev_ms: null,
                sample_size: 0,
                points: [],
                category_id: 3,
              }),
            ),
        ),
      );
      renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);

      // Espera a que desaparezca el skeleton y aparezca el mensaje
      await waitFor(() => {
        expect(
          screen.getByText(/el deportista no corrió esta válida/i),
        ).toBeInTheDocument();
      });

      // No debe haber texto de stack/excepción crudo
      const container = screen.getByTestId("distribution-chart");
      const text = container.textContent ?? "";
      expect(text).not.toMatch(/Error:/i);
      expect(text).not.toMatch(/TypeError/i);
      expect(text).not.toMatch(/undefined/i);
      expect(text).not.toMatch(/null/i);
      expect(text).not.toMatch(/at\s+\w+\s+\(/); // stack trace lines

      // No se renderiza ningún chart
      expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
    });

    it("no tiene violaciones a11y en el estado no-data (axe)", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () =>
            HttpResponse.json(
              mockDistribution({
                athlete_time_ms: null,
                athlete_z_score: null,
                athlete_percentile: null,
                curve: [],
                confidence: "low",
                mean_ms: null,
                stddev_ms: null,
                sample_size: 0,
                points: [],
                category_id: 3,
              }),
            ),
        ),
      );
      const { container } = renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
      await waitFor(() => {
        expect(
          screen.getByText(/el deportista no corrió esta válida/i),
        ).toBeInTheDocument();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  describe("T009 — estado error amigable (sin texto de excepción crudo)", () => {
    it("muestra role=alert con mensaje amigable y SIN texto crudo de excepción", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () => new HttpResponse(null, { status: 500 }),
        ),
      );
      renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });

      const alert = screen.getByRole("alert");

      // El mensaje amigable debe estar presente
      expect(alert).toHaveTextContent(/no pudimos cargar la distribución/i);

      // Sin texto de stack/excepción crudo en todo el componente
      const fullText = screen.getByTestId("distribution-chart").textContent ?? "";
      expect(fullText).not.toMatch(/Error:/i);
      expect(fullText).not.toMatch(/TypeError/i);
      expect(fullText).not.toMatch(/500/);
      expect(fullText).not.toMatch(/Internal Server Error/i);
      expect(fullText).not.toMatch(/at\s+\w+\s+\(/); // stack trace lines
    });

    it("no tiene violaciones a11y en el estado de error (axe)", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () => new HttpResponse(null, { status: 500 }),
        ),
      );
      const { container } = renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);
      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // ---------------------------------------------------------------------------
  // T009/US1 TDD-red — prop defaultEventId y query por event_id
  // Los tests de esta sección deben FALLAR hasta que se implemente US1:
  //   1. DistributionChart acepta prop `defaultEventId?: number`
  //   2. useAthleteDistribution pasa event_id al backend en lugar de valida_num
  //   3. DistributionResponse incluye campo `event_id`
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // T017 — race picker (US2): TDD-red hasta que T021/T022 implementen el picker
  // ---------------------------------------------------------------------------

  describe("T017 — race picker (US2)", () => {
    /**
     * T017-1: El picker lista cada carrera del backend UNA VEZ con su label
     * del servidor y prepend "Temporada (todas)".
     *
     * TDD-red: el picker actual es un placeholder que no consulta
     * /race-analysis/races ni renderiza las opciones del backend.
     */
    it("lista cada carrera del backend con su label y prepende 'Temporada (todas)'", async () => {
      mswServer.use(racesListHandler);
      renderWithProviders(<DistributionChart athleteId={42} />);

      await waitFor(() => {
        // La opción agregada SIEMPRE debe estar presente
        expect(
          screen.getByRole("option", { name: aggregateLabel() }),
        ).toBeInTheDocument();
      });

      // Cada carrera del backend aparece exactamente una vez con su label
      const opt1 = screen.getByRole("option", { name: "Válida I — Sevilla" });
      const opt2 = screen.getByRole("option", { name: "Cto. Dep. — Ginebra" });
      expect(opt1).toBeInTheDocument();
      expect(opt2).toBeInTheDocument();

      // Los valores de las opciones corresponden a sus event_id
      expect(opt1).toHaveValue(raceOptionValue(91));
      expect(opt2).toHaveValue(raceOptionValue(200));

      // La opción del campeonato es reconocible por su label (no por valida_num)
      expect(opt2.textContent).toMatch(/Cto\. Dep\./);
    });

    /**
     * T017-2: Seleccionar "Temporada (todas)" muestra mensaje informativo
     * y NO dispara una petición /distribution.
     *
     * TDD-red: el componente actual no tiene este flujo — T022 lo implementará.
     *
     * Feature 036/T035: con carreras disponibles y sin `defaultEventId` el
     * montaje YA autoselecciona la más reciente (ver describe "T035" más
     * abajo), así que el propio mount dispara una petición /distribution.
     * Esperamos explícitamente a que esa petición inicial llegue ANTES de
     * limpiar `distributionCalls` — de lo contrario la limpieza puede
     * ejecutarse antes de que el efecto de autoselección + el fetch que
     * habilita terminen de propagarse, y el conteo post-selección queda
     * contaminado por una carrera de datos (flaky, no por un fetch real
     * disparado por la selección manual de "Temporada (todas)").
     */
    it("seleccionar 'Temporada (todas)' muestra mensaje informativo y no dispara /distribution", async () => {
      const distributionCalls: string[] = [];
      mswServer.use(
        racesListHandler,
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          ({ request }) => {
            distributionCalls.push(request.url);
            return HttpResponse.json(mockDistribution());
          },
        ),
      );

      renderWithProviders(<DistributionChart athleteId={42} />);

      // Espera a que el picker esté disponible
      await waitFor(() => {
        expect(
          screen.getByTestId("distribution-valida-select"),
        ).toBeInTheDocument();
      });

      // Espera a que termine el fetch inicial disparado por la
      // autoselección T035 antes de limpiar el contador (ver nota arriba).
      await waitFor(() => {
        expect(distributionCalls.length).toBeGreaterThan(0);
      });

      // Limpiar llamadas previas (el mount ya disparó su propia query T035)
      distributionCalls.length = 0;

      // Seleccionar "Temporada (todas)" via fireEvent
      const picker = screen.getByTestId("distribution-valida-select");
      fireEvent.change(picker, { target: { value: SEASON_AGGREGATE } });

      // El mensaje informativo debe aparecer y el chart no
      await waitFor(() => {
        expect(
          screen.getByText(/la distribución se calcula por carrera/i),
        ).toBeInTheDocument();
        expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
      });

      // NO debe haberse disparado ninguna petición /distribution tras la selección
      // (si el componente hubiera hecho fetch, ya habría llegado dentro del waitFor)
      expect(distributionCalls).toHaveLength(0);

      // El chart NO debe estar presente
      expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
    });

    /**
     * T017-3: Seleccionar una carrera real envía event_id correcto al backend
     * (round-trip: opción → event_id → query string).
     *
     * TDD-red: el picker actual no usa useAthleteRaces, ergo nunca pide
     * /distribution con el event_id de una carrera del backend.
     */
    it("seleccionar una carrera envía event_id correcto en la query /distribution", async () => {
      const distributionCalls: string[] = [];
      mswServer.use(
        racesListHandler,
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          ({ request }) => {
            distributionCalls.push(new URL(request.url).search);
            return HttpResponse.json(mockDistribution({ event_id: 91 }));
          },
        ),
      );

      renderWithProviders(<DistributionChart athleteId={42} />);

      // Esperar a que el picker esté en el DOM
      await waitFor(() => {
        expect(
          screen.getByTestId("distribution-valida-select"),
        ).toBeInTheDocument();
      });

      // Seleccionar la Válida I (event_id=91) via fireEvent
      const picker = screen.getByTestId("distribution-valida-select");
      fireEvent.change(picker, { target: { value: raceOptionValue(91) } });

      // La query de distribución debe haberse disparado con event_id=91
      await waitFor(() => {
        expect(
          distributionCalls.some((s) => s.includes("event_id=91")),
          "Se esperaba una petición /distribution con event_id=91",
        ).toBe(true);
      });

      // No debe haber enviado valida_num
      expect(distributionCalls.some((s) => s.includes("valida_num"))).toBe(false);
    });

    /**
     * T017-4: Con cero carreras el picker muestra SOLO "Temporada (todas)"
     * y un estado vacío amigable. No debe haber error.
     *
     * TDD-red: el componente actual no consulta /race-analysis/races.
     */
    it("cero carreras → picker solo muestra 'Temporada (todas)' + estado vacío amigable", async () => {
      mswServer.use(emptyRacesListHandler);
      renderWithProviders(<DistributionChart athleteId={42} />);

      await waitFor(() => {
        // La opción "Temporada (todas)" debe estar presente
        expect(
          screen.getByRole("option", { name: aggregateLabel() }),
        ).toBeInTheDocument();
      });

      // No debe haber ninguna otra opción de carrera
      const allOptions = screen.getAllByRole("option");
      const raceOptions = allOptions.filter(
        (opt) => opt.getAttribute("value") !== SEASON_AGGREGATE,
      );
      expect(raceOptions).toHaveLength(0);

      // Mensaje de estado vacío amigable
      expect(
        screen.getByText(/no hay carreras disponibles/i),
      ).toBeInTheDocument();

      // No debe haber mensajes de error
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    /**
     * Feature 036 (US5): un fallo al cargar /races NO debe caer en silencio
     * al placeholder "Selecciona una carrera" — eso le miente al coach
     * diciéndole que debe elegir, cuando en realidad la petición falló y el
     * selector no tiene nada para ofrecer. Debe mostrar el ErrorState
     * compartido con "Reintentar", igual que ya hace la query de distribución.
     */
    it("fallo al cargar /races → ErrorState con Reintentar, NUNCA el placeholder de selección", async () => {
      mswServer.use(errorRacesListHandler);
      renderWithProviders(<DistributionChart athleteId={42} />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/no pudimos cargar las carreras/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /reintentar/i }),
      ).toBeInTheDocument();

      // Nunca el placeholder que sugiere que basta con elegir una carrera.
      expect(
        screen.queryByText(/selecciona una carrera en el selector/i),
      ).not.toBeInTheDocument();
      // Tampoco el mensaje de "0 carreras" — esto no es una temporada vacía.
      expect(
        screen.queryByText(/no hay carreras disponibles/i),
      ).not.toBeInTheDocument();
    });

    /**
     * T017-5: axe — zero a11y violations con el picker poblado.
     *
     * Este test puede pasar en verde incluso antes de T022 si el picker
     * placeholder no introduce violaciones — es un guardia de regresión.
     */
    it("zero violaciones a11y con el picker poblado (axe)", async () => {
      mswServer.use(racesListHandler);
      const { container } = renderWithProviders(
        <DistributionChart athleteId={42} />,
      );

      // Espera a que el picker esté en el DOM (mínimo: options renderizadas)
      await waitFor(() => {
        expect(
          screen.getByTestId("distribution-valida-select"),
        ).toBeInTheDocument();
      });

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // ---------------------------------------------------------------------------
  // T035 (feature 036) — el selector abría en "Temporada (todas)", un valor
  // que solo produce el placeholder "selecciona una carrera": el sub-tab
  // abría vacío y el coach tenía que adivinar que debía cambiar el selector.
  // ---------------------------------------------------------------------------

  describe("T035 — selector por defecto en la carrera más reciente", () => {
    it("con carreras disponibles autoselecciona la más reciente (por event_date) y muestra datos", async () => {
      mswServer.use(racesListHandler);
      renderWithProviders(<DistributionChart athleteId={42} />);

      await waitFor(() => {
        expect(
          screen.getByTestId("distribution-valida-select"),
        ).toBeInTheDocument();
      });

      // racesListHandler: Válida I (2026-01-31, event_id=91) y Cto. Dep.
      // (2026-06-12, event_id=200) — el más reciente es el campeonato.
      await waitFor(() => {
        expect(screen.getByTestId("distribution-valida-select")).toHaveValue(
          raceOptionValue(200),
        );
      });

      // Con una carrera ya seleccionada se ve el chart de una vez — no el
      // placeholder "selecciona una carrera" (el bug que T035 corrige).
      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });
      expect(
        screen.queryByText(/la distribución se calcula por carrera/i),
      ).not.toBeInTheDocument();
    });

    it("con defaultEventId explícito NO autoselecciona — respeta la elección del caller", async () => {
      mswServer.use(racesListHandler);
      renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={91} />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });

      // Se mantiene en 91 (Válida I) aunque 200 (Cto. Dep.) sea más reciente.
      expect(screen.getByTestId("distribution-valida-select")).toHaveValue(
        raceOptionValue(91),
      );
    });

    it("con 0 carreras no falla: se queda en 'Temporada (todas)' (código defensivo)", async () => {
      mswServer.use(emptyRacesListHandler);
      renderWithProviders(<DistributionChart athleteId={42} />);

      await waitFor(() => {
        expect(
          screen.getByText(/no hay carreras disponibles/i),
        ).toBeInTheDocument();
      });
      expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("US1 TDD-red — defaultEventId prop y ruta por event_id", () => {
    it("acepta prop defaultEventId y la usa para hacer la primera query (TDD-red)", async () => {
      // Capturamos los params de la request
      const capturedParams: URLSearchParams[] = [];
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          ({ request }) => {
            capturedParams.push(new URL(request.url).searchParams);
            return HttpResponse.json(mockDistribution());
          },
        ),
      );

      // Renderizamos con defaultEventId=100 (evento específico, no válida genérica)
      renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);

      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });

      // La query DEBE incluir event_id=100, NO valida_num
      expect(
        capturedParams.some((p) => p.get("event_id") === "100"),
        "Se esperaba que la query enviara event_id=100 al backend",
      ).toBe(true);
    });

    it("cuando defaultEventId está presente NO envía valida_num en la query (TDD-red)", async () => {
      const capturedParams: URLSearchParams[] = [];
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          ({ request }) => {
            capturedParams.push(new URL(request.url).searchParams);
            return HttpResponse.json(mockDistribution());
          },
        ),
      );

      renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);

      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });

      // valida_num NO debe estar presente cuando se usa event_id
      expect(
        capturedParams.some((p) => p.has("valida_num")),
        "No se debe enviar valida_num cuando defaultEventId está presente",
      ).toBe(false);
    });

    it("el payload de respuesta incluye event_id cuando el backend lo devuelve", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () =>
            HttpResponse.json({
              ...mockDistribution(),
              event_id: 100,
            }),
        ),
      );

      renderWithProviders(<DistributionChart athleteId={42} defaultEventId={100} />);

      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });

      // El componente NO debe mostrar texto 500/excepción aunque haya campo extra
      const text = screen.getByTestId("distribution-chart").textContent ?? "";
      expect(text).not.toMatch(/Error:/i);
      expect(text).not.toMatch(/TypeError/i);

      // Verificamos que el campo event_id del payload esté accesible
      // (el componente lo debería exponer, p.e., en un data-event-id o similar).
      const section = screen.getByTestId("distribution-chart");
      expect(section.getAttribute("data-event-id")).toBe("100");
    });
  });

  // ---------------------------------------------------------------------------
  // T032 — chart regression contract (contracts/chart-style.md): grid is a
  // solid hairline (no dashing), rider reference-line labels cap at n>8,
  // and the n<5 low-confidence fallback keeps rendering unchanged (no
  // toggle ever coexists with it).
  // ---------------------------------------------------------------------------

  describe("T032 — chart regression contract", () => {
    it("CartesianGrid nunca recibe strokeDasharray (grilla hairline sólida, sin punteado)", async () => {
      renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={100} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("area-chart")).toBeInTheDocument(),
      );
      const grid = screen.getByTestId("recharts-grid");
      expect(grid.getAttribute("data-stroke-dasharray")).toBe("");
    });

    it("con points.length<=8 todas las reference lines de rivales conservan su label visible", async () => {
      mswServer.use(coachHighConfidenceDistributionHandler); // 8 puntos totales (self incl.)
      renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={100} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("area-chart")).toBeInTheDocument(),
      );
      const refLines = screen.getAllByTestId("recharts-ref-line");
      // self "Tú" (1) + 7 rivales (self excluido de RiderReferenceLines) = 8.
      expect(refLines).toHaveLength(8);
      const withLabel = refLines.filter((el) => el.getAttribute("data-label"));
      expect(withLabel).toHaveLength(refLines.length);
    });

    it("con points.length>8 solo self/mejor/peor conservan label — el resto sigue renderizando su ReferenceLine (posición preservada) sin texto", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/distribution",
          () =>
            HttpResponse.json(
              mockDistribution({
                sample_size: 9,
                points: [
                  { pseudonym: "C0001", time_ms: 1_700_000, is_self: false }, // mejor
                  { pseudonym: "C0002", time_ms: 1_720_000, is_self: false },
                  { pseudonym: "C0003", time_ms: 1_740_000, is_self: false },
                  { pseudonym: "C0004", time_ms: 1_760_000, is_self: false },
                  { pseudonym: "C0005", time_ms: 1_780_000, is_self: true }, // self
                  { pseudonym: "C0006", time_ms: 1_800_000, is_self: false },
                  { pseudonym: "C0007", time_ms: 1_820_000, is_self: false },
                  { pseudonym: "C0008", time_ms: 1_840_000, is_self: false },
                  { pseudonym: "C0009", time_ms: 1_860_000, is_self: false }, // peor
                ],
              }),
            ),
        ),
      );
      renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={100} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("area-chart")).toBeInTheDocument(),
      );
      const refLines = screen.getAllByTestId("recharts-ref-line");
      // self "Tú" (1) + 8 rivales (self excluido) = 9 ReferenceLine — todas
      // siguen renderizando (posición preservada), solo el label cambia.
      expect(refLines).toHaveLength(9);
      const withLabel = refLines.filter((el) => el.getAttribute("data-label"));
      // Solo self("Tú") + mejor(C0001) + peor(C0009) conservan label visible.
      expect(withLabel).toHaveLength(3);
    });

    it("el fallback n<5 (low confidence) se renderiza sin cambios: tabla simple + disclaimer, jamás junto al toggle Gráfica/Tabla", async () => {
      mswServer.use(lowConfidenceDistributionHandler);
      renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={100} />,
      );
      await waitFor(() => {
        expect(screen.getByRole("note")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/muestra insuficiente.*n<5/i),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
      // El toggle Gráfica/Tabla (T028) NUNCA coexiste con el fallback n<5.
      expect(
        screen.queryByTestId("distribution-view-chart"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("distribution-view-table"),
      ).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // T033 — el twin de tabla debe ser el equivalente WCAG-limpio de la
  // gráfica por sí mismo (no solo "también presente"): axe corre sobre el
  // contenedor cuando la vista "Tabla" está activa y es la única vista
  // montada (Radix Tabs desmonta el panel inactivo).
  // ---------------------------------------------------------------------------

  describe("T033 — table-view twin es WCAG-limpio por sí mismo (axe)", () => {
    it("la vista Tabla activa no tiene violaciones a11y y reemplaza por completo a la gráfica en el DOM", async () => {
      const user = userEvent.setup();
      const { container } = renderWithProviders(
        <DistributionChart athleteId={42} defaultEventId={100} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("area-chart")).toBeInTheDocument(),
      );

      await user.click(screen.getByTestId("distribution-view-table"));

      await waitFor(() => {
        expect(screen.getByRole("table")).toBeInTheDocument();
        expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
      });

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
