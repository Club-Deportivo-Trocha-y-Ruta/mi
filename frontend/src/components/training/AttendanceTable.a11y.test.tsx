import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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

  it("los grupos de rúbrica (RPE + 3 rúbrica) exponen opciones discretas accesibles (radio) al expandir la evaluación", () => {
    // feature 028 T018: los <input type="range"> nativos fueron reemplazados
    // por ToggleGroup/ToggleGroupItem (steppers discretos, target >=48px) —
    // Radix expone cada grupo como role="group" y cada opción como
    // role="radio" con aria-checked, no valuenow/valuemin/valuemax.
    // Rediseño progressive disclosure: la rúbrica queda colapsada por
    // defecto — hay que pulsar "Evaluar" antes de que existan sus grupos.
    renderTable([
      makeAttendance({ athlete_id: 1, status: "presente", rpe_omni: 7, rubric_effort: 4, rubric_attitude: 3, rubric_technique: 5 }),
    ]);

    const row = within(screen.getByTestId("attendance-row-1"));
    fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));

    const groups = screen.getAllByRole("group");
    // Estado de asistencia + RPE OMNI + Esfuerzo/Actitud/Técnica = 5 grupos
    // como mínimo (se duplican entre card móvil y fila de escritorio en jsdom).
    expect(groups.length).toBeGreaterThanOrEqual(5);

    const options = screen.getAllByRole("radio");
    expect(options.length).toBeGreaterThanOrEqual(9); // 5 (Estado) + al menos 4 de rúbrica

    for (const option of options) {
      expect(option).toHaveAttribute("aria-checked");
    }
  });

  it("el control segmentado de estado expone un grupo con nombre accesible", () => {
    renderTable([makeAttendance()]);
    const groups = screen.getAllByRole("group", { name: "Estado de asistencia" });
    expect(groups.length).toBeGreaterThanOrEqual(1);
    groups.forEach((g) => {
      const radios = within(g).getAllByRole("radio");
      expect(radios.length).toBe(5);
    });
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
      expect(within(row).getByRole("radio", { name: "Ausente", checked: true })).toBeInTheDocument();
    });
  });

  describe("rediseño progressive disclosure — barra superior y panel expandido", () => {
    it("sin violaciones axe con el panel de evaluación expandido", async () => {
      const { container } = renderTable([
        makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "presente" }),
      ]);
      const row = within(screen.getByTestId("attendance-row-1"));
      fireEvent.click(row.getByRole("button", { name: /Evaluar|Editar/i }));

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe con un filtro de la barra superior activo", async () => {
      const { container } = renderTable([
        makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "presente" }),
        makeAttendance({ id: 2, athlete_id: 2, athlete_name: "Laura Pérez", status: "ausente" }),
      ]);
      fireEvent.click(screen.getByRole("radio", { name: /Ausencias/i }));

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe en la fila con el campo de razón visible (debajo del control de Estado, sin columna propia)", async () => {
      const { container } = renderTable([
        makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "ausente", excuse_reason: "Cita médica" }),
      ]);
      // `AttendanceTable` renderiza card móvil + fila de escritorio a la vez
      // en jsdom (responsividad solo CSS) — ambas muestran el mismo campo de
      // razón, así que se acota a la fila de escritorio para evitar
      // "multiple elements found".
      const row = within(screen.getByTestId("attendance-row-1"));
      expect(row.getByRole("textbox", { name: /Razón de ausencia/i })).toBeInTheDocument();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe en la fila con razón visible y la alerta 'Falta razón' activa", async () => {
      const { container } = renderTable([
        makeAttendance({ id: 1, athlete_id: 1, athlete_name: "Sebastián García", status: "ausente", excuse_reason: null }),
      ]);
      expect(screen.getAllByTestId("needs-reason-alert").length).toBeGreaterThanOrEqual(1);

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
