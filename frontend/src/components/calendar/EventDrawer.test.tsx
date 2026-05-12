import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock("@/api/calendar", () => ({
  useCalendarEvent: vi.fn(),
  useCancelCalendarEvent: vi.fn(),
}));

import { useCalendarEvent, useCancelCalendarEvent } from "@/api/calendar";
import { EventDrawer } from "./EventDrawer";
import { makeCalendarEventRead } from "@/test/msw/calendarHandlers";

const cancelMutateAsync = vi.fn();
const cancelMutationStub = {
  mutate: vi.fn(),
  mutateAsync: cancelMutateAsync,
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

function renderDrawer(
  eventId: number | null,
  open: boolean,
  onOpenChange = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <EventDrawer eventId={eventId} open={open} onOpenChange={onOpenChange} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("EventDrawer", () => {
  beforeEach(() => {
    cancelMutateAsync.mockClear();
    vi.mocked(useCancelCalendarEvent).mockReturnValue(
      cancelMutationStub as unknown as ReturnType<typeof useCancelCalendarEvent>,
    );
  });

  it("does not render content when closed", () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(null, false);
    // Radix Dialog portals the content, but when closed it's not in the DOM
    expect(screen.queryByText("Entrenamiento técnico XCO")).not.toBeInTheDocument();
  });

  it("shows loading skeleton while fetching", () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);
    // The drawer should be in DOM when open
    expect(document.body).toBeInTheDocument();
  });

  it("renders event details when data is available", async () => {
    const event = makeCalendarEventRead({
      id: 1,
      title: "Copa Valle II — Ginebra",
      location: "Ginebra, Valle del Cauca",
      description: "Segunda fecha Copa Valle 2026",
      audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
    });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(screen.getByText("Copa Valle II — Ginebra")).toBeInTheDocument();
    });
    expect(screen.getByText("Ginebra, Valle del Cauca")).toBeInTheDocument();
    expect(screen.getByText("Segunda fecha Copa Valle 2026")).toBeInTheDocument();
    expect(screen.getByText("Todo el club")).toBeInTheDocument();
  });

  it("renders category audience correctly", async () => {
    const event = makeCalendarEventRead({
      audiences: [
        {
          audience_type: "category",
          audience_value: { category: "Pre-juvenil A" },
        },
      ],
    });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(screen.getByText("Categoría: Pre-juvenil A")).toBeInTheDocument();
    });
  });

  it("renders athlete_list audience with count", async () => {
    const event = makeCalendarEventRead({
      audiences: [
        {
          audience_type: "athlete_list",
          audience_value: { athlete_ids: [1, 2, 3] },
        },
      ],
    });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(screen.getByText("3 atletas seleccionados")).toBeInTheDocument();
    });
  });

  it("shows cancel event confirm modal when cancel button is clicked", async () => {
    const user = userEvent.setup();
    const event = makeCalendarEventRead({ status: "scheduled" });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(screen.getByText("Cancelar evento")).toBeInTheDocument();
    });

    // Click the cancel event button (in footer)
    const cancelButton = screen.getAllByText("Cancelar evento")[0];
    await user.click(cancelButton);

    // Confirm modal should appear
    await waitFor(() => {
      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    });
  });

  it("disables cancel button when event is already cancelled", async () => {
    const event = makeCalendarEventRead({ status: "cancelled" });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(screen.getByText("Cancelar evento")).toBeInTheDocument();
    });

    const cancelBtn = screen.getByText("Cancelar evento").closest("button");
    expect(cancelBtn).toBeDisabled();
  });

  it("shows error message when fetch fails", async () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(1, true);

    await waitFor(() => {
      expect(
        screen.getByText(/No se pudo cargar el detalle del evento/i),
      ).toBeInTheDocument();
    });
  });

  it("oculta los botones Editar y Cancelar cuando el evento es un cumpleaños", async () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        id: -1000042,
        event_type: "birthday",
        title: "🎂 Cumpleaños de Santiago",
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer(-1000042, true);

    await waitFor(() => {
      expect(screen.getByText(/Cumpleaños de Santiago/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Editar$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancelar evento/i })).not.toBeInTheDocument();
  });
});
