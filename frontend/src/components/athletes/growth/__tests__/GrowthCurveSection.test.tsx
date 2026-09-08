/**
 * Tests — GrowthCurveSection (feature 040, T047/US3).
 *
 * `GrowthCurveSection` compone `PercentileToolbar` + `PercentileChart`/
 * `PercentileTable` + `PercentileInterpretationBlock`, y es dueño de todo el
 * estado de la curva (`indicator`/`axis`/`range`/`detail`/`view`) y de la
 * exportación a PNG (`html-to-image`) — per las props exactas de la
 * orquestación de la ola 5: `{ athlete, records, mode }` (sin recibir
 * indicador/eje desde `GrowthTab`).
 *
 * Se mockean los cuatro hijos para aislar la lógica propia del contenedor
 * (filtrado de indicadores por edad, gating del eje, toggle de vista,
 * disparo de exportación) de la implementación interna de cada hijo, que se
 * prueba por separado en sus propios archivos. Este es el mismo criterio de
 * aislamiento que ya usa el resto de `GrowthTab.test.tsx` para sus secciones.
 *
 * El toggle de eje cronológico/biológico reutiliza el gating por rol de la
 * antigua `PercentileCurves.tsx` (`useAuthStore`, coach/admin únicamente),
 * combinado con `mode === "coach"` y `phvAgeMonths` definido — por eso los
 * tests de esa sección fijan el rol con `useAuthStore.setState`, igual que
 * `PercentileCurves.characterization.test.tsx`.
 *
 * Datos: sintéticos, sin nombres ni fechas de nacimiento reales de menores.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MaturationStatus, Sex, UserRole } from "@/types/enums";
import { useAuthStore } from "@/store/auth.store";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { MeResponse } from "@/types/auth.types";
import type { GrowthIndicator } from "@/lib/growth/lms";

// ---------------------------------------------------------------------------
// Mocks de los hijos — capturan las props recibidas en `captured` para poder
// hacer aserciones sobre la lógica de estado del contenedor.
// ---------------------------------------------------------------------------

const captured = vi.hoisted(() => ({
  toolbar: null as null | {
    indicators: { key: GrowthIndicator; label: string }[];
    indicator: GrowthIndicator;
    axis: "chrono" | "bio";
    showAxisToggle: boolean;
    range: "window" | "full";
    detail: boolean;
    view: "chart" | "table";
    exporting?: boolean;
    onIndicator: (key: GrowthIndicator) => void;
    onAxis: (axis: "chrono" | "bio") => void;
    onView: (view: "chart" | "table") => void;
    onExport?: () => void;
  },
  chart: null as null | {
    indicator: GrowthIndicator;
    records: { id: number }[];
    phvAgeMonths?: number;
    preset?: "coach" | "family";
  },
  table: null as null | {
    preset?: "coach" | "family";
  },
}));

vi.mock("@/components/athletes/growth/PercentileToolbar", () => ({
  PercentileToolbar: (props: (typeof captured)["toolbar"]) => {
    captured.toolbar = props;
    return (
      <div data-testid="mock-toolbar">
        <button type="button" onClick={() => props!.onIndicator("bmi_for_age")}>
          mock-set-bmi
        </button>
        <button type="button" onClick={() => props!.onAxis("bio")}>
          mock-set-bio
        </button>
        <button
          type="button"
          onClick={() => props!.onView(props!.view === "chart" ? "table" : "chart")}
        >
          mock-toggle-view
        </button>
        <button type="button" onClick={() => props!.onExport?.()}>
          mock-export
        </button>
      </div>
    );
  },
}));

vi.mock("@/components/athletes/growth/PercentileChart", () => ({
  PercentileChart: (props: (typeof captured)["chart"]) => {
    captured.chart = props;
    return <div data-testid="mock-chart" />;
  },
}));

vi.mock("@/components/athletes/growth/PercentileTable", () => ({
  PercentileTable: (props: (typeof captured)["table"]) => {
    captured.table = props;
    return <div data-testid="mock-table" />;
  },
}));

vi.mock("@/components/athletes/PercentileInterpretationBlock", () => ({
  PercentileInterpretationBlock: () => <div data-testid="mock-interpretation" />,
}));

// html-to-image se resuelve manualmente en cada test que lo necesita, para
// poder observar el estado `exporting` intermedio (promesa controlada).
const mockToPng = vi.fn();
vi.mock("html-to-image", () => ({ toPng: mockToPng }));

import { GrowthCurveSection } from "@/components/athletes/growth/GrowthCurveSection";

// ---------------------------------------------------------------------------
// Fixtures — sintéticas, sin datos reales de deportistas menores de edad.
// ---------------------------------------------------------------------------

function makeAthlete(overrides: Partial<AthleteDetailOut> = {}): AthleteDetailOut {
  return {
    id: 1,
    user_id: 10,
    first_name: "Atleta",
    last_name: "Ficticio",
    birth_date: "2013-09-01",
    sex: Sex.M,
    club_join_date: "2023-01-01",
    years_in_club: 2.3,
    age_decimal: 12.5,
    category: "Sub-15",
    club_id: 1,
    created_at: "2023-01-01T00:00:00Z",
    latest_anthropometry: null,
    ...overrides,
  };
}

function makeRecord(
  overrides: Partial<AnthropometricRecord> & { id: number },
): AnthropometricRecord {
  return {
    athlete_id: 1,
    evaluation_date: "2026-01-23",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 77.0,
    leg_sitting_ratio: 0.987,
    maturity_offset: -0.3,
    age_at_phv: 13.2,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-23T10:00:00",
    notes: null,
    height_z_score: 0.3,
    height_percentile: 62,
    bmi: 18.7,
    bmi_z_score: -0.2,
    bmi_percentile: 42,
    weight_z_score: 0.1,
    weight_percentile: 54,
    nutritional_status: "adecuado",
    ...overrides,
  };
}

const oneRecord = [makeRecord({ id: 1 })];

function makeUser(role: UserRole, overrides: Partial<MeResponse> = {}): MeResponse {
  return {
    id: 1,
    email: "prueba@example.com",
    first_name: "Persona",
    last_name: "Ficticia",
    phone: null,
    role,
    is_active: true,
    can_login: true,
    club_ids: [1],
    created_at: "2026-01-01T00:00:00",
    ...overrides,
  };
}

beforeEach(() => {
  captured.toolbar = null;
  captured.chart = null;
  captured.table = null;
  mockToPng.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false });
});

// ---------------------------------------------------------------------------
// 1. < 1 medición → no se renderiza la curva
// ---------------------------------------------------------------------------

describe("GrowthCurveSection — sin mediciones", () => {
  it("con records=[] no renderiza el toolbar ni la curva", () => {
    const { container } = render(
      <GrowthCurveSection athlete={makeAthlete()} records={[]} mode="coach" />,
    );
    expect(screen.queryByTestId("mock-toolbar")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});

// ---------------------------------------------------------------------------
// 2. Lista de indicadores filtrada por edad (no Peso > 10 años)
// ---------------------------------------------------------------------------

describe("GrowthCurveSection — lista de indicadores por edad", () => {
  it("con age_decimal > 10 no ofrece Peso", () => {
    render(
      <GrowthCurveSection
        athlete={makeAthlete({ age_decimal: 12.5 })}
        records={oneRecord}
        mode="coach"
      />,
    );
    const keys = captured.toolbar!.indicators.map((i) => i.key);
    expect(keys).not.toContain("weight_for_age");
    expect(keys).toContain("height_for_age");
    expect(keys).toContain("bmi_for_age");
  });

  it("con age_decimal <= 10 sí ofrece Peso", () => {
    render(
      <GrowthCurveSection
        athlete={makeAthlete({ age_decimal: 9.0 })}
        records={oneRecord}
        mode="coach"
      />,
    );
    const keys = captured.toolbar!.indicators.map((i) => i.key);
    expect(keys).toContain("weight_for_age");
  });
});

// ---------------------------------------------------------------------------
// 3. Gating del toggle de eje — solo coach, nunca en IMC
// ---------------------------------------------------------------------------

describe("GrowthCurveSection — gating del eje cronológico/biológico", () => {
  it("modo coach + rol coach + indicador inicial (talla) → showAxisToggle=true", () => {
    useAuthStore.setState({ user: makeUser(UserRole.coach), isAuthenticated: true });
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );
    expect(captured.toolbar!.showAxisToggle).toBe(true);
  });

  it("modo coach pero rol parent (vista de padre autenticado) → showAxisToggle=false", () => {
    useAuthStore.setState({ user: makeUser(UserRole.parent), isAuthenticated: true });
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );
    expect(captured.toolbar!.showAxisToggle).toBe(false);
  });

  it("modo parent → showAxisToggle=false sin importar el indicador ni el rol", () => {
    useAuthStore.setState({ user: makeUser(UserRole.coach), isAuthenticated: true });
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="parent" />,
    );
    expect(captured.toolbar!.showAxisToggle).toBe(false);
  });

  it("cambiar el indicador a IMC apaga el toggle y resetea el eje a 'chrono'", async () => {
    useAuthStore.setState({ user: makeUser(UserRole.coach), isAuthenticated: true });
    const user = userEvent.setup();
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );

    // Activar eje biológico primero para poder observar el reset.
    await user.click(screen.getByRole("button", { name: "mock-set-bio" }));
    await waitFor(() => expect(captured.toolbar!.axis).toBe("bio"));

    await user.click(screen.getByRole("button", { name: "mock-set-bmi" }));

    await waitFor(() => {
      expect(captured.toolbar!.indicator).toBe("bmi_for_age");
      expect(captured.toolbar!.showAxisToggle).toBe(false);
      expect(captured.toolbar!.axis).toBe("chrono");
    });
  });
});

// ---------------------------------------------------------------------------
// 4. Toggle de vista — Gráfica ↔ Tabla
// ---------------------------------------------------------------------------

describe("GrowthCurveSection — toggle de vista", () => {
  it("por defecto muestra la gráfica; al alternar la vista muestra la tabla", async () => {
    const user = userEvent.setup();
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );

    expect(screen.getByTestId("mock-chart")).toBeInTheDocument();
    expect(screen.queryByTestId("mock-table")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "mock-toggle-view" }));

    await waitFor(() => {
      expect(screen.queryByTestId("mock-chart")).not.toBeInTheDocument();
      expect(screen.getByTestId("mock-table")).toBeInTheDocument();
    });
  });

  // El proposal §5.2 pide "table view available" también para la familia: el
  // toggle no puede quedar visible pero inerte (regresión encontrada en el
  // gate de la ola US4).
  it("en modo padre el toggle de vista funciona y monta la tabla con preset family", async () => {
    const user = userEvent.setup();
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="parent" />,
    );

    expect(screen.getByTestId("mock-chart")).toBeInTheDocument();
    expect(captured.chart!.preset).toBe("family");

    await user.click(screen.getByRole("button", { name: "mock-toggle-view" }));

    await waitFor(() => {
      expect(screen.getByTestId("mock-table")).toBeInTheDocument();
    });
    expect(captured.table!.preset).toBe("family");
  });

  it("en modo coach la gráfica y la tabla usan el preset de coach", async () => {
    const user = userEvent.setup();
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );

    expect(captured.chart!.preset).toBe("coach");

    await user.click(screen.getByRole("button", { name: "mock-toggle-view" }));

    await waitFor(() => {
      expect(screen.getByTestId("mock-table")).toBeInTheDocument();
    });
    expect(captured.table!.preset).toBe("coach");
  });
});

// ---------------------------------------------------------------------------
// 5. Exportación PNG — nombre de archivo sin PII, estado `exporting`
// ---------------------------------------------------------------------------

describe("GrowthCurveSection — exportación a PNG", () => {
  it("genera un enlace de descarga sin datos identificables y refleja `exporting` mientras dura", async () => {
    let resolveToPng: (dataUrl: string) => void = () => {};
    mockToPng.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          resolveToPng = resolve;
        }),
    );

    // Referencia real a document.createElement para no recursar sobre el spy.
    const originalCreateElement = document.createElement.bind(document);
    const mockLink = { href: "", download: "", click: vi.fn() };
    const createElementSpy = vi
      .spyOn(document, "createElement")
      .mockImplementation((tag: string) => {
        if (tag === "a") return mockLink as unknown as HTMLElement;
        return originalCreateElement(tag);
      });

    const user = userEvent.setup();
    render(
      <GrowthCurveSection athlete={makeAthlete()} records={oneRecord} mode="coach" />,
    );

    await user.click(screen.getByRole("button", { name: "mock-export" }));

    await waitFor(() => expect(captured.toolbar!.exporting).toBe(true));

    resolveToPng("data:image/png;base64,AAAA");

    await waitFor(() => expect(mockLink.click).toHaveBeenCalledOnce());

    expect(mockLink.download).toMatch(/^crecimiento-.*\.png$/);
    // Sin nombre, apellido ni id de atleta expuestos en el nombre de archivo.
    expect(mockLink.download).not.toMatch(/atleta|ficticio|-1-|athlete/i);

    await waitFor(() => expect(captured.toolbar!.exporting).toBe(false));

    createElementSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// 9. PHV derivado de la medición más reciente (regresión T004/T005)
// ---------------------------------------------------------------------------

/**
 * Antes de T052 la página (`MyAthleteDetailPage.tsx`) calculaba
 * `phvAgeMonths` y lo pasaba al gráfico; el defecto G-0x del audit era que
 * tomaba la medición más antigua. Ahora la derivación vive aquí
 * (`findLatestRecord` ordena por `evaluation_date` desc), así que la
 * regresión se vigila en este archivo — la página sólo garantiza que
 * entrega la lista completa sin reordenar.
 */
describe("GrowthCurveSection — PHV de la medición más reciente", () => {
  const newest = makeRecord({ id: 3, evaluation_date: "2026-08-01", age_at_phv: 13.5 });
  const middle = makeRecord({ id: 2, evaluation_date: "2026-05-01", age_at_phv: 13.0 });
  const oldest = makeRecord({ id: 1, evaluation_date: "2026-01-15", age_at_phv: 12.0 });

  it("con la lista newest-first usa age_at_phv de la más reciente", () => {
    render(
      <GrowthCurveSection
        athlete={makeAthlete()}
        records={[newest, middle, oldest]}
        mode="coach"
      />,
    );
    // 13.5 años * 12 = 162 meses (la más antigua daría 144).
    expect(captured.chart!.phvAgeMonths).toBe(162);
  });

  it("con la lista desordenada sigue usando la medición más reciente", () => {
    render(
      <GrowthCurveSection
        athlete={makeAthlete()}
        records={[oldest, newest, middle]}
        mode="coach"
      />,
    );
    expect(captured.chart!.phvAgeMonths).toBe(162);
  });

  it("sin age_at_phv en la más reciente no pasa phvAgeMonths", () => {
    render(
      <GrowthCurveSection
        athlete={makeAthlete()}
        records={[makeRecord({ id: 4, evaluation_date: "2026-09-01", age_at_phv: undefined }), oldest]}
        mode="coach"
      />,
    );
    expect(captured.chart!.phvAgeMonths).toBeUndefined();
  });
});
