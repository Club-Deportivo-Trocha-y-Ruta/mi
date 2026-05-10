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
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { first_name: string; last_name: string; role: string } }) => unknown) =>
    selector({
      user: { first_name: "Entrenador", last_name: "Test", role: "coach" },
    }),
}));

import { useCalendarEvents, useCalendarEvent, useCancelCalendarEvent } from "@/api/calendar";
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
    vi.mocked(useCancelCalendarEvent).mockReturnValue(
      noopMutation as unknown as ReturnType<typeof useCancelCalendarEvent>,
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
    } as unknown as ReturnType<typeof useCalendarEvents>);

    renderPage();
    expect(
      screen.getByText(/No se pudieron cargar los eventos/i),
    ).toBeInTheDocument();
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
});
