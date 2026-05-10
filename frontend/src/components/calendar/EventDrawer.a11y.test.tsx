import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

expect.extend(toHaveNoViolations);

vi.mock("@/api/calendar", () => ({
  useCalendarEvent: vi.fn(),
  useCancelCalendarEvent: vi.fn(),
}));

import { useCalendarEvent, useCancelCalendarEvent } from "@/api/calendar";
import { EventDrawer } from "./EventDrawer";
import { makeCalendarEventRead } from "@/test/msw/calendarHandlers";

const cancelMutationStub = {
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

function renderDrawer(open = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <EventDrawer eventId={1} open={open} onOpenChange={vi.fn()} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("EventDrawer — accesibilidad", () => {
  beforeEach(() => {
    vi.mocked(useCancelCalendarEvent).mockReturnValue(
      cancelMutationStub as unknown as ReturnType<typeof useCancelCalendarEvent>,
    );
  });

  it("sin violaciones axe cuando está abierto con datos", async () => {
    const event = makeCalendarEventRead({
      title: "Copa Valle II",
      location: "Ginebra",
      description: "Segunda fecha de la copa",
      audiences: [
        { audience_type: "all_club", audience_value: {} as Record<string, never> },
      ],
    });

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: event,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    const { container } = renderDrawer();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en estado de carga", async () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    const { container } = renderDrawer();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe cuando el drawer está cerrado", async () => {
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    const { container } = renderDrawer(false);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
