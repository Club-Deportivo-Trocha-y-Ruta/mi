import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ─── FullCalendar ResizeObserver polyfill ─────────────────────────────────────
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock("@/api/calendar", () => ({
  useCalendarEvents: vi.fn(),
  useCalendarEvent: vi.fn(),
  useCancelCalendarEvent: vi.fn(),
  useDeleteCalendarEventPermanent: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { first_name: string; last_name: string; role: string } }) => unknown) =>
    selector({
      user: { first_name: "Entrenador", last_name: "Test", role: "coach" },
    }),
}));

// useNavigate is mocked (partial mock — MemoryRouter/Link stay real) so the
// handleDateClick regression test can assert on the navigation call.
const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// CalendarShell wraps FullCalendar, whose dateClick is driven by real pointer
// drag hit-testing against DOM layout geometry — unavailable in jsdom (verified:
// userEvent.click() on a real FullCalendar `[data-date]` cell never fires
// onDateClick). CalendarShell's real FullCalendar rendering is already covered
// by its own dedicated CalendarShell.test.tsx, so stubbing it here to expose a
// clickable "day" trades no coverage — it just moves the interaction assertion
// to the layer that can actually observe it.
vi.mock("@/components/calendar/CalendarShell", () => ({
  CalendarShell: ({
    onDateClick,
  }: {
    onDateClick: (dateStr: string) => void;
  }) => (
    <div data-testid="calendar-shell">
      <button type="button" onClick={() => onDateClick("2026-07-15")}>
        Simular clic en día vacío
      </button>
    </div>
  ),
}));

import { useCalendarEvents, useCalendarEvent, useCancelCalendarEvent, useDeleteCalendarEventPermanent } from "@/api/calendar";
import { CalendarPage } from "./CalendarPage";
import { makeCalendarListItem } from "@/test/msw/calendarHandlers";

const noopMutation = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <CalendarPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("CalendarPage", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    vi.mocked(useCancelCalendarEvent).mockReturnValue(
      noopMutation as unknown as ReturnType<typeof useCancelCalendarEvent>,
    );
    vi.mocked(useDeleteCalendarEventPermanent).mockReturnValue(
      noopMutation as unknown as ReturnType<typeof useDeleteCalendarEventPermanent>,
    );
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);
  });

  it("renders page title", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    // "Calendario" appears in both nav link and page h1; verify at least one
    const items = screen.getAllByText("Calendario");
    expect(items.length).toBeGreaterThanOrEqual(1);
    // The h1 heading is present
    expect(screen.getByRole("heading", { name: /Calendario/i })).toBeInTheDocument();
  });

  it("shows loading skeleton while fetching", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    expect(screen.getByLabelText(/Cargando calendario/i)).toBeInTheDocument();
  });

  it("shows error message when fetch fails", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    expect(
      screen.getByText(/No se pudieron cargar los eventos/i),
    ).toBeInTheDocument();
  });

  it("retries the events query when 'Reintentar' is clicked", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      refetch,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();

    const retryButton = screen.getByRole("button", { name: /Reintentar/i });
    await user.click(retryButton);

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("renders the cold-start 'waking' copy and tone instead of the error tone when the failure looks like a cold start", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network Error"),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();

    // Cold start swaps in ErrorState's friendly "waking up" copy instead of the
    // calendar-specific error copy, and renders role=status (not role=alert)
    // with the warm/warning tone rather than the danger/red error tone.
    expect(screen.getByText(/La aplicación está iniciando/i)).toBeInTheDocument();
    expect(screen.queryByText(/No se pudieron cargar los eventos/i)).not.toBeInTheDocument();

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(status.className).toContain("warning");
    expect(status.className).not.toContain("danger");
  });

  it("renders FullCalendar when data is available", async () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [
        makeCalendarListItem(),
        makeCalendarListItem({ id: 2, event_type: "competition" }),
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
    });
  });

  it("renders view toggle buttons", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    expect(screen.getByText("Mes")).toBeInTheDocument();
    expect(screen.getByText("Semana")).toBeInTheDocument();
    expect(screen.getByText("Día")).toBeInTheDocument();
    expect(screen.getByText("Agenda")).toBeInTheDocument();
  });

  it("changes view when view button is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();

    const semanaBtn = screen.getByRole("button", { name: /Semana/i });
    await user.click(semanaBtn);

    expect(semanaBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("renders '+ Nuevo evento' link", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    const link = screen.getByRole("link", { name: /Nuevo evento/i });
    expect(link).toHaveAttribute("href", "/calendar/events/new");
  });

  it("renders filters bar", () => {
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    // Filter bar contains event type buttons
    expect(screen.getByText("Entrenamiento")).toBeInTheDocument();
  });

  it("navigates to the new-event form with the clicked date when an empty day is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(useCalendarEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();

    await user.click(
      screen.getByRole("button", { name: /Simular clic en día vacío/i }),
    );

    expect(mockNavigate).toHaveBeenCalledWith(
      "/calendar/events/new?date=2026-07-15",
    );
  });
});
