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
import { AttendanceTable, type AttendanceWithAttribution } from "./AttendanceTable";
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

function makeAttendance(
  overrides?: Partial<AttendanceWithAttribution>,
): AttendanceWithAttribution {
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

function renderTable(
  attendances: AttendanceWithAttribution[],
  options: RenderTableOptions = {},
) {
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

    it("muestra el control segmentado de estado con el valor inicial marcado", () => {
      renderTable([makeAttendance({ status: "presente" })]);
      const groups = screen.getAllByRole("group", { name: "Estado de asistencia" });
      const checked = within(groups[0]).getByRole("radio", { checked: true });
      expect(checked).toHaveAccessibleName("Presente");
    });
  });

  describe("atribución de registro (feature 041 — gobernanza multi-coach)", () => {
    it("muestra 'Registrado por {A} · Editado por {B}' cuando ambos difieren", () => {
      renderTable([
        makeAttendance({
          athlete_id: 1,
          recorded_by_display_name: "Ana Coach",
          last_edited_by_display_name: "Bruno Coach",
        }),
      ]);
      const lines = screen.getAllByTestId("attendance-attribution-1");
      expect(lines.length).toBeGreaterThanOrEqual(1);
      lines.forEach((line) =>
        expect(line).toHaveTextContent("Registrado por Ana Coach · Editado por Bruno Coach"),
      );
    });

    it("muestra solo 'Registrado por {A}' cuando last_edited_by_display_name es null", () => {
      renderTable([
        makeAttendance({
          athlete_id: 1,
          recorded_by_display_name: "Ana Coach",
          last_edited_by_display_name: null,
        }),
      ]);
      const lines = screen.getAllByTestId("attendance-attribution-1");
      lines.forEach((line) => expect(line).toHaveTextContent("Registrado por Ana Coach"));
      lines.forEach((line) => expect(line).not.toHaveTextContent("Editado por"));
    });

    it("muestra solo 'Registrado por {A}' cuando ambos nombres coinciden", () => {
      renderTable([
        makeAttendance({
          athlete_id: 1,
          recorded_by_display_name: "Ana Coach",
          last_edited_by_display_name: "Ana Coach",
        }),
      ]);
      const lines = screen.getAllByTestId("attendance-attribution-1");
      lines.forEach((line) => expect(line).not.toHaveTextContent("Editado por"));
    });

    it("no renderiza nada cuando ambos campos son null (fila anterior a la feature)", () => {
      renderTable([
        makeAttendance({
          athlete_id: 1,
          recorded_by_display_name: null,
          last_edited_by_display_name: null,
        }),
      ]);
      expect(screen.queryByTestId("attendance-attribution-1")).not.toBeInTheDocument();
    });

    it("no renderiza nada cuando ninguno de los dos campos viene en el payload (pre-041)", () => {
      renderTable([makeAttendance({ athlete_id: 1 })]);
      expect(screen.queryByTestId("attendance-attribution-1")).not.toBeInTheDocument();
    });
  });

  describe("autosave debounced", () => {
    it("llama mutate después de 500ms de idle", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.click(within(row).getByRole("radio", { name: "Tarde" }));

      expect(mutate).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(600);
      });

      expect(mutate).toHaveBeenCalled();
      vi.useRealTimers();
    });

    it("RPE OMNI y las 3 rúbricas son opcionales: cambiar solo el estado a 'presente' no inventa valores (quedan en null)", async () => {
      vi.useFakeTimers();
      // Fixture típica de una sesión sin evaluación previa (p. ej. venía de
      // "ausente" con fisioterapia): los 4 campos ya son null en el servidor.
      renderTable([
        makeAttendance({
          status: "ausente",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
          individual_feedback: null,
        }),
      ]);

      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("radio", { name: "Presente" }));

      await act(async () => { vi.advanceTimersByTime(600); });

      expect(mutate).toHaveBeenCalled();
      const { payload } = mutate.mock.calls[mutate.mock.calls.length - 1][0];
      expect(payload.status).toBe("presente");
      expect(payload.rpe_omni).toBeNull();
      expect(payload.rubric_effort).toBeNull();
      expect(payload.rubric_attitude).toBeNull();
      expect(payload.rubric_technique).toBeNull();

      vi.useRealTimers();
    });

    it("deseleccionar un valor de rúbrica ya guardado lo envía como null (no lo deja en el valor anterior)", async () => {
      vi.useFakeTimers();
      renderTable([
        makeAttendance({ status: "presente", rpe_omni: 6, rubric_effort: 4, rubric_attitude: 4, rubric_technique: 3 }),
      ]);

      const table = within(screen.getByRole("table"));
      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));

      const rpeGroup = table.getByRole("group", { name: "RPE OMNI 0-10" });
      fireEvent.click(within(rpeGroup).getByRole("radio", { name: "RPE OMNI 0-10: 6 — Algo duro" }));

      await act(async () => { vi.advanceTimersByTime(600); });

      expect(mutate).toHaveBeenCalled();
      const { payload } = mutate.mock.calls[mutate.mock.calls.length - 1][0];
      expect(payload.rpe_omni).toBeNull();
      // Las otras 3 rúbricas no se tocaron, deben conservar su valor.
      expect(payload.rubric_effort).toBe(4);

      vi.useRealTimers();
    });
  });

  describe("shortcuts de teclado", () => {
    it("P key establece estado presente en la fila del atleta", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance({ status: "ausente" })]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "p" });

      expect(within(row).getByRole("radio", { name: "Presente", checked: true })).toBeInTheDocument();

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("A key establece estado ausente", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance({ status: "presente" })]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "a" });

      expect(within(row).getByRole("radio", { name: "Ausente", checked: true })).toBeInTheDocument();

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("J key establece estado justificado", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "j" });

      expect(within(row).getByRole("radio", { name: "Justificado", checked: true })).toBeInTheDocument();

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("T key establece estado tarde", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "t" });

      expect(within(row).getByRole("radio", { name: "Tarde", checked: true })).toBeInTheDocument();

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("L key establece estado lesionado", async () => {
      vi.useFakeTimers();
      renderTable([makeAttendance()]);

      const row = screen.getByTestId("attendance-row-1");
      fireEvent.keyDown(row, { key: "l" });

      expect(within(row).getByRole("radio", { name: "Lesionado", checked: true })).toBeInTheDocument();

      await act(async () => { vi.advanceTimersByTime(600); });
      vi.useRealTimers();
    });

    it("ignora shortcut cuando el foco está en un input de texto", () => {
      renderTable([makeAttendance({ status: "ausente" })]);

      const row = screen.getByTestId("attendance-row-1");
      const input = row.querySelector("input[type='text']");
      if (input) {
        fireEvent.keyDown(input, { key: "p" });
        expect(within(row).getByRole("radio", { name: "Ausente", checked: true })).toBeInTheDocument();
      }
    });
  });

  describe("rúbrica deshabilitada para ausente", () => {
    it("no muestra RubricSliders cuando status=ausente", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      // feature 028 T018: opciones ahora son role="radio" (ToggleGroupItem),
      // no role="slider" (input range nativo retirado).
      const options = screen.queryAllByRole("radio", { name: /RPE OMNI/i });
      expect(options.length).toBe(0);
    });

    it("muestra campo razón cuando status=ausente", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      const inputs = screen.getAllByRole("textbox", { name: /Razón de ausencia/i });
      expect(inputs.length).toBeGreaterThanOrEqual(1);
    });

    it("muestra RubricSliders cuando status=presente al pulsar Evaluar", () => {
      renderTable([makeAttendance({ status: "presente" })]);
      // Rediseño progressive disclosure: la rúbrica queda colapsada por
      // defecto — hay que pulsar "Evaluar" antes de que aparezcan sus
      // opciones discretas (feature 028 T018: 11 opciones 0-10).
      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));
      const options = screen.getAllByRole("radio", { name: /RPE OMNI/i });
      expect(options.length).toBeGreaterThanOrEqual(1);
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
      fireEvent.click(within(row).getByRole("radio", { name: "Tarde" }));

      await act(async () => { vi.advanceTimersByTime(600); });

      act(() => { capturedOnSuccess?.(); });

      expect(screen.getByTestId("saved-indicator")).toBeInTheDocument();
      vi.useRealTimers();
    });
  });

  describe("disabled cuando cancelled", () => {
    it("las opciones de estado están deshabilitadas cuando disabled=true", () => {
      renderTable([makeAttendance()], { sessionId: 10, disabled: true });
      const groups = screen.getAllByRole("group", { name: "Estado de asistencia" });
      groups.forEach((g) => within(g).getAllByRole("radio").forEach((r) => expect(r).toBeDisabled()));
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

  describe("rediseño progressive disclosure — rúbrica colapsada por defecto", () => {
    it("la rúbrica está colapsada por defecto y aparece solo al pulsar Evaluar", () => {
      renderTable([makeAttendance({ status: "presente" })]);
      // AttendanceTable siempre renderiza card móvil + fila de escritorio en
      // jsdom (responsividad solo CSS) y comparte el estado de expansión
      // entre ambas — se acota a la tabla de escritorio para evitar
      // "multiple elements found" con la card móvil duplicada.
      const table = within(screen.getByRole("table"));
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(table.queryByRole("group", { name: "RPE OMNI 0-10" })).not.toBeInTheDocument();

      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));
      expect(table.getByRole("group", { name: "RPE OMNI 0-10" })).toBeInTheDocument();

      fireEvent.click(row.getByRole("button", { name: /Cerrar evaluación/i }));
      expect(table.queryByRole("group", { name: "RPE OMNI 0-10" })).not.toBeInTheDocument();
    });

    it("no muestra el botón Evaluar cuando el estado no permite rúbrica", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.queryByRole("button", { name: /Evaluar|Editar/i })).not.toBeInTheDocument();
    });

    it("muestra el badge 'Sin evaluar' cuando no hay evaluación guardada y el formulario no fue tocado", () => {
      renderTable([
        makeAttendance({
          status: "presente",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
          individual_feedback: null,
        }),
      ]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText("Sin evaluar")).toBeInTheDocument();
    });

    it("muestra 'No aplica' cuando el estado no permite rúbrica", () => {
      renderTable([makeAttendance({ status: "ausente" })]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText("No aplica")).toBeInTheDocument();
    });

    it("el resumen de chips refleja los valores guardados (RPE/Esfuerzo/Actitud/Técnica)", () => {
      renderTable([
        makeAttendance({ status: "presente", rpe_omni: 7, rubric_effort: 4, rubric_attitude: 3, rubric_technique: 5 }),
      ]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText(/RPE 7/)).toBeInTheDocument();
      expect(row.getByText("Esfuerzo 4 · Actitud 3 · Técnica 5")).toBeInTheDocument();
    });

    it("una evaluación parcial (solo Actitud + comentario) muestra únicamente ese chip, sin inventar los demás", () => {
      renderTable([
        makeAttendance({
          status: "presente",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: 4,
          rubric_technique: null,
          individual_feedback: "Buena disposición hoy",
        }),
      ]);
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByText("Actitud 4")).toBeInTheDocument();
      expect(row.queryByText(/RPE/)).not.toBeInTheDocument();
      expect(row.queryByText(/Esfuerzo/)).not.toBeInTheDocument();
      expect(row.queryByText(/Técnica/)).not.toBeInTheDocument();
      expect(row.queryByText("Sin evaluar")).not.toBeInTheDocument();
      expect(row.getByLabelText("Con comentario del coach")).toBeInTheDocument();
    });

    it("el resumen de chips se actualiza en vivo al editar la rúbrica expandida", () => {
      renderTable([
        makeAttendance({ status: "presente", rpe_omni: 5, rubric_effort: 3, rubric_attitude: 3, rubric_technique: 3 }),
      ]);
      const table = within(screen.getByRole("table"));
      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));

      const effortGroup = table.getByRole("group", { name: "Esfuerzo" });
      fireEvent.click(within(effortGroup).getByRole("radio", { name: "Esfuerzo: 5 — Excelente" }));

      expect(row.getByText(/Esfuerzo 5/)).toBeInTheDocument();
    });

    it("el botón cambia de 'Evaluar' a 'Editar' en cuanto el formulario tiene algún valor (sin esperar el autosave)", () => {
      renderTable([
        makeAttendance({
          status: "presente",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
          individual_feedback: null,
        }),
      ]);
      const table = within(screen.getByRole("table"));
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByRole("button", { name: /^Evaluar a /i })).toBeInTheDocument();

      fireEvent.click(row.getByRole("button", { name: /^Evaluar a /i }));
      const attitudeGroup = table.getByRole("group", { name: "Actitud" });
      fireEvent.click(within(attitudeGroup).getByRole("radio", { name: "Actitud: 4 — Bueno" }));

      // Mientras el panel sigue abierto el botón dice "Cerrar" (tiene
      // prioridad sobre el estado de evaluación); al cerrarlo debe reflejar
      // que ya hay una evaluación (aunque el autosave de 500ms no haya corrido).
      expect(row.getByRole("button", { name: /^Cerrar evaluación de /i })).toBeInTheDocument();
      fireEvent.click(row.getByRole("button", { name: /^Cerrar evaluación de /i }));

      expect(row.getByRole("button", { name: /^Editar evaluación de /i })).toBeInTheDocument();
    });

    it("el botón 'Limpiar' pone en null los 4 campos y vacía el comentario, y vuelve a 'Sin evaluar'", () => {
      renderTable([
        makeAttendance({
          status: "presente",
          rpe_omni: 6,
          rubric_effort: 4,
          rubric_attitude: 4,
          rubric_technique: 3,
          individual_feedback: "Buen trabajo",
        }),
      ]);
      const table = within(screen.getByRole("table"));
      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));

      fireEvent.click(table.getByRole("button", { name: /^Limpiar$/i }));

      expect(row.getByText("Sin evaluar")).toBeInTheDocument();
      expect(table.getAllByText("Sin registrar").length).toBeGreaterThanOrEqual(4);
    });
  });

  describe("barra superior — resumen, filtros, búsqueda y acciones globales", () => {
    function manyAttendances(): AttendanceWithAttribution[] {
      return [
        makeAttendance({
          athlete_id: 1,
          athlete_name: "Sebastián García",
          status: "presente",
          rpe_omni: 5,
          rubric_effort: 3,
          rubric_attitude: 3,
          rubric_technique: 3,
        }),
        makeAttendance({ athlete_id: 2, athlete_name: "Laura Pérez", status: "ausente", excuse_reason: null }),
        makeAttendance({
          athlete_id: 3,
          athlete_name: "María José Ánimas",
          status: "tarde",
          rpe_omni: null,
          rubric_effort: null,
          rubric_attitude: null,
          rubric_technique: null,
          individual_feedback: null,
        }),
        makeAttendance({
          athlete_id: 4,
          athlete_name: "Andrés Ruiz",
          status: "justificado",
          excuse_reason: "Cita médica",
        }),
        makeAttendance({ athlete_id: 5, athlete_name: "Camilo Torres", status: "lesionado", excuse_reason: "Esguince" }),
        makeAttendance({ athlete_id: 6, athlete_name: "Julián Soto", status: "presente" }),
        makeAttendance({ athlete_id: 7, athlete_name: "Nicolás Vega", status: "presente" }),
        makeAttendance({ athlete_id: 8, athlete_name: "Valentina Ríos", status: "presente" }),
        makeAttendance({ athlete_id: 9, athlete_name: "Isabella Cano", status: "presente" }),
      ];
    }

    it("no renderiza una línea de resumen de texto aparte (los conteos ya están en los chips de filtro)", () => {
      renderTable(manyAttendances());
      expect(screen.queryByTestId("attendance-summary")).not.toBeInTheDocument();
    });

    it("los chips de filtro muestran el conteo correcto y 'Todos' siempre está visible", () => {
      renderTable(manyAttendances());
      const toolbar = within(screen.getByTestId("attendance-toolbar"));
      expect(toolbar.getByRole("radio", { name: "Todos (9)" })).toBeInTheDocument();
      expect(toolbar.getByRole("radio", { name: "Presentes (5)" })).toBeInTheDocument();
      expect(toolbar.getByRole("radio", { name: "Ausencias (3)" })).toBeInTheDocument();
      expect(toolbar.getByRole("radio", { name: "Sin evaluar (1)" })).toBeInTheDocument();
      expect(toolbar.getByRole("radio", { name: "Falta razón (1)" })).toBeInTheDocument();
    });

    it("oculta los chips de filtro con conteo 0 (salvo 'Todos')", () => {
      // Un solo atleta ya evaluado y con razón: "Sin evaluar", "Falta razón"
      // y "Ausencias" quedan en 0 y no deberían listarse como opciones.
      renderTable([
        makeAttendance({
          status: "presente",
          rpe_omni: 5,
          rubric_effort: 3,
          rubric_attitude: 3,
          rubric_technique: 3,
        }),
      ]);
      const toolbar = within(screen.getByTestId("attendance-toolbar"));
      expect(toolbar.getByRole("radio", { name: "Todos (1)" })).toBeInTheDocument();
      expect(toolbar.getByRole("radio", { name: "Presentes (1)" })).toBeInTheDocument();
      expect(toolbar.queryByRole("radio", { name: /Sin evaluar/i })).not.toBeInTheDocument();
      expect(toolbar.queryByRole("radio", { name: /Falta razón/i })).not.toBeInTheDocument();
      expect(toolbar.queryByRole("radio", { name: /Ausencias/i })).not.toBeInTheDocument();
    });

    it("filtro 'Sin evaluar' muestra solo presente/tarde sin evaluación guardada", () => {
      renderTable(manyAttendances());
      const toolbar = within(screen.getByTestId("attendance-toolbar"));
      fireEvent.click(toolbar.getByRole("radio", { name: /Sin evaluar/i }));

      expect(screen.getByTestId("attendance-row-3")).toBeInTheDocument();
      expect(screen.queryByTestId("attendance-row-1")).not.toBeInTheDocument();
    });

    it("filtro 'Falta razón' muestra solo estados que requieren razón y no la tienen", () => {
      renderTable(manyAttendances());
      const toolbar = within(screen.getByTestId("attendance-toolbar"));
      fireEvent.click(toolbar.getByRole("radio", { name: /Falta razón/i }));

      expect(screen.getByTestId("attendance-row-2")).toBeInTheDocument();
      expect(screen.queryByTestId("attendance-row-4")).not.toBeInTheDocument();
    });

    it("muestra mensaje cuando el filtro + búsqueda no dejan ninguna fila", () => {
      // "Presentes" tiene 5 convocados (conteo > 0, así que el chip es
      // visible), pero ninguno se llama "zzz" — la búsqueda lo reduce a 0.
      renderTable(manyAttendances());
      const toolbar = within(screen.getByTestId("attendance-toolbar"));
      fireEvent.click(toolbar.getByRole("radio", { name: /^Presentes/i }));

      const search = screen.getByLabelText("Buscar atleta");
      fireEvent.change(search, { target: { value: "zzz" } });

      expect(screen.getByText(/Ningún atleta coincide con el filtro/i)).toBeInTheDocument();
    });

    it("la búsqueda solo aparece con más de 8 convocados", () => {
      renderTable([makeAttendance()]);
      expect(screen.queryByLabelText("Buscar atleta")).not.toBeInTheDocument();
    });

    it("la búsqueda filtra por nombre de forma insensible a acentos y mayúsculas", () => {
      renderTable(manyAttendances());
      const search = screen.getByLabelText("Buscar atleta");
      fireEvent.change(search, { target: { value: "JOSE animas" } });

      expect(screen.getByTestId("attendance-row-3")).toBeInTheDocument();
      expect(screen.queryByTestId("attendance-row-1")).not.toBeInTheDocument();
    });

    it("'Expandir todo' expande la rúbrica de las filas visibles con rúbrica aplicable y cambia a 'Contraer todo'", () => {
      renderTable(manyAttendances());
      const toggleButton = screen.getByTestId("toggle-expand-all-button");
      expect(toggleButton).toHaveTextContent("Expandir todo");

      fireEvent.click(toggleButton);

      // presente (1,6,7,8,9) + tarde (3) = 6 filas con rúbrica aplicable.
      expect(screen.getAllByRole("group", { name: "RPE OMNI 0-10" }).length).toBeGreaterThanOrEqual(6);
      expect(screen.getByTestId("toggle-expand-all-button")).toHaveTextContent("Contraer todo");
    });

    it("'Contraer todo' colapsa las rúbricas expandidas de las filas visibles y vuelve a 'Expandir todo'", () => {
      renderTable(manyAttendances());
      const toggleButton = screen.getByTestId("toggle-expand-all-button");

      fireEvent.click(toggleButton);
      fireEvent.click(screen.getByTestId("toggle-expand-all-button"));

      expect(screen.queryByRole("group", { name: "RPE OMNI 0-10" })).not.toBeInTheDocument();
      expect(screen.getByTestId("toggle-expand-all-button")).toHaveTextContent("Expandir todo");
    });

    it("no muestra el botón de expandir/contraer todo cuando la tabla está deshabilitada", () => {
      renderTable(manyAttendances(), { disabled: true });
      expect(screen.queryByTestId("toggle-expand-all-button")).not.toBeInTheDocument();
    });
  });
});
