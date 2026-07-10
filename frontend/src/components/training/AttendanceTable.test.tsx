import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/api/trainingSessions", () => ({
  useUpdateAttendance: vi.fn(),
}));

// `ActivityEvidenceStrip` en estado "enlazado" expandido renderiza
// `ActivityCard`, que lee el rol autenticado internamente (doble gate de
// `canLink` + rol — ver docstring de ActivityCard.tsx).
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "coach" } }),
}));

// `LinkSessionDialog` real depende de `useTrainingSessions`/MSW — fuera del
// alcance de esta suite (ya cubierto por LinkSessionDialog.test.tsx /
// ActivityEvidenceStrip.test.tsx). Se stubea para aislar el estado "sin
// enlazar" de la fila.
vi.mock("@/components/activities/LinkSessionDialog", () => ({
  LinkSessionDialog: () => null,
}));

import { useUpdateAttendance } from "@/api/trainingSessions";
import { AttendanceTable } from "./AttendanceTable";
import type { Attendance } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";

const mutate = vi.fn();
const mutationStub = {
  mutate,
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  data: undefined,
  error: null,
  variables: undefined,
  context: undefined,
  status: "idle" as const,
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

function makeAttendance(overrides?: Partial<Attendance>): Attendance {
  return {
    id: 1,
    session_id: 10,
    athlete_id: 1,
    athlete_name: "Sebastián García",
    status: "presente",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    rpe_omni: 5,
    rubric_effort: 3,
    rubric_attitude: 3,
    rubric_technique: 3,
    ...overrides,
  };
}

function makeActivity(overrides?: Partial<ActivityOut>): ActivityOut {
  return {
    id: 1,
    athlete_id: 1,
    athlete_name: "Sebastián García",
    name: "Rodada matutina",
    sport_type: "MountainBikeRide",
    start_date_local: "2026-07-08T06:30:00",
    elapsed_time_s: 5400,
    moving_time_s: 5100,
    distance_m: 32000,
    total_elevation_gain_m: 450,
    average_heartrate: 148,
    max_heartrate: 172,
    is_trainer: false,
    upstream_state: "present",
    summary_complete: true,
    link: null,
    ...overrides,
  };
}

interface RenderTableOptions {
  sessionId?: number;
  disabled?: boolean;
  linkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  unlinkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  activitiesLoading?: boolean;
  canLink?: boolean;
}

function renderTable(attendances: Attendance[], options: RenderTableOptions = {}) {
  const {
    sessionId = 10,
    disabled = false,
    linkedActivitiesByAthleteId,
    unlinkedActivitiesByAthleteId,
    activitiesLoading = false,
    canLink = false,
  } = options;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AttendanceTable
          sessionId={sessionId}
          attendances={attendances}
          disabled={disabled}
          linkedActivitiesByAthleteId={linkedActivitiesByAthleteId}
          unlinkedActivitiesByAthleteId={unlinkedActivitiesByAthleteId}
          activitiesLoading={activitiesLoading}
          canLink={canLink}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mutate.mockClear();
  vi.mocked(useUpdateAttendance).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpdateAttendance>,
  );
});

describe("AttendanceTable", () => {
  describe("estado vacío", () => {
    it("muestra mensaje cuando no hay convocados", () => {
      renderTable([]);
      expect(
        screen.getByText(/No hay atletas convocados en esta sesión/i),
      ).toBeInTheDocument();
    });
  });

  describe("renderizado de fila", () => {
    it("muestra el nombre del atleta", () => {
      renderTable([makeAttendance()]);
      expect(screen.getAllByText("Sebastián García").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra el select de estado con valor inicial", () => {
      renderTable([makeAttendance({ status: "presente" })]);
      const selects = screen.getAllByRole("combobox", { name: /Estado de asistencia/i });
      expect(selects[0]).toHaveValue("presente");
    });
  });

  describe("autosave debounced", () => {
    it("llama mutate después de 500ms de idle", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const selects = screen.getAllByRole("combobox", { name: /Estado de asistencia/i });
      fireEvent.change(selects[0], { target: { value: "tarde" } });

      expect(mutate).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(600);
      });

      expect(mutate).toHaveBeenCalled();
      vi.useRealTimers();
    });
  });

  describe("shortcuts de teclado", () => {
    it("P key establece estado presente en la fila del atleta", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance({ status: "ausente" })]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "p" });

      // El select en la fila desktop (puede estar hidden en CSS pero presente en DOM)
      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("presente");

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("A key establece estado ausente", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance({ status: "presente" })]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "a" });

      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("ausente");

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("J key establece estado justificado", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "j" });

      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("justificado");

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("T key establece estado tarde", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "t" });

      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("tarde");

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("L key establece estado lesionado", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "l" });

      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("lesionado");

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("ignora shortcut cuando el foco está en un input de texto", () => {
      renderTable([makeAttendance({ status: "ausente" })]);

      const row = screen.getByTestId("attendance-row-1");
      const input = row.querySelector("input[type='text']");
      if (input) {
        fireEvent.keyDown(input, { key: "p" });
        const selects = row.querySelectorAll("select");
        expect(selects[0]).toHaveValue("ausente");
      }
    });
  });

  describe("rúbrica deshabilitada para ausente", () => {
    it("no muestra RubricSliders cuando status=ausente", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      const ranges = screen.queryAllByRole("slider", { name: /RPE OMNI/i });
      expect(ranges.length).toBe(0);
    });

    it("muestra campo razón cuando status=ausente", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      const inputs = screen.getAllByRole("textbox", { name: /Razón de ausencia/i });
      expect(inputs.length).toBeGreaterThanOrEqual(1);
    });

    it("muestra RubricSliders cuando status=presente", () => {
      renderTable([makeAttendance({ status: "presente" })]);
      const ranges = screen.getAllByRole("slider", { name: /RPE OMNI/i });
      expect(ranges.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("indicador guardado", () => {
    it("muestra icono guardado tras llamada exitosa a mutate", async () => {
      let capturedOnSuccess: (() => void) | undefined;
      vi.mocked(useUpdateAttendance).mockReturnValue({
        ...mutationStub,
        mutate: vi.fn((_vars: unknown, opts?: { onSuccess?: () => void }) => {
          capturedOnSuccess = opts?.onSuccess;
        }),
      } as unknown as ReturnType<typeof useUpdateAttendance>);

      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      const selects = row.querySelectorAll("select");
      fireEvent.change(selects[0], { target: { value: "tarde" } });

      await act(async () => { vi.advanceTimersByTime(600); });

      act(() => { capturedOnSuccess?.(); });

      expect(screen.getByTestId("saved-indicator")).toBeInTheDocument();
      vi.useRealTimers();
    });
  });

  describe("disabled cuando cancelled", () => {
    it("los selects están deshabilitados cuando disabled=true", () => {
      renderTable([makeAttendance()], { sessionId: 10, disabled: true });
      const selects = screen.getAllByRole("combobox", { name: /Estado de asistencia/i });
      selects.forEach((s) => expect(s).toBeDisabled());
    });
  });

  // `AttendanceTable` siempre renderiza AMBAS variantes (card móvil + fila
  // de escritorio) en el DOM — la responsividad es solo CSS (`md:hidden` /
  // `hidden md:block`), que jsdom no aplica. Las queries se acotan con
  // `within(desktopRow)` para evitar falsos "multiple elements found"
  // (mismo patrón que el resto de la suite: `row.querySelectorAll(...)`).
  describe("evidencia de actividad Strava (session-detail-redesign.md §3.2)", () => {
    it("atleta sin datos de actividad muestra el estado neutro 'Sin actividad Strava'", () => {
      renderTable([makeAttendance({ athlete_id: 1 })]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText(/Sin actividad Strava/i)).toBeInTheDocument();
    });

    it("un Map sin entrada para el atleta cae al estado vacío en vez de lanzar", () => {
      const linked = new Map<number, ActivityOut[]>([[999, [makeActivity({ athlete_id: 999 })]]]);
      renderTable([makeAttendance({ athlete_id: 1 })], {
        linkedActivitiesByAthleteId: linked,
      });
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText(/Sin actividad Strava/i)).toBeInTheDocument();
    });

    it("resuelve la actividad enlazada correcta por athlete_id (lookup puntual, no por índice)", () => {
      const linked = new Map<number, ActivityOut[]>([
        [2, [makeActivity({ id: 20, athlete_id: 2, elapsed_time_s: 5400 })]],
      ]);
      renderTable(
        [
          makeAttendance({ athlete_id: 1, athlete_name: "Atleta Uno" }),
          makeAttendance({ athlete_id: 2, athlete_name: "Atleta Dos" }),
        ],
        { linkedActivitiesByAthleteId: linked },
      );

      // Atleta 1 (sin actividad en el Map) queda neutro; atleta 2 (con
      // actividad) muestra el chip de cumplimiento.
      expect(screen.getAllByTestId("activity-evidence-empty-1").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByTestId("activity-evidence-linked-2").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra el badge 'Actividad sin enlazar' + botón Enlazar cuando canLink=true", () => {
      const unlinked = new Map<number, ActivityOut[]>([
        [1, [makeActivity({ id: 30, athlete_id: 1, link: null })]],
      ]);
      renderTable([makeAttendance({ athlete_id: 1 })], {
        unlinkedActivitiesByAthleteId: unlinked,
        canLink: true,
      });

      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText(/Actividad sin enlazar/i)).toBeInTheDocument();
      expect(row.getByRole("button", { name: /Enlazar/i })).toBeInTheDocument();
    });

    it("oculta el botón Enlazar cuando canLink=false aunque haya actividad sin enlazar", () => {
      const unlinked = new Map<number, ActivityOut[]>([
        [1, [makeActivity({ id: 30, athlete_id: 1, link: null })]],
      ]);
      renderTable([makeAttendance({ athlete_id: 1 })], {
        unlinkedActivitiesByAthleteId: unlinked,
        canLink: false,
      });

      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText(/Actividad sin enlazar/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Enlazar/i })).not.toBeInTheDocument();
    });

    it("muestra el skeleton de carga cuando activitiesLoading=true", () => {
      renderTable([makeAttendance({ athlete_id: 1 })], { activitiesLoading: true });
      expect(screen.getAllByTestId("activity-evidence-loading-1").length).toBeGreaterThanOrEqual(1);
    });

    it("el chevron expande y muestra un ActivityCard por actividad enlazada", () => {
      const linked = new Map<number, ActivityOut[]>([
        [1, [makeActivity({ id: 40, athlete_id: 1 })]],
      ]);
      renderTable([makeAttendance({ athlete_id: 1 })], {
        linkedActivitiesByAthleteId: linked,
      });

      const row = within(screen.getByTestId("attendance-row-1"));
      expect(screen.queryByText(/Rodada matutina/i)).not.toBeInTheDocument();
      fireEvent.click(row.getByRole("button", { name: /ver detalle de actividad/i }));
      expect(row.getByText(/Rodada matutina/i)).toBeInTheDocument();
    });
  });
});
