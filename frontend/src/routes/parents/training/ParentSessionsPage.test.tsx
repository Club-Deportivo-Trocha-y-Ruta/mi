import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/trainingSessions");

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentMonthlySummary, useParentSessions } from "@/api/trainingSessions";
import { useParentContextStore } from "@/store/parentContext.store";
import { ParentSessionsPage } from "./ParentSessionsPage";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { MyAthleteOut } from "@/types/parent.types";
import type {
  KidAttendance,
  ParentMonthlySummary,
  TrainingSession,
} from "@/types/trainingSession.types";

function makeAthlete(id: number, firstName: string, ageDecimal: number | null = 13.2): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: firstName,
    athlete_last_name: "García",
    birth_date: "2013-01-01",
    sex: "M" as any,
    age_decimal: ageDecimal,
    category: "U15",
    relationship: "padre" as any,
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function makeSession(
  id: number,
  focus: string,
  kidAttendance?: KidAttendance | null,
  overrides?: Partial<TrainingSession>,
): TrainingSession {
  return {
    id,
    club_id: 1,
    created_by_user_id: 2,
    status: "executed",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: focus,
    description: "Sesión técnica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    kid_attendances: kidAttendance ? [kidAttendance] : null,
    ...overrides,
  };
}

function makeSummary(athleteId: number, overrides?: Partial<ParentMonthlySummary>): ParentMonthlySummary {
  return {
    athlete_id: athleteId,
    athlete_name: "Atleta Test",
    year: 2026,
    month: 5,
    count_present: 3,
    count_total: 4,
    percentage: 75,
    focos_técnicos: ["Frenada", "Cornering"],
    avg_rpe: 6.5,
    avg_rubric_effort: 4,
    avg_rubric_attitude: 5,
    avg_rubric_technique: 3,
    ...overrides,
  };
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function renderPage() {
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={0}>
        <MemoryRouter>
          <ParentSessionsPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function mockSummary(value?: Partial<ReturnType<typeof useParentMonthlySummary>>) {
  (useParentMonthlySummary as any).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    ...value,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
  // Wave 4: ParentSessionsPage ahora lee el atleta seleccionado desde
  // useParentContextStore (singleton). Sin reset, el id elegido en un
  // test previo se filtra al siguiente y rompe asserts de "sin selección".
  useParentContextStore.setState({ activeAthleteId: null });
  window.localStorage.removeItem("parent-context");
  // default summary mock — overridable per test
  mockSummary();
});

describe("ParentSessionsPage — privacidad y estados base", () => {
  it("muestra solo las sesiones del atleta del padre (filtro defensivo)", () => {
    const myAthlete = makeAthlete(10, "Sebastián");
    const mySession = makeSession(1, "Foco MI atleta", { athlete_id: 10, status: "presente" });

    (useMyAthletes as any).mockReturnValue({ data: [myAthlete], isLoading: false, isError: false });
    (useParentSessions as any).mockReturnValue({
      data: [mySession],
      isLoading: false,
      isError: false,
    });

    renderPage();

    expect(screen.getByText("Foco MI atleta")).toBeInTheDocument();
  });

  it("muestra el estado vacío si no hay sesiones", () => {
    (useMyAthletes as any).mockReturnValue({ data: [makeAthlete(10, "Sebastián")], isLoading: false, isError: false });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("muestra selector de atleta cuando el padre tiene múltiples hijos", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián"), makeAthlete(20, "Valentina")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.getByRole("button", { name: /Sebastián/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Valentina/i })).toBeInTheDocument();
  });

  it("cambia el filtro al seleccionar un atleta diferente", async () => {
    const user = userEvent.setup();
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián"), makeAthlete(20, "Valentina")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    const valentina = screen.getByRole("button", { name: /Valentina/i });
    await user.click(valentina);

    expect(valentina).toHaveAttribute("aria-pressed", "true");
  });

  it("no muestra selector cuando el padre tiene un solo hijo", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.queryByRole("button", { name: /Sebastián/i })).not.toBeInTheDocument();
  });

  it("muestra mensaje de error si la query de sesiones falla", () => {
    (useMyAthletes as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    (useParentSessions as any).mockReturnValue({ data: undefined, isLoading: false, isError: true });

    renderPage();

    expect(screen.getByText(/No fue posible cargar las sesiones/)).toBeInTheDocument();
  });

  it("muestra estado vacío de no-atletas cuando el padre no está vinculado", () => {
    (useMyAthletes as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.getByTestId("no-athletes-state")).toBeInTheDocument();
  });

  it("muestra selector de mes cuando hay atletas", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.getByRole("button", { name: /Mes anterior/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mes siguiente/i })).toBeInTheDocument();
  });

  it("el botón Mes siguiente está deshabilitado en el mes actual", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.getByRole("button", { name: /Mes siguiente/i })).toBeDisabled();
  });
});

describe("ParentSessionsPage — banner promedios mensuales", () => {
  it("muestra el banner cuando hay un único atleta", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({ data: [makeSummary(10)] });

    renderPage();

    expect(screen.getByTestId("parent-monthly-banner")).toBeInTheDocument();
    // Wave 5: copy migrado a "X entrenos de Y programados" + % como referencia.
    expect(screen.getByTestId("monthly-stat-attendance")).toHaveTextContent(
      /3 entrenos de 4 programados/,
    );
  });

  it("oculta rúbrica numérica en banner para atletas <13 años", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián", 11.5)],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({ data: [makeSummary(10)] });

    renderPage();

    expect(screen.queryByTestId("monthly-stat-effort")).not.toBeInTheDocument();
    expect(screen.queryByTestId("monthly-stat-rpe")).not.toBeInTheDocument();
    // pero sí asistencia y focos
    expect(screen.getByTestId("monthly-stat-attendance")).toBeInTheDocument();
    expect(screen.getByTestId("monthly-technical-focuses")).toBeInTheDocument();
  });

  it("muestra rúbrica con etiquetas cualitativas en banner para ≥13", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián", 14)],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({ data: [makeSummary(10)] });

    renderPage();

    const banner = screen.getByTestId("parent-monthly-banner");
    expect(within(banner).getByText("Consolidando")).toBeInTheDocument(); // effort 4
    expect(within(banner).getByText("Dominando")).toBeInTheDocument(); // attitude 5
    expect(within(banner).getByText("Avanzando")).toBeInTheDocument(); // technique 3
  });

  it("oculta el banner cuando hay múltiples atletas sin selección — muestra hint", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián"), makeAthlete(20, "Valentina")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });

    renderPage();

    expect(screen.queryByTestId("parent-monthly-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("multi-athlete-hint")).toBeInTheDocument();
  });

  it("muestra el banner tras seleccionar un atleta en vista multi-atleta", async () => {
    const user = userEvent.setup();
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián"), makeAthlete(20, "Valentina")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({ data: [makeSummary(20, { athlete_name: "Valentina García" })] });

    renderPage();

    await user.click(screen.getByRole("button", { name: /Valentina/i }));
    expect(screen.getByTestId("parent-monthly-banner")).toBeInTheDocument();
  });

  it("muestra estado vacío del banner cuando count_total es 0", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({
      data: [makeSummary(10, { count_present: 0, count_total: 0, percentage: 0, focos_técnicos: [] })],
    });

    renderPage();

    expect(screen.getByTestId("monthly-banner-empty")).toBeInTheDocument();
  });

  it("muestra estado de error del banner si la query falla", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({ data: [], isLoading: false, isError: false });
    mockSummary({ data: undefined, isError: true });

    renderPage();

    expect(screen.getByTestId("monthly-banner-error")).toBeInTheDocument();
  });
});

describe("ParentSessionsPage — privacidad cross-atleta en card", () => {
  it("no muestra rúbrica ni comentario del atleta NO seleccionado", async () => {
    const user = userEvent.setup();
    const session = makeSession(1, "Sesión compartida", null, {
      kid_attendances: [
        {
          athlete_id: 10,
          status: "presente",
          rubric_effort: 5,
          individual_feedback: "Comentario sobre Sebastián",
        },
        {
          athlete_id: 20,
          status: "presente",
          rubric_effort: 2,
          individual_feedback: "Comentario sobre Valentina — confidencial",
        },
      ],
    });

    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián", 14), makeAthlete(20, "Valentina", 14)],
      isLoading: false,
      isError: false,
    });
    (useParentSessions as any).mockReturnValue({
      data: [session],
      isLoading: false,
      isError: false,
    });
    mockSummary({ data: [makeSummary(10), makeSummary(20)] });

    renderPage();

    // Sin selección de atleta — no debe mostrar rúbrica ni comentario individual
    expect(screen.queryByText(/Comentario sobre Sebastián/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Comentario sobre Valentina/)).not.toBeInTheDocument();

    // Selecciono Sebastián
    await user.click(screen.getByRole("button", { name: /Sebastián/i }));
    expect(screen.getByText(/Comentario sobre Sebastián/)).toBeInTheDocument();
    expect(screen.queryByText(/Comentario sobre Valentina/)).not.toBeInTheDocument();
  });
});
