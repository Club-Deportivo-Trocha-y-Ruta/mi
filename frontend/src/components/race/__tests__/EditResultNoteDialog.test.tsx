/**
 * Tests for EditResultNoteDialog (T015) and ResultsTable note affordance (T018).
 *
 * T015 — EditResultNoteDialog:
 *  - Renders with prefilled current note when one exists.
 *  - Validation: empty (after trim) and >500 chars show localized Zod errors.
 *  - Calls setResultCoachNote on valid submit.
 *  - Shows error state when mutation rejects (no silent failure).
 *  - "Eliminar nota" button calls clearResultCoachNote.
 *  - axe zero violations on the open dialog.
 *  - Note affordance is hidden when isCoachOrAdmin=false (parent role).
 *
 * T018 — ResultsTable note UI:
 *  - Coach/admin sees coach_note preview on a row that has one.
 *  - Coach/admin row with coach_note gets edit aria-label.
 *  - Coach/admin row without coach_note gets add aria-label.
 *  - Parent role (isCoachOrAdmin=false) sees no note affordance or preview.
 *
 * Strategy:
 *  - Mock @/hooks/race/useRaceResults to avoid real TanStack Query / network.
 *  - Mock @/store/auth.store for token.
 *  - Wrap with QueryClientProvider for TanStack hooks.
 *  - Real timers for the setTimeout(1200) close delay; waitFor with extended timeout.
 *  - jest-axe via setup.ts (already extends expect).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks declared BEFORE imports that depend on them (vitest hoisting)
// ---------------------------------------------------------------------------

// Mock the mutation hooks — we test the dialog component in isolation,
// not the full TanStack Query + network stack.
const mockSetNoteMutate = vi.fn();
const mockClearNoteMutate = vi.fn();

vi.mock("@/hooks/race/useRaceResults", () => ({
  useSetResultCoachNote: () => ({
    mutate: mockSetNoteMutate,
    isPending: false,
  }),
  useClearResultCoachNote: () => ({
    mutate: mockClearNoteMutate,
    isPending: false,
  }),
  useRaceResults: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

// The AI analysis button uses useLaunchAthleteAnalysis — stub it so ResultsTable renders.
vi.mock("@/hooks/athletes/useLaunchAthleteAnalysis", () => ({
  useLaunchAthleteAnalysis: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

import { EditResultNoteDialog } from "@/components/race/EditResultNoteDialog";
import { ResultsTable } from "@/components/competitions/results/ResultsTable";
import type {
  RaceEventResultsResponse,
  RaceResultRow,
} from "@/types/raceResults.types";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeQc() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function wrap(ui: ReactNode) {
  return render(
    createElement(
      MemoryRouter,
      {},
      createElement(QueryClientProvider, { client: makeQc() }, ui),
    ),
  );
}

function makeDialogProps(overrides: Partial<React.ComponentProps<typeof EditResultNoteDialog>> = {}) {
  return {
    resultId: 1,
    displayName: "Corredor Ficticio",
    currentNote: null,
    raceEventId: 100,
    filters: {},
    open: true,
    onOpenChange: vi.fn(),
    ...overrides,
  };
}

// Minimal RaceResultRow factory
function makeRow(overrides: Partial<RaceResultRow> = {}): RaceResultRow {
  return {
    result_id: 1,
    position: 1,
    competitor_id: 1,
    display_name: "Atleta Ficticio",
    club_text: "Club TyR Ficticio",
    athlete_id: 1,
    is_our_club: true,
    status: "finished",
    race_time_ms: 200_000,
    laps_behind: null,
    points_awarded: 40,
    bib_number: null,
    coach_note: null,
    coach_note_updated_at: null,
    ...overrides,
  };
}

function makeResultsResponse(rows: RaceResultRow[]): RaceEventResultsResponse {
  return {
    race_event_id: 100,
    event_name: "VALIDA IV TEST FICTICIA",
    event_date: "2026-05-17",
    location: "Cali",
    status: "completed",
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows,
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// T015 — EditResultNoteDialog tests
// ---------------------------------------------------------------------------

describe("EditResultNoteDialog — renderiza con nota existente", () => {
  it("abre el sheet con el texto actual de la nota en el textarea", async () => {
    const existingNote = "Corredor ficticio manejó bien la bajada técnica.";
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: existingNote })} />);

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    expect(textarea).toHaveValue(existingNote);
  });

  it("abre con textarea vacío cuando no hay nota", async () => {
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    expect(textarea).toHaveValue("");
  });

  it("muestra 'Agregar nota' en el título cuando currentNote es null", async () => {
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    expect(await screen.findByText(/Agregar nota/i)).toBeInTheDocument();
  });

  it("muestra 'Editar nota' en el título cuando hay nota existente", async () => {
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: "Nota existente." })} />);

    expect(await screen.findByText(/Editar nota/i)).toBeInTheDocument();
  });
});

describe("EditResultNoteDialog — validación Zod localizada", () => {
  it("muestra error en español cuando se envía nota vacía (después de trim)", async () => {
    const user = userEvent.setup();
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    // Wait for mount
    await screen.findByRole("textbox", { name: /nota del entrenador/i });

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    const errorMsg = await screen.findByRole("alert");
    expect(errorMsg).toHaveTextContent(/no puede estar vacía/i);
    expect(mockSetNoteMutate).not.toHaveBeenCalled();
  });

  it("muestra error en español cuando la nota supera 500 caracteres", async () => {
    // The textarea has maxLength=500 which prevents the browser from accepting
    // chars beyond 500 via keyboard input. We bypass this by using fireEvent
    // to set the value programmatically, then trigger validation via submit.
    const { fireEvent: fe } = await import("@testing-library/react");
    const user = userEvent.setup();
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    // Bypass maxLength constraint: set value directly
    fe.change(textarea, { target: { value: "A".repeat(501) } });

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    const errorMsg = await screen.findByRole("alert");
    expect(errorMsg).toHaveTextContent(/500/i);
    expect(mockSetNoteMutate).not.toHaveBeenCalled();
  });

  it("no dispara mutación cuando la nota es solo espacios", async () => {
    const user = userEvent.setup();
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    await user.type(textarea, "   ");

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    // Zod .trim().min(1) rejects whitespace-only
    const errorMsg = await screen.findByRole("alert");
    expect(errorMsg).toBeInTheDocument();
    expect(mockSetNoteMutate).not.toHaveBeenCalled();
  });
});

describe("EditResultNoteDialog — submit llama a setResultCoachNote", () => {
  it("llama a setResultCoachNote con los parámetros correctos al guardar", async () => {
    const user = userEvent.setup();
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    await user.type(textarea, "Buena salida, buen ritmo ficticio.");

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    await waitFor(() => expect(mockSetNoteMutate).toHaveBeenCalledTimes(1));

    const [variables] = mockSetNoteMutate.mock.calls[0];
    expect(variables.resultId).toBe(1);
    expect(variables.raceEventId).toBe(100);
    expect(variables.coach_note).toBe("Buena salida, buen ritmo ficticio.");
  });
});

describe("EditResultNoteDialog — estado de error en mutación", () => {
  it("muestra mensaje de error cuando la mutación falla (sin cierre silencioso)", async () => {
    // Override the mock to simulate a failure via onError callback
    mockSetNoteMutate.mockImplementationOnce((_vars: unknown, callbacks: { onError?: () => void }) => {
      callbacks?.onError?.();
    });

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(
      <EditResultNoteDialog
        {...makeDialogProps({ currentNote: null, onOpenChange })}
      />,
    );

    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    await user.type(textarea, "Nota que fallará en el test.");

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(
        screen.getByText(/no se pudo guardar la nota/i),
      ).toBeInTheDocument(),
    );

    // Sheet must NOT close on error
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe("EditResultNoteDialog — botón Eliminar nota", () => {
  it("muestra botón 'Eliminar nota' solo cuando hay nota existente", async () => {
    wrap(
      <EditResultNoteDialog {...makeDialogProps({ currentNote: "Nota existente para eliminar." })} />,
    );

    expect(await screen.findByRole("button", { name: /eliminar nota/i })).toBeInTheDocument();
  });

  it("no muestra botón 'Eliminar nota' cuando currentNote es null", async () => {
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    await screen.findByRole("textbox", { name: /nota del entrenador/i }); // wait for mount
    expect(screen.queryByRole("button", { name: /eliminar nota/i })).not.toBeInTheDocument();
  });

  it("llama a clearResultCoachNote al hacer clic en 'Eliminar nota'", async () => {
    const user = userEvent.setup();
    wrap(
      <EditResultNoteDialog {...makeDialogProps({ currentNote: "Nota a eliminar." })} />,
    );

    const deleteBtn = await screen.findByRole("button", { name: /eliminar nota/i });
    await user.click(deleteBtn);

    await waitFor(() => expect(mockClearNoteMutate).toHaveBeenCalledTimes(1));
    const [variables] = mockClearNoteMutate.mock.calls[0];
    expect(variables.resultId).toBe(1);
    expect(variables.raceEventId).toBe(100);
  });

  it("muestra mensaje de error cuando clearResultCoachNote falla", async () => {
    mockClearNoteMutate.mockImplementationOnce((_vars: unknown, callbacks: { onError?: () => void }) => {
      callbacks?.onError?.();
    });

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(
      <EditResultNoteDialog
        {...makeDialogProps({
          currentNote: "Nota a eliminar con fallo.",
          onOpenChange,
        })}
      />,
    );

    const deleteBtn = await screen.findByRole("button", { name: /eliminar nota/i });
    await user.click(deleteBtn);

    await waitFor(() =>
      expect(
        screen.getByText(/no se pudo eliminar la nota/i),
      ).toBeInTheDocument(),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe("EditResultNoteDialog — accesibilidad (a11y)", () => {
  it("dialog abierto: 0 violaciones axe en el sheet", async () => {
    wrap(
      <EditResultNoteDialog
        {...makeDialogProps({ currentNote: "Nota de accesibilidad." })}
      />,
    );

    // Wait for portal to mount
    await screen.findByRole("textbox", { name: /nota del entrenador/i });

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("dialog sin nota: 0 violaciones axe", async () => {
    wrap(<EditResultNoteDialog {...makeDialogProps({ currentNote: null })} />);

    await screen.findByRole("textbox", { name: /nota del entrenador/i });

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});

// ---------------------------------------------------------------------------
// T018 — ResultsTable note affordance tests
// ---------------------------------------------------------------------------

describe("ResultsTable — affordance de nota para coach/admin", () => {
  it("muestra preview de coach_note en la fila cuando hay nota y es coach", async () => {
    const noteText = "Corredor ficticio realizó buena entrada en curvas.";
    const data = makeResultsResponse([makeRow({ coach_note: noteText })]);

    wrap(
      <ResultsTable data={data} isCoachOrAdmin={true} />,
    );

    // The note preview appears inline in the club row (may appear twice:
    // once for mobile layout, once for desktop layout — both are valid).
    const notes = await screen.findAllByText(noteText);
    expect(notes.length).toBeGreaterThan(0);
  });

  it("muestra aria-label de edición cuando la fila ya tiene nota", async () => {
    const data = makeResultsResponse([
      makeRow({ coach_note: "Nota existente de prueba." }),
    ]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={true} />);

    // Button aria-label references "Editar nota de ..."
    expect(
      await screen.findByRole("button", { name: /editar nota de atleta ficticio/i }),
    ).toBeInTheDocument();
  });

  it("muestra aria-label de agregar cuando la fila no tiene nota", async () => {
    const data = makeResultsResponse([makeRow({ coach_note: null })]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={true} />);

    expect(
      await screen.findByRole("button", { name: /agregar nota para atleta ficticio/i }),
    ).toBeInTheDocument();
  });

  it("abre EditResultNoteDialog con nota actual al hacer clic en el botón de nota", async () => {
    const user = userEvent.setup();
    const existingNote = "Nota prefill para el diálogo ficticio.";
    const data = makeResultsResponse([
      makeRow({ coach_note: existingNote }),
    ]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={true} />);

    const editBtn = await screen.findByRole("button", {
      name: /editar nota de atleta ficticio/i,
    });
    await user.click(editBtn);

    // Dialog opens and prefills with existing note
    const textarea = await screen.findByRole("textbox", { name: /nota del entrenador/i });
    expect(textarea).toHaveValue(existingNote);
  });

  it("muestra affordance de agregar cuando coach_note es null", async () => {
    const data = makeResultsResponse([makeRow({ coach_note: null })]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={true} />);

    // Add note button exists for null-note rows
    expect(
      await screen.findByRole("button", {
        name: /agregar nota para atleta ficticio/i,
      }),
    ).toBeInTheDocument();
  });
});

describe("ResultsTable — sin affordance de nota para rol padre", () => {
  it("no muestra botones de nota cuando isCoachOrAdmin=false", async () => {
    // Rival row: is_our_club=false, no note button rendered
    const rivalRow = makeRow({
      competitor_id: 2,
      athlete_id: null,
      is_our_club: false,
      coach_note: null,
    });
    // Club row: is_our_club=true but isCoachOrAdmin=false → no button
    const clubRow = makeRow({ coach_note: "Nota para el coach." });
    const data = makeResultsResponse([clubRow, rivalRow]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={false} />);

    // Actions column is not rendered
    expect(screen.queryByRole("button", { name: /agregar nota/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /editar nota/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /eliminar nota/i })).not.toBeInTheDocument();
  });

  it("no muestra preview de nota cuando isCoachOrAdmin=false", async () => {
    const noteText = "Esta nota no debe ver el padre.";
    const data = makeResultsResponse([makeRow({ coach_note: noteText })]);

    wrap(<ResultsTable data={data} isCoachOrAdmin={false} />);

    // Give it a moment to render
    await screen.findByText("Atleta Ficticio");
    expect(screen.queryByText(noteText)).not.toBeInTheDocument();
  });
});
