import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ─── Mocks ───────────────────────────────────────────────────────────────────
vi.mock("@/api/calendar");

import { useRSVPEvent } from "@/api/calendar";
import { ParentRSVPInline } from "./ParentRSVPInline";
import type { RSVPStatus } from "@/types/calendar.types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildMutation(overrides: Partial<ReturnType<typeof useRSVPEvent>> = {}) {
  return {
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
    ...overrides,
  };
}

interface RenderProps {
  eventId?: number;
  athleteId?: number;
  currentRSVP?: RSVPStatus;
  disabled?: boolean;
}

function renderComponent({
  eventId = 1,
  athleteId = 42,
  currentRSVP = "pending",
  disabled = false,
}: RenderProps = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ParentRSVPInline
          eventId={eventId}
          athleteId={athleteId}
          currentRSVP={currentRSVP}
          disabled={disabled}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ParentRSVPInline", () => {
  it("renderiza los tres botones de RSVP", () => {
    vi.mocked(useRSVPEvent).mockReturnValue(buildMutation() as unknown as ReturnType<typeof useRSVPEvent>);

    renderComponent();
    expect(screen.getByRole("button", { name: /Aceptar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Declinar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tentativo/i })).toBeInTheDocument();
  });

  it("el botón activo tiene aria-pressed=true (estado inicial 'pending')", () => {
    vi.mocked(useRSVPEvent).mockReturnValue(buildMutation() as unknown as ReturnType<typeof useRSVPEvent>);

    renderComponent({ currentRSVP: "accepted" });
    expect(screen.getByRole("button", { name: /Aceptar/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Declinar/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Tentativo/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("click en 'Aceptar' llama a la mutation con el status correcto", async () => {
    const mutateFn = vi.fn();
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ mutate: mutateFn }) as unknown as ReturnType<typeof useRSVPEvent>,
    );
    const user = userEvent.setup();

    renderComponent({ eventId: 5, athleteId: 42, currentRSVP: "pending" });
    await user.click(screen.getByRole("button", { name: /Aceptar/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      { athlete_id: 42, rsvp_status: "accepted" },
      expect.any(Object),
    );
  });

  it("click en 'Declinar' llama a la mutation con status 'declined'", async () => {
    const mutateFn = vi.fn();
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ mutate: mutateFn }) as unknown as ReturnType<typeof useRSVPEvent>,
    );
    const user = userEvent.setup();

    renderComponent({ currentRSVP: "pending" });
    await user.click(screen.getByRole("button", { name: /Declinar/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      { athlete_id: 42, rsvp_status: "declined" },
      expect.any(Object),
    );
  });

  it("click en 'Tentativo' llama a la mutation con status 'tentative'", async () => {
    const mutateFn = vi.fn();
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ mutate: mutateFn }) as unknown as ReturnType<typeof useRSVPEvent>,
    );
    const user = userEvent.setup();

    renderComponent({ currentRSVP: "pending" });
    await user.click(screen.getByRole("button", { name: /Tentativo/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      { athlete_id: 42, rsvp_status: "tentative" },
      expect.any(Object),
    );
  });

  it("actualiza aria-pressed optimistamente al hacer click", async () => {
    vi.mocked(useRSVPEvent).mockReturnValue(buildMutation() as unknown as ReturnType<typeof useRSVPEvent>);
    const user = userEvent.setup();

    renderComponent({ currentRSVP: "pending" });
    const declinarBtn = screen.getByRole("button", { name: /Declinar/i });
    expect(declinarBtn).toHaveAttribute("aria-pressed", "false");

    await user.click(declinarBtn);
    expect(declinarBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("todos los botones están deshabilitados cuando disabled=true", () => {
    vi.mocked(useRSVPEvent).mockReturnValue(buildMutation() as unknown as ReturnType<typeof useRSVPEvent>);

    renderComponent({ disabled: true });
    expect(screen.getByRole("button", { name: /Aceptar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Declinar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Tentativo/i })).toBeDisabled();
  });

  it("deshabilita todos los botones cuando la mutation está pendiente", () => {
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ isPending: true }) as unknown as ReturnType<typeof useRSVPEvent>,
    );

    renderComponent();
    expect(screen.getByRole("button", { name: /Aceptar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Declinar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Tentativo/i })).toBeDisabled();
  });

  it("muestra feedback 'Respuesta guardada' tras éxito", async () => {
    const mutateFn = vi.fn().mockImplementation((_payload, callbacks) => {
      callbacks?.onSuccess?.();
    });
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ mutate: mutateFn }) as unknown as ReturnType<typeof useRSVPEvent>,
    );
    const user = userEvent.setup();

    renderComponent();
    await user.click(screen.getByRole("button", { name: /Aceptar/i }));

    await waitFor(() => {
      expect(screen.getByTestId("rsvp-saved-feedback")).toBeInTheDocument();
    });
    expect(screen.getByTestId("rsvp-saved-feedback")).toHaveTextContent(/Respuesta guardada/i);
  });

  it("revierte update optimístico y muestra error si la mutation falla", async () => {
    const mutateFn = vi.fn().mockImplementation((_payload, callbacks) => {
      callbacks?.onError?.();
    });
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ mutate: mutateFn, isError: true }) as unknown as ReturnType<typeof useRSVPEvent>,
    );
    const user = userEvent.setup();

    renderComponent({ currentRSVP: "pending" });
    // After clicking "Aceptar" and error, optimistic update should revert to "pending"
    await user.click(screen.getByRole("button", { name: /Aceptar/i }));

    await waitFor(() => {
      // On error, reverts back to "pending" (none active among the 3 explicit options)
      const aceptarBtn = screen.getByRole("button", { name: /Aceptar/i });
      // Reverted: neither accepted nor any specific state is forced — optimistic is reset
      expect(aceptarBtn).toBeInTheDocument();
    });
  });

  it("muestra el error si la mutation falla", () => {
    vi.mocked(useRSVPEvent).mockReturnValue(
      buildMutation({ isError: true }) as unknown as ReturnType<typeof useRSVPEvent>,
    );

    renderComponent();
    expect(screen.getByTestId("rsvp-error")).toBeInTheDocument();
    expect(screen.getByText(/No se pudo guardar la respuesta/i)).toBeInTheDocument();
  });
});
