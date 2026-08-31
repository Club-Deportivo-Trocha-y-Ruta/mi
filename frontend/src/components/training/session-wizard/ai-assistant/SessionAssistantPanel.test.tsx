/**
 * Tests for SessionAssistantPanel (Feature 006, Tasks T019 + T035).
 *
 * Covers:
 *   T019 — renders questions, single-select ≤1, multi-select keeps many,
 *           "Otro" reveals input, "Generar borrador" calls draft and emits values.
 *   T035 — 503 shows unavailable + continuar manualmente (no data loss);
 *           loading states; axe = 0 violations.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({
      accessToken: "tok",
      user: { id: 7, role: "coach", club_ids: [1] },
      isAuthenticated: true,
    }),
  ),
}));

// Mock the hooks to control behavior in tests
const mockClarifySpy = vi.fn();
const mockDraftSpy = vi.fn();

vi.mock("@/hooks/training/useSessionAssistant", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/training/useSessionAssistant")>(
    "@/hooks/training/useSessionAssistant",
  );
  return {
    ...actual,
    useClarify: vi.fn(() => ({
      mutateAsync: mockClarifySpy,
      isPending: false,
      error: null,
      reset: vi.fn(),
    })),
    useDraft: vi.fn(() => ({
      mutateAsync: mockDraftSpy,
      isPending: false,
      error: null,
      reset: vi.fn(),
    })),
  };
});

import {
  useClarify,
  useDraft,
  AssistantUnavailableError,
  AssistantValidationError,
} from "@/hooks/training/useSessionAssistant";
import { SessionAssistantPanel } from "./SessionAssistantPanel";
import type { AthleteOut } from "@/types/athlete.types";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";
import { Sex } from "@/types/enums";
import {
  mockClarifyResponse,
  mockDraftResponse,
} from "@/test/msw/sessionAssistantHandlers";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMPTY_FORM: TrainingSessionFormValues = {
  scheduled_date: "",
  scheduled_start_time: "",
  duration_min: 60,
  location: "",
  technical_focus: "",
  description: "",
  session_kind: "entrenamiento",
  objectives: "",
  route_text: "",
  strava_url: "",
  coach_notes: "",
  convocados_athlete_ids: [],
};

const MOCK_ROSTER: AthleteOut[] = [
  {
    id: 10,
    user_id: 100,
    first_name: "Sofía",
    last_name: "Ríos",
    birth_date: "2012-03-01", // age ~14, grupo_13_15
    sex: Sex.F,
    club_join_date: null,
    years_in_club: null,
    age_decimal: 14,
    category: "JUV-F",
    club_id: 1,
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: 11,
    user_id: 101,
    first_name: "Andrés",
    last_name: "Vega",
    birth_date: "2015-06-01", // age ~10, grupo_10_12
    sex: Sex.M,
    club_join_date: null,
    years_in_club: null,
    age_decimal: 10,
    category: "INF-M",
    club_id: 1,
    created_at: "2024-01-01T00:00:00Z",
  },
];

const onDraftReady = vi.fn();
const onContinueManually = vi.fn();

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionAssistantPanel
        clubId={1}
        roster={MOCK_ROSTER}
        currentFormValues={EMPTY_FORM}
        onDraftReady={onDraftReady}
        onContinueManually={onContinueManually}
      />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupClarifySuccess() {
  vi.mocked(useClarify).mockReturnValue({
    mutateAsync: mockClarifySpy.mockResolvedValue(mockClarifyResponse),
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useClarify>);
  vi.mocked(useDraft).mockReturnValue({
    mutateAsync: mockDraftSpy.mockResolvedValue(mockDraftResponse),
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDraft>);
}

function setupClarify503() {
  const unavailable = new AssistantUnavailableError();
  vi.mocked(useClarify).mockReturnValue({
    mutateAsync: mockClarifySpy.mockRejectedValue(unavailable),
    isPending: false,
    error: unavailable,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useClarify>);
  vi.mocked(useDraft).mockReturnValue({
    mutateAsync: mockDraftSpy,
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDraft>);
}

function setupDraft503() {
  const unavailable = new AssistantUnavailableError();
  vi.mocked(useClarify).mockReturnValue({
    mutateAsync: mockClarifySpy.mockResolvedValue(mockClarifyResponse),
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useClarify>);
  vi.mocked(useDraft).mockReturnValue({
    mutateAsync: mockDraftSpy.mockRejectedValue(unavailable),
    isPending: false,
    error: unavailable,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDraft>);
}

function setupDraft422() {
  const validationErr = new AssistantValidationError();
  vi.mocked(useClarify).mockReturnValue({
    mutateAsync: mockClarifySpy.mockResolvedValue(mockClarifyResponse),
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useClarify>);
  vi.mocked(useDraft).mockReturnValue({
    mutateAsync: mockDraftSpy.mockRejectedValue(validationErr),
    isPending: false,
    error: validationErr,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDraft>);
}

function setupLoading() {
  vi.mocked(useClarify).mockReturnValue({
    mutateAsync: mockClarifySpy,
    isPending: true,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useClarify>);
  vi.mocked(useDraft).mockReturnValue({
    mutateAsync: mockDraftSpy,
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDraft>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  onDraftReady.mockReset();
  onContinueManually.mockReset();
});

describe("SessionAssistantPanel — render inicial", () => {
  it("muestra el panel con intent textarea y botón de preguntar", () => {
    setupClarifySuccess();
    renderPanel();
    expect(screen.getByTestId("session-assistant-panel")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /qué quieres trabajar/i })).toBeInTheDocument();
    expect(screen.getByTestId("assistant-ask-btn")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-manual-btn")).toBeInTheDocument();
  });

  it("'Continuar manualmente' llama onContinueManually", () => {
    setupClarifySuccess();
    renderPanel();
    fireEvent.click(screen.getByTestId("assistant-manual-btn"));
    expect(onContinueManually).toHaveBeenCalledTimes(1);
  });
});

describe("SessionAssistantPanel — flujo clarify + draft (T019)", () => {
  it("envía intención y renderiza preguntas de clarificación", async () => {
    setupClarifySuccess();
    renderPanel();

    fireEvent.change(screen.getByRole("textbox", { name: /qué quieres trabajar/i }), {
      target: { value: "sesión técnica de bajadas" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });

    expect(await screen.findByTestId("clarify-question-q1")).toBeInTheDocument();
    expect(await screen.findByTestId("clarify-question-q2")).toBeInTheDocument();
  });

  it("single-select (q1): seleccionar una opción activa el chip; elegir otra reemplaza la anterior", async () => {
    setupClarifySuccess();
    renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");

    // In JSDOM, single-select ToggleGroup items render as role="radio"
    const chip1012 = screen.getAllByRole("radio").find(
      (el) => el.getAttribute("aria-label")?.includes("10-12 años"),
    );
    expect(chip1012).toBeDefined();

    // Select "10-12 años"
    fireEvent.click(chip1012!);
    await waitFor(() => expect(chip1012).toHaveAttribute("data-state", "on"));

    // Selecting "13-15 años" should replace the selection
    const chip1315 = screen.getAllByRole("radio").find(
      (el) => el.getAttribute("aria-label")?.includes("13-15 años"),
    );
    fireEvent.click(chip1315!);
    await waitFor(() => {
      expect(chip1315).toHaveAttribute("data-state", "on");
      expect(chip1012).toHaveAttribute("data-state", "off");
    });
  });

  it("multi-select (q2): puede mantener múltiples selecciones activas", async () => {
    setupClarifySuccess();
    renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q2");

    // q2 is multi-select — ToggleGroup items may render as role="checkbox" in jsdom
    const chipBajada = screen.getByTestId("clarify-chips-q2").querySelector(
      '[aria-label*="Técnica de bajada"]',
    );
    const chipResistencia = screen.getByTestId("clarify-chips-q2").querySelector(
      '[aria-label*="Resistencia Z1-Z2"]',
    );
    expect(chipBajada).toBeDefined();
    expect(chipResistencia).toBeDefined();

    fireEvent.click(chipBajada!);
    fireEvent.click(chipResistencia!);

    await waitFor(() => {
      expect(chipBajada).toHaveAttribute("data-state", "on");
      expect(chipResistencia).toHaveAttribute("data-state", "on");
    });
  });

  it("chip 'Otro' revela un input de texto libre", async () => {
    setupClarifySuccess();
    renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");

    // Click "Otro" chip on q1
    fireEvent.click(screen.getByTestId("clarify-otro-chip-q1"));
    expect(screen.getByTestId("clarify-other-input-q1")).toBeInTheDocument();

    // Type in the free-text
    fireEvent.change(screen.getByTestId("clarify-other-input-q1"), {
      target: { value: "Solo el grupo de 14 años" },
    });
    expect(screen.getByTestId("clarify-other-input-q1")).toHaveValue(
      "Solo el grupo de 14 años",
    );
  });

  it("'Generar borrador' llama useDraft con las respuestas y emite valores mapeados", async () => {
    setupClarifySuccess();
    renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");

    // Answer q1 (single-select) — find by aria-label
    const chip1315 = screen.getByTestId("clarify-chips-q1").querySelector(
      '[aria-label*="13-15 años"]',
    );
    fireEvent.click(chip1315!);

    // Answer q2 (multi-select) — find by aria-label
    const chipBajada = screen.getByTestId("clarify-chips-q2").querySelector(
      '[aria-label*="Técnica de bajada"]',
    );
    fireEvent.click(chipBajada!);

    // Generate draft
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-draft-btn"));
    });

    await waitFor(() => {
      expect(mockDraftSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          answers: expect.arrayContaining([
            expect.objectContaining({
              question_id: "q1",
              selected_labels: ["13-15 años"],
            }),
            expect.objectContaining({
              question_id: "q2",
              selected_labels: ["Técnica de bajada"],
            }),
          ]),
        }),
      );
      expect(onDraftReady).toHaveBeenCalledWith(
        expect.objectContaining({
          values: expect.objectContaining({
            technical_focus: "Técnica de descenso en terreno suelto",
            duration_min: 90,
            session_kind: "entrenamiento",
          }),
          seededFields: expect.any(Set),
          draftNotes: expect.any(String),
        }),
      );
    });
  });

  it("resuelve athlete_call_up=grupo_13_15 → solo atletas con edad ≥13", async () => {
    setupClarifySuccess();
    renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");

    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-draft-btn"));
    });

    await waitFor(() => {
      expect(onDraftReady).toHaveBeenCalled();
    });

    const payload = onDraftReady.mock.calls[0][0] as { values: { convocados_athlete_ids: number[] } };
    // Sofía (id 10, age ~14) should be included; Andrés (id 11, age ~10) excluded
    expect(payload.values.convocados_athlete_ids).toContain(10);
    expect(payload.values.convocados_athlete_ids).not.toContain(11);
  });
});

describe("SessionAssistantPanel — estados de carga", () => {
  it("muestra 'Pensando…' mientras carga clarify", () => {
    setupLoading();
    renderPanel();
    expect(screen.getByTestId("assistant-ask-btn")).toHaveTextContent(/pensando/i);
  });
});

describe("SessionAssistantPanel — fallback 503 (T035)", () => {
  it("503 en clarify muestra banner de no disponible + continuar manualmente", async () => {
    setupClarify503();
    renderPanel();

    // Simulate error already in state (mock returns error=unavailable)
    // The component reads error from the hook directly
    expect(screen.getByTestId("assistant-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-fallback-manual-btn")).toBeInTheDocument();
  });

  it("503 → 'Continuar manualmente' llama onContinueManually (sin pérdida de datos)", async () => {
    setupClarify503();
    renderPanel();

    fireEvent.click(screen.getByTestId("assistant-fallback-manual-btn"));
    expect(onContinueManually).toHaveBeenCalledTimes(1);
  });

  it("503 → 'Reintentar' resetea el estado de error", async () => {
    setupClarify503();
    const { rerender } = renderPanel();

    expect(screen.getByTestId("assistant-unavailable")).toBeInTheDocument();

    // After clicking retry, reset the mock to a non-error state
    vi.mocked(useClarify).mockReturnValue({
      mutateAsync: mockClarifySpy,
      isPending: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useClarify>);
    vi.mocked(useDraft).mockReturnValue({
      mutateAsync: mockDraftSpy,
      isPending: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useDraft>);

    fireEvent.click(screen.getByTestId("assistant-retry-btn"));

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <SessionAssistantPanel
          clubId={1}
          roster={MOCK_ROSTER}
          currentFormValues={EMPTY_FORM}
          onDraftReady={onDraftReady}
          onContinueManually={onContinueManually}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByTestId("assistant-unavailable")).not.toBeInTheDocument();
    });
  });

  it("503 en draft muestra banner de no disponible", async () => {
    setupDraft503();
    renderPanel();
    expect(screen.getByTestId("assistant-unavailable")).toBeInTheDocument();
  });
});

describe("SessionAssistantPanel — error 422 recuperable", () => {
  it("422 en draft muestra error inline recuperable (no unavailable banner)", async () => {
    setupDraft422();
    renderPanel();

    expect(screen.getByTestId("assistant-validation-error")).toBeInTheDocument();
    expect(screen.queryByTestId("assistant-unavailable")).not.toBeInTheDocument();
  });
});

describe("SessionAssistantPanel — accesibilidad (axe, T035)", () => {
  it("panel inicial sin violaciones de accesibilidad", async () => {
    setupClarifySuccess();
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("panel con preguntas sin violaciones de accesibilidad", async () => {
    setupClarifySuccess();
    const { container } = renderPanel();

    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("banner 503 sin violaciones de accesibilidad", async () => {
    setupClarify503();
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("banner 422 sin violaciones de accesibilidad", async () => {
    setupDraft422();
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("panel con 'Otro' revelado sin violaciones de accesibilidad", async () => {
    setupClarifySuccess();
    const { container } = renderPanel();

    await act(async () => {
      fireEvent.click(screen.getByTestId("assistant-ask-btn"));
    });
    await screen.findByTestId("clarify-question-q1");
    fireEvent.click(screen.getByTestId("clarify-otro-chip-q1"));

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
