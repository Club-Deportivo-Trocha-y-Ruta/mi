import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/trainingSessions", () => ({
  useUpdateAttendance: vi.fn(),
}));

import { useUpdateAttendance } from "@/api/trainingSessions";
import { AttendanceTable } from "./AttendanceTable";
import type { Attendance } from "@/types/trainingSession.types";

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

function renderTable(
  attendances: Attendance[],
  sessionId = 10,
  disabled = false,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AttendanceTable
        sessionId={sessionId}
        attendances={attendances}
        disabled={disabled}
      />
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
      renderTable([makeAttendance()], 10, true);
      const selects = screen.getAllByRole("combobox", { name: /Estado de asistencia/i });
      selects.forEach((s) => expect(s).toBeDisabled());
    });
  });
});
