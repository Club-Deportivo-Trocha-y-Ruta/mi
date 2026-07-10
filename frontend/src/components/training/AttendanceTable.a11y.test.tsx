import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

expect.extend(toHaveNoViolations);

vi.mock("@/api/trainingSessions", () => ({
  useUpdateAttendance: vi.fn(),
}));

// `LinkSessionDialog` real depende de `useTrainingSessions`/MSW — fuera del
// alcance de esta suite (ya cubierto por LinkSessionDialog.test.tsx /
// ActivityEvidenceStrip.test.tsx). Se stubea para aislar el axe scan del
// estado "sin enlazar" de la fila.
vi.mock("@/components/activities/LinkSessionDialog", () => ({
  LinkSessionDialog: () => null,
}));

import { useUpdateAttendance } from "@/api/trainingSessions";
import { AttendanceTable } from "./AttendanceTable";
import type { Attendance } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";
import { makeAttendance } from "@/test/msw/trainingHandlers";
import { mockActivity } from "@/test/msw/stravaHandlers";

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

function renderTable(attendances: Attendance[], disabled = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AttendanceTable sessionId={10} attendances={attendances} disabled={disabled} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mutate.mockClear();
  vi.mocked(useUpdateAttendance).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpdateAttendance>,
  );
});

describe("AttendanceTable — accesibilidad", () => {
  it("sin violaciones axe con atletas presentes", async () => {
    const { container } = renderTable([
      makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "presente" }),
      makeAttendance({ id: 2, athlete_id: 2, athlete_name: "Laura Pérez", status: "ausente" }),
    ]);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe con tabla vacía", async () => {
    const { container } = renderTable([]);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe con tabla deshabilitada (sesión cancelada)", async () => {
    const { container } = renderTable(
      [makeAttendance({ status: "presente" })],
      true,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("tab navega a través de las filas de asistencia", async () => {
    const user = userEvent.setup();
    renderTable([
      makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "presente" }),
      makeAttendance({ id: 2, athlete_id: 2, athlete_name: "Laura Pérez", status: "presente" }),
    ]);

    // Tab desde el documento para moverse al primer elemento interactivo de la tabla
    await user.tab();

    // Debe existir un elemento enfocado
    expect(document.activeElement).not.toBe(document.body);
  });

  it("los sliders de rúbrica tienen roles, aria-valuenow, aria-valuemin y aria-valuemax", () => {
    renderTable([makeAttendance({ status: "presente", rpe_omni: 7, rubric_effort: 4, rubric_attitude: 3, rubric_technique: 5 })]);

    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBeGreaterThanOrEqual(4); // RPE + 3 rúbrica

    for (const slider of sliders) {
      expect(slider).toHaveAttribute("aria-valuenow");
      expect(slider).toHaveAttribute("aria-valuemin");
      expect(slider).toHaveAttribute("aria-valuemax");
    }
  });

  it("el select de estado tiene aria-label", () => {
    renderTable([makeAttendance()]);
    const selects = screen.getAllByRole("combobox", { name: /Estado de asistencia/i });
    expect(selects.length).toBeGreaterThanOrEqual(1);
  });

  describe("evidencia de actividad Strava — axe por estado (session-detail-redesign.md §8)", () => {
    function renderTableWithActivities(
      attendances: Attendance[],
      opts: {
        linkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
        unlinkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
        activitiesLoading?: boolean;
        canLink?: boolean;
      } = {},
    ) {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <AttendanceTable
              sessionId={10}
              attendances={attendances}
              linkedActivitiesByAthleteId={opts.linkedActivitiesByAthleteId}
              unlinkedActivitiesByAthleteId={opts.unlinkedActivitiesByAthleteId}
              activitiesLoading={opts.activitiesLoading}
              canLink={opts.canLink}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );
    }

    it("sin violaciones axe: estado vacío (sin actividad Strava)", async () => {
      const { container } = renderTableWithActivities([
        makeAttendance({ athlete_id: 1, status: "presente" }),
      ]);
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones axe: cargando (skeleton)", async () => {
      const { container } = renderTableWithActivities(
        [makeAttendance({ athlete_id: 1, status: "presente" })],
        { activitiesLoading: true },
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones axe: sin enlazar, con acción Enlazar", async () => {
      const unlinked = new Map<number, ActivityOut[]>([
        [1, [mockActivity({ id: 5, athlete_id: 1, link: null })]],
      ]);
      const { container } = renderTableWithActivities(
        [makeAttendance({ athlete_id: 1, status: "presente" })],
        { unlinkedActivitiesByAthleteId: unlinked, canLink: true },
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones axe: enlazada, colapsada", async () => {
      const linked = new Map<number, ActivityOut[]>([
        [1, [mockActivity({ id: 5, athlete_id: 1 })]],
      ]);
      const { container } = renderTableWithActivities(
        [makeAttendance({ athlete_id: 1, status: "presente" })],
        { linkedActivitiesByAthleteId: linked, canLink: true },
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones axe: enlazada, expandida (ActivityCard visible, sin acordeón anidado)", async () => {
      const user = userEvent.setup();
      const linked = new Map<number, ActivityOut[]>([
        [1, [mockActivity({ id: 5, athlete_id: 1 })]],
      ]);
      const { container } = renderTableWithActivities(
        [makeAttendance({ athlete_id: 1, status: "presente" })],
        { linkedActivitiesByAthleteId: linked, canLink: true },
      );
      // `AttendanceTable` renderiza card móvil + fila de escritorio a la
      // vez en jsdom (responsividad solo CSS) — se acota al chevron de la
      // fila de escritorio para evitar ambigüedad de "multiple elements".
      const row = within(screen.getByTestId("attendance-row-1"));
      await user.click(row.getByRole("button", { name: /ver detalle de actividad/i }));
      expect(await axe(container)).toHaveNoViolations();
    });

    it("el chevron y el botón Enlazar no interfieren con los atajos P/A/J/T/L de la fila", () => {
      const unlinked = new Map<number, ActivityOut[]>([
        [1, [mockActivity({ id: 5, athlete_id: 1, link: null })]],
      ]);
      renderTableWithActivities(
        [makeAttendance({ athlete_id: 1, status: "ausente" })],
        { unlinkedActivitiesByAthleteId: unlinked, canLink: true },
      );
      const row = screen.getByTestId("attendance-row-1");
      const enlazarButton = within(row).getByRole("button", { name: /^Enlazar$/i });
      // El guard de la fila bail-ea en tag === "button" — un keydown "p"
      // disparado desde el propio botón no debe alterar el estado de la fila.
      enlazarButton.dispatchEvent(
        new KeyboardEvent("keydown", { key: "p", bubbles: true }),
      );
      const selects = row.querySelectorAll("select");
      expect(selects[0]).toHaveValue("ausente");
    });
  });
});
