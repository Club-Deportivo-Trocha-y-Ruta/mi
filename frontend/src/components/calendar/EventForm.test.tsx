import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock("@/api/calendar", () => ({
  useCreateCalendarEvent: vi.fn(),
  useUpdateCalendarEvent: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({
    data: {
      items: [
        { id: 1, first_name: "Sebastián", last_name: "García", age_decimal: 13.2, category: "Pre-juvenil A" },
      ],
    },
    isLoading: false,
  }),
}));

import { useCreateCalendarEvent, useUpdateCalendarEvent } from "@/api/calendar";
import { EventForm } from "./EventForm";

const mutateAsync = vi.fn();
const mutationStub = {
  mutateAsync,
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  isIdle: true,
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

function renderForm(
  mode: "create" | "edit" = "create",
  onSuccess = vi.fn(),
  onCancel = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <EventForm mode={mode} onSuccess={onSuccess} onCancel={onCancel} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventForm", () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    vi.mocked(useCreateCalendarEvent).mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useCreateCalendarEvent>,
    );
    vi.mocked(useUpdateCalendarEvent).mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useUpdateCalendarEvent>,
    );
  });

  it("renders event type selector", () => {
    renderForm();
    expect(screen.getByText("Tipo de evento")).toBeInTheDocument();
    expect(screen.getByText("Entrenamiento")).toBeInTheDocument();
    expect(screen.getByText("Competencia")).toBeInTheDocument();
    expect(screen.getByText("Evento del club")).toBeInTheDocument();
  });

  it("renders basic tab fields", () => {
    renderForm();
    expect(screen.getByLabelText(/Título/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Hora inicio/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Duración/i)).toBeInTheDocument();
  });

  it("shows validation error when title is empty on submit", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /Crear evento/i }));

    await waitFor(() => {
      expect(screen.getByText(/requerido/i)).toBeInTheDocument();
    });
  });

  it("calls createMutation on valid club_event submit", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    mutateAsync.mockResolvedValue({ id: 99 });
    renderForm("create", onSuccess);

    // Select club_event type
    await user.click(screen.getByText("Evento del club"));

    // Fill title
    await user.type(screen.getByLabelText(/Título/i), "Asamblea anual");

    // Fill date
    const dateInput = screen.getByLabelText(/Fecha/i);
    await user.clear(dateInput);
    await user.type(dateInput, "2026-06-01");

    // Fill time
    const timeInput = screen.getByLabelText(/Hora inicio/i);
    await user.clear(timeInput);
    await user.type(timeInput, "18:00");

    // Fill duration
    const durationInput = screen.getByLabelText(/Duración/i);
    await user.clear(durationInput);
    await user.type(durationInput, "120");

    // Click create
    await user.click(screen.getByRole("button", { name: /Crear evento/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalled();
    });
  });

  it("calls onCancel when cancel button is clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderForm("create", vi.fn(), onCancel);

    await user.click(screen.getByRole("button", { name: /Cancelar/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows competition-specific fields when competition type is selected", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));

    // Navigate to specific tab
    await user.click(screen.getByText("Datos específicos"));

    expect(screen.getByLabelText(/Ciudad/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Categoría de carrera/i)).toBeInTheDocument();
  });

  it("shows rest_day fields when rest_day type is selected", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Día de descanso"));
    await user.click(screen.getByText("Datos específicos"));

    expect(screen.getByLabelText(/Alcance/i)).toBeInTheDocument();
  });

  it("shows personal_training fields when personal_training type is selected", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Entrenamiento personal"));
    await user.click(screen.getByText("Datos específicos"));

    expect(screen.getByLabelText(/Intensidad/i)).toBeInTheDocument();
  });

  it("shows error message when mutation fails", async () => {
    vi.mocked(useCreateCalendarEvent).mockReturnValue({
      ...mutationStub,
      isError: true,
    } as unknown as ReturnType<typeof useCreateCalendarEvent>);

    renderForm();
    expect(
      screen.getByText(/No se pudo guardar el evento/i),
    ).toBeInTheDocument();
  });

  it("shows 'Guardar cambios' button in edit mode", () => {
    renderForm("edit");
    expect(
      screen.getByRole("button", { name: /Guardar cambios/i }),
    ).toBeInTheDocument();
  });
});
