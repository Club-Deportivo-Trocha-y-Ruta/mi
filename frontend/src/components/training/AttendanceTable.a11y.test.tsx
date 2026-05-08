import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

expect.extend(toHaveNoViolations);

vi.mock("@/api/trainingSessions", () => ({
  useUpdateAttendance: vi.fn(),
}));

import { useUpdateAttendance } from "@/api/trainingSessions";
import { AttendanceTable } from "./AttendanceTable";
import type { Attendance } from "@/types/trainingSession.types";
import { makeAttendance } from "@/test/msw/trainingHandlers";

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
});
