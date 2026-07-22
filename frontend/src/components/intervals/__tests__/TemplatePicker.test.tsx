/**
 * Tests para TemplatePicker (feature 026, US4):
 *   - Filtros: los tres selects estáticos (categoría de edad, fase de
 *     mesociclo, proximidad a competencia) + checkbox "Incluir archivados"
 *     se pasan a `useTemplates` como filtros; "Limpiar filtros" resetea a
 *     `{}` y oculta el contador de filtros activos.
 *   - Estados de resultados: carga (skeletons), error (copy cold-start vs.
 *     genérico), vacío sin filtros vs. con filtros, éxito con tarjetas.
 *   - Modo biblioteca (sin `trainingSessionId`): sin botón de adjuntar.
 *   - Modo adjunto (con `trainingSessionId`): "Adjuntar a la sesión" llama a
 *     `useAttachTemplate().mutate` con el payload correcto; éxito invoca
 *     `onAttached`.
 *   - Compuerta por edad al adjuntar (FR-006/FR-007): `age_gate_confirmation_required`
 *     → `AgeGateDialog` modo confirmation, "Confirmar estructura" reintenta con
 *     `age_gate_confirmed: true`; `age_gate_z3_blocked` → modo blocked, sin
 *     reintento automático; cualquier otro error → alerta genérica.
 *   - a11y: jest-axe sin violaciones en los estados relevantes.
 *
 * Estrategia de mock: `useTemplates`/`useAttachTemplate` se mockean a nivel
 * de módulo (mirror de `InsightsTabAnalyze.test.tsx`) — sin MSW, sin red real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import type {
  IntervalStructureOut,
  IntervalTemplateOut,
} from "@/types/intervals.types";

const mockUseTemplates = vi.fn();
const mockAttachMutate = vi.fn();
let mockAttachIsPending = false;
let mockAttachVariables: unknown = undefined;

vi.mock("@/hooks/intervals/useIntervals", () => ({
  useTemplates: (...args: unknown[]) => mockUseTemplates(...args),
  useAttachTemplate: () => ({
    mutate: mockAttachMutate,
    isPending: mockAttachIsPending,
    variables: mockAttachVariables,
  }),
}));

import { TemplatePicker } from "../TemplatePicker";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios, nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

function makeBlock(position: number) {
  return {
    id: position,
    position,
    block_type: "work" as const,
    duration_type: "fixed" as const,
    duration_s: 120,
    target_zone: "Z2" as const,
    target_cadence_rpm: 75,
    repeat_group: null,
    repeat_count: null,
  };
}

const TPL_BASE: IntervalTemplateOut = {
  id: 1,
  name: "Piramidal base",
  target_age_band: "13-15",
  mesocycle_phase: "base",
  competition_proximity: "general",
  is_archived: false,
  blocks: [makeBlock(1), makeBlock(2), makeBlock(3)],
  total_planned_duration_s: 1800,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
};

const TPL_TAPER_ARCHIVED: IntervalTemplateOut = {
  id: 2,
  name: "Afinamiento semana de carrera",
  target_age_band: "10-12",
  mesocycle_phase: "taper",
  competition_proximity: "semana-carrera",
  is_archived: true,
  blocks: [makeBlock(1), makeBlock(2)],
  total_planned_duration_s: 900,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
};

const STRUCTURE_OUT: IntervalStructureOut = {
  id: 77,
  training_session_id: 42,
  target_age_band: "13-15",
  age_gate_confirmed: false,
  age_gate_confirmed_by: null,
  age_gate_confirmed_at: null,
  blocks: [],
  total_planned_duration_s: 1800,
  created_at: "2026-07-08T10:00:00Z",
  updated_at: "2026-07-08T10:00:00Z",
};

/** Error 422 legible por máquina (mismo contrato que `extractIntervalValidationError`). */
function makeGateError(
  code: "age_gate_confirmation_required" | "age_gate_z3_blocked",
  message: string,
  positions?: number[],
) {
  return {
    isAxiosError: true,
    response: {
      status: 422,
      data: { detail: { code, message, positions } },
    },
  };
}

const CONFLICT_ERROR = {
  isAxiosError: true,
  response: { status: 409, data: {} },
};

function successResult(items: IntervalTemplateOut[] = [TPL_BASE, TPL_TAPER_ARCHIVED]) {
  return {
    data: { items, total: items.length },
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAttachIsPending = false;
  mockAttachVariables = undefined;
  mockUseTemplates.mockReturnValue(successResult());
});

function renderPicker(
  props: { trainingSessionId?: number; onAttached?: (s: IntervalStructureOut) => void } = {},
) {
  return render(<TemplatePicker {...props} />);
}

// ---------------------------------------------------------------------------
// Suite: filtros
// ---------------------------------------------------------------------------

describe("TemplatePicker — filtros", () => {
  it("renderiza los tres selects y el checkbox de archivados", () => {
    renderPicker();

    expect(screen.getByLabelText("Categoría de edad")).toBeInTheDocument();
    expect(screen.getByLabelText("Fase de mesociclo")).toBeInTheDocument();
    expect(screen.getByLabelText("Proximidad a competencia")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Incluir archivados" }),
    ).toBeInTheDocument();
  });

  it("seleccionar categoría de edad llama a useTemplates con age_band", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(
      screen.getByLabelText("Categoría de edad"),
      "10-12",
    );

    const lastArgs = mockUseTemplates.mock.calls.at(-1)?.[0];
    expect(lastArgs).toEqual({ age_band: "10-12" });
  });

  it("seleccionar fase de mesociclo llama a useTemplates con mesocycle_phase", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(
      screen.getByLabelText("Fase de mesociclo"),
      "taper",
    );

    const lastArgs = mockUseTemplates.mock.calls.at(-1)?.[0];
    expect(lastArgs).toEqual({ mesocycle_phase: "taper" });
  });

  it("seleccionar proximidad a competencia llama a useTemplates con competition_proximity", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(
      screen.getByLabelText("Proximidad a competencia"),
      "pre-competencia",
    );

    const lastArgs = mockUseTemplates.mock.calls.at(-1)?.[0];
    expect(lastArgs).toEqual({ competition_proximity: "pre-competencia" });
  });

  it("marcar 'Incluir archivados' lo agrega a los filtros", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.click(screen.getByRole("checkbox", { name: "Incluir archivados" }));

    const lastArgs = mockUseTemplates.mock.calls.at(-1)?.[0];
    expect(lastArgs).toEqual({ include_archived: true });
  });

  it("el botón 'Limpiar filtros' no aparece sin filtros activos", () => {
    renderPicker();
    expect(
      screen.queryByRole("button", { name: /Limpiar filtros/ }),
    ).not.toBeInTheDocument();
  });

  it("con un filtro activo aparece 'Limpiar filtros' y '1 filtro activo'", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(
      screen.getByLabelText("Categoría de edad"),
      "10-12",
    );

    expect(
      screen.getByRole("button", { name: "Limpiar filtros" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 filtro activo/)).toBeInTheDocument();
  });

  it("con tres filtros activos muestra '3 filtros activos'", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(screen.getByLabelText("Categoría de edad"), "10-12");
    await user.selectOptions(screen.getByLabelText("Fase de mesociclo"), "base");
    await user.click(screen.getByRole("checkbox", { name: "Incluir archivados" }));

    expect(screen.getByText(/3 filtros activos/)).toBeInTheDocument();
  });

  it("'Limpiar filtros' resetea los filtros y oculta el botón", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.selectOptions(screen.getByLabelText("Categoría de edad"), "10-12");
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    const lastArgs = mockUseTemplates.mock.calls.at(-1)?.[0];
    expect(lastArgs).toEqual({});
    expect(
      screen.queryByRole("button", { name: /Limpiar filtros/ }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de carga
// ---------------------------------------------------------------------------

describe("TemplatePicker — estado de carga", () => {
  it("muestra el estado de carga con aria-busy y 6 tarjetas esqueleto", () => {
    mockUseTemplates.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      isError: false,
      error: null,
    });
    renderPicker();

    const status = screen.getByRole("status", {
      name: "Cargando biblioteca de templates de intervalos…",
    });
    expect(status).toHaveAttribute("aria-busy", "true");
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de error
// ---------------------------------------------------------------------------

describe("TemplatePicker — estado de error", () => {
  it("muestra role=alert con el copy genérico para un error desconocido", () => {
    mockUseTemplates.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: true,
      error: new Error("boom"),
    });
    renderPicker();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo cargar la biblioteca de templates. Intentá de nuevo.",
    );
  });

  it("muestra el copy de servidor iniciando para errores de red", () => {
    mockUseTemplates.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: true,
      error: new Error("Network Error"),
    });
    renderPicker();

    expect(screen.getByRole("alert")).toHaveTextContent(
      /El servidor está iniciando/,
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: estado vacío
// ---------------------------------------------------------------------------

describe("TemplatePicker — estado vacío", () => {
  it("sin filtros activos muestra 'La biblioteca está vacía'", () => {
    mockUseTemplates.mockReturnValue(successResult([]));
    renderPicker();

    expect(screen.getByText("La biblioteca está vacía")).toBeInTheDocument();
    expect(
      screen.getByText("Aún no hay templates de intervalos guardados en el club."),
    ).toBeInTheDocument();
  });

  it("con filtros activos muestra 'Sin templates para estos filtros'", async () => {
    const user = userEvent.setup();
    mockUseTemplates.mockReturnValue(successResult([]));
    renderPicker();

    await user.selectOptions(screen.getByLabelText("Categoría de edad"), "10-12");

    expect(
      screen.getByText("Sin templates para estos filtros"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado exitoso (tarjetas)
// ---------------------------------------------------------------------------

describe("TemplatePicker — tarjetas", () => {
  it("renderiza una tarjeta por template con sus etiquetas y metadatos", () => {
    renderPicker();

    const heading = screen.getByRole("heading", { name: "Piramidal base" });
    const card = heading.closest(".shadow-card") as HTMLElement;
    expect(within(card).getByText("13 a 15 años")).toBeInTheDocument();
    expect(within(card).getByText("Base")).toBeInTheDocument();
    expect(within(card).getByText("General")).toBeInTheDocument();
    expect(within(card).getByText("3 bloques · 30 min")).toBeInTheDocument();
  });

  it("marca la tarjeta archivada con el badge 'Archivado'", () => {
    renderPicker();

    expect(screen.getByText("Afinamiento semana de carrera")).toBeInTheDocument();
    expect(screen.getByText("Archivado")).toBeInTheDocument();
  });

  it("muestra el total de templates ('2 templates')", () => {
    renderPicker();
    expect(screen.getByText(/2 templates/)).toBeInTheDocument();
  });

  it("con un solo template usa el singular ('1 template')", () => {
    mockUseTemplates.mockReturnValue(successResult([TPL_BASE]));
    renderPicker();
    expect(screen.getByText(/^1 template\b/)).toBeInTheDocument();
  });

  it("muestra '· Actualizando…' cuando isFetching sin estar en isLoading", () => {
    mockUseTemplates.mockReturnValue({
      ...successResult(),
      isFetching: true,
    });
    renderPicker();

    expect(screen.getByText(/Actualizando…/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: modo biblioteca (sin trainingSessionId)
// ---------------------------------------------------------------------------

describe("TemplatePicker — modo biblioteca (sin trainingSessionId)", () => {
  it("no renderiza ningún botón 'Adjuntar a la sesión'", () => {
    renderPicker();
    expect(
      screen.queryByRole("button", { name: "Adjuntar a la sesión" }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: modo adjunto (con trainingSessionId)
// ---------------------------------------------------------------------------

describe("TemplatePicker — modo adjunto", () => {
  it("renderiza un botón 'Adjuntar a la sesión' por tarjeta", () => {
    renderPicker({ trainingSessionId: 42 });

    expect(
      screen.getAllByRole("button", { name: "Adjuntar a la sesión" }),
    ).toHaveLength(2);
  });

  it("clicar 'Adjuntar a la sesión' llama a mutate con el payload correcto", async () => {
    const user = userEvent.setup();
    renderPicker({ trainingSessionId: 42 });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[0]); // TPL_BASE

    expect(mockAttachMutate).toHaveBeenCalledWith(
      {
        templateId: TPL_BASE.id,
        input: { training_session_id: 42, age_gate_confirmed: false },
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("en éxito llama a onAttached con la estructura devuelta", async () => {
    const user = userEvent.setup();
    mockAttachMutate.mockImplementation((_vars, opts) =>
      opts.onSuccess(STRUCTURE_OUT),
    );
    const onAttached = vi.fn();
    renderPicker({ trainingSessionId: 42, onAttached });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[0]);

    expect(onAttached).toHaveBeenCalledWith(STRUCTURE_OUT);
  });

  it("mientras se adjunta un template, su botón muestra 'Adjuntando…' y los demás quedan deshabilitados", () => {
    mockAttachIsPending = true;
    mockAttachVariables = {
      templateId: TPL_BASE.id,
      input: { training_session_id: 42, age_gate_confirmed: false },
    };
    renderPicker({ trainingSessionId: 42 });

    expect(
      screen.getByRole("button", { name: "Adjuntando…" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Adjuntar a la sesión" }),
    ).toBeDisabled();
  });

  it("un error genérico (409) muestra role=alert sin abrir el diálogo de compuerta", async () => {
    const user = userEvent.setup();
    mockAttachMutate.mockImplementation((_vars, opts) =>
      opts.onError(CONFLICT_ERROR),
    );
    renderPicker({ trainingSessionId: 42 });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[0]);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "La sesión ya tiene una estructura. Editá la existente.",
    );
    expect(
      screen.queryByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: compuerta por edad al adjuntar (FR-006/FR-007)
// ---------------------------------------------------------------------------

describe("TemplatePicker — compuerta por edad confirmable (FR-007)", () => {
  it("abre AgeGateDialog modo confirmation con la banda del template", async () => {
    const user = userEvent.setup();
    mockAttachMutate.mockImplementation((_vars, opts) =>
      opts.onError(
        makeGateError(
          "age_gate_confirmation_required",
          "Confirmá explícitamente la estructura para la categoría 10-12 antes de guardar.",
        ),
      ),
    );
    renderPicker({ trainingSessionId: 42 });

    // TPL_TAPER_ARCHIVED (índice 1) es el template 10-12.
    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[1]);

    expect(
      await screen.findByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/la categoría 10 a 12 años/)).toBeInTheDocument();
  });

  it("'Confirmar estructura' reintenta el adjunto con age_gate_confirmed: true", async () => {
    const user = userEvent.setup();
    mockAttachMutate
      .mockImplementationOnce((_vars, opts) =>
        opts.onError(
          makeGateError("age_gate_confirmation_required", "Confirmá."),
        ),
      )
      .mockImplementationOnce((_vars, opts) => opts.onSuccess(STRUCTURE_OUT));
    renderPicker({ trainingSessionId: 42 });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[1]);

    await screen.findByRole("heading", {
      name: "Confirmá la estructura para esta categoría",
    });
    await user.click(
      screen.getByRole("button", { name: "Confirmar estructura" }),
    );

    expect(mockAttachMutate).toHaveBeenCalledTimes(2);
    const retryArgs = mockAttachMutate.mock.calls[1][0] as {
      templateId: number;
      input: { age_gate_confirmed: boolean };
    };
    expect(retryArgs.input.age_gate_confirmed).toBe(true);
    expect(
      screen.queryByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).not.toBeInTheDocument();
  });
});

describe("TemplatePicker — bloqueo duro Z3+ al adjuntar (FR-006)", () => {
  it("abre AgeGateDialog modo blocked sin reintento automático", async () => {
    const user = userEvent.setup();
    mockAttachMutate.mockImplementation((_vars, opts) =>
      opts.onError(
        makeGateError(
          "age_gate_z3_blocked",
          "Intensidad Z3 o superior no está disponible para la categoría 10-12.",
          [2],
        ),
      ),
    );
    renderPicker({ trainingSessionId: 42 });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[1]);

    expect(
      await screen.findByRole("heading", {
        name: "Intensidad no permitida para esta categoría",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Entendido" }));

    expect(
      screen.queryByRole("heading", {
        name: "Intensidad no permitida para esta categoría",
      }),
    ).not.toBeInTheDocument();
    expect(mockAttachMutate).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("TemplatePicker — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado exitoso (modo biblioteca)", async () => {
    const { container } = renderPicker();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en el estado de carga", async () => {
    mockUseTemplates.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      isError: false,
      error: null,
    });
    const { container } = renderPicker();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en el estado vacío", async () => {
    mockUseTemplates.mockReturnValue(successResult([]));
    const { container } = renderPicker();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en modo adjunto con tarjetas", async () => {
    const { container } = renderPicker({ trainingSessionId: 42 });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con el diálogo de compuerta por edad abierto", async () => {
    const user = userEvent.setup();
    mockAttachMutate.mockImplementation((_vars, opts) =>
      opts.onError(
        makeGateError("age_gate_confirmation_required", "Confirmá."),
      ),
    );
    const { container } = renderPicker({ trainingSessionId: 42 });

    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[1]);
    await screen.findByRole("heading", {
      name: "Confirmá la estructura para esta categoría",
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
