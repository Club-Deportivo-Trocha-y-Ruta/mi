/**
 * Tests para StructureEditor (feature 026, T013; compuerta por edad T014):
 *   - Estado inicial: un bloque por defecto, indicador de duración total,
 *     conteo de bloques.
 *   - Agregar / quitar bloques: conteo y duración total se actualizan; al
 *     quitar el último bloque aparece el mensaje vacío y el submit se
 *     deshabilita (no se puede guardar una estructura sin bloques).
 *   - Reordenar bloques ("Subir"/"Bajar" deshabilitados en los extremos).
 *   - Grupo repetido: activar el checkbox agrega los inputs de número de
 *     grupo/repeticiones y el indicador de duración aplana según
 *     `repeat_count` (misma regla que el motor de matching y el instructivo).
 *   - `computeFlattenedDurationS` (función pura) probada directamente con
 *     grupos repetidos multi-bloque.
 *   - Envío: `onSubmit` recibe el payload con `training_session_id`,
 *     `target_age_band`, `age_gate_confirmed: false` y `blocks` con
 *     posiciones 1-indexadas recalculadas.
 *   - Compuerta por edad (FR-006/FR-007), mismo flujo que
 *     `strength/BlockAssembler.tsx`:
 *       * `age_gate_confirmation_required` → abre `AgeGateDialog` modo
 *         "confirmation"; "Confirmar estructura" reenvía con
 *         `age_gate_confirmed: true`.
 *       * `age_gate_z3_blocked` → abre `AgeGateDialog` modo "blocked" (sin
 *         reintento automático); "Entendido" cierra el diálogo.
 *   - Errores inline por posición: `cadence_below_minimum` /
 *     `invalid_repeat_group` marcan el campo correspondiente en la fila.
 *   - `isPending` / `errorMessage` / `submitLabel` / `defaultValues`.
 *   - a11y: jest-axe sin violaciones en los estados relevantes.
 *
 * Mirror de `components/strength/__tests__/BlockAssembler.test.tsx`.
 */
import { describe, it, expect, vi, type Mock } from "vitest";
import { render, screen, within, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import {
  StructureEditor,
  computeFlattenedDurationS,
  type StructureEditorSubmitInput,
} from "../StructureEditor";
import type { IntervalValidationCode } from "@/types/intervals.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface OverrideProps {
  trainingSessionId?: number;
  onSubmit?: Mock<(input: StructureEditorSubmitInput) => void | Promise<void>>;
  isPending?: boolean;
  errorMessage?: string | null;
  defaultValues?: {
    target_age_band?: "10-12" | "13-15";
    blocks?: StructureEditorSubmitInput["blocks"];
  };
  submitLabel?: string;
}

function renderEditor(overrides: OverrideProps = {}) {
  const props = {
    trainingSessionId: 42,
    onSubmit: vi.fn<(input: StructureEditorSubmitInput) => void>(),
    isPending: false,
    errorMessage: null,
    ...overrides,
  };
  return { ...render(<StructureEditor {...props} />), onSubmit: props.onSubmit };
}

/**
 * Error 422 legible por máquina simulado — misma forma que
 * `extractIntervalValidationError` espera de Axios (contracts/api.md).
 */
function makeIntervalValidationError(
  code: IntervalValidationCode,
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

function blocksList() {
  return screen.getByRole("list", { name: "Bloques de la estructura" });
}

function blockItems() {
  return within(blocksList()).getAllByRole("listitem");
}

// ---------------------------------------------------------------------------
// Suite: computeFlattenedDurationS (función pura)
// ---------------------------------------------------------------------------

describe("computeFlattenedDurationS — función pura", () => {
  it("suma la duración de bloques no agrupados una sola vez", () => {
    expect(
      computeFlattenedDurationS([
        { duration_s: 300, repeat_group: null, repeat_count: null },
        { duration_s: 300, repeat_group: null, repeat_count: null },
      ]),
    ).toBe(600);
  });

  it("multiplica los bloques de un grupo repetido por repeat_count", () => {
    expect(
      computeFlattenedDurationS([
        { duration_s: 300, repeat_group: null, repeat_count: null }, // calentamiento
        { duration_s: 120, repeat_group: 1, repeat_count: 3 }, // trabajo x3
        { duration_s: 60, repeat_group: 1, repeat_count: 3 }, // recuperación x3
        { duration_s: 300, repeat_group: null, repeat_count: null }, // enfriamiento
      ]),
    ).toBe(300 + 120 * 3 + 60 * 3 + 300);
  });

  it("ignora repeat_count si repeat_group es null (cuenta una sola vez)", () => {
    expect(
      computeFlattenedDurationS([
        { duration_s: 100, repeat_group: null, repeat_count: 5 },
      ]),
    ).toBe(100);
  });

  it("retorna 0 para una lista vacía", () => {
    expect(computeFlattenedDurationS([])).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Suite: estado inicial
// ---------------------------------------------------------------------------

describe("StructureEditor — estado inicial", () => {
  it("renderiza un bloque por defecto", () => {
    renderEditor();
    expect(blockItems()).toHaveLength(1);
  });

  it("muestra el conteo de bloques '1 bloque' (singular)", () => {
    renderEditor();
    expect(screen.getByTestId("structure-block-count")).toHaveTextContent(
      "1 bloque",
    );
  });

  it("muestra la duración total estimada '5:00' para el bloque por defecto (300s)", () => {
    renderEditor();
    expect(screen.getByTestId("structure-total-duration")).toHaveTextContent(
      "5:00",
    );
  });

  it("la categoría objetivo por defecto es '13 a 15 años'", () => {
    renderEditor();
    expect(screen.getByLabelText("Categoría objetivo")).toHaveValue("13-15");
  });

  it("renderiza el formulario con aria-label 'Editor de estructura de intervalos'", () => {
    renderEditor();
    expect(
      screen.getByRole("form", { name: "Editor de estructura de intervalos" }),
    ).toBeInTheDocument();
  });

  it("el botón de envío usa el texto por defecto 'Guardar estructura'", () => {
    renderEditor();
    expect(
      screen.getByRole("button", { name: "Guardar estructura" }),
    ).toBeInTheDocument();
  });

  it("submitLabel personalizado sobreescribe el texto del botón", () => {
    renderEditor({ submitLabel: "Actualizar estructura" });
    expect(
      screen.getByRole("button", { name: "Actualizar estructura" }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: defaultValues (modo edición)
// ---------------------------------------------------------------------------

describe("StructureEditor — defaultValues", () => {
  it("precarga la categoría objetivo y los bloques existentes", () => {
    renderEditor({
      defaultValues: {
        target_age_band: "10-12",
        blocks: [
          {
            position: 1,
            block_type: "warmup",
            duration_s: 180,
            target_zone: "Z1",
            target_cadence_rpm: 75,
            repeat_group: null,
            repeat_count: null,
          },
          {
            position: 2,
            block_type: "cooldown",
            duration_s: 180,
            target_zone: "Z1",
            target_cadence_rpm: 65,
            repeat_group: null,
            repeat_count: null,
          },
        ],
      },
    });

    expect(screen.getByLabelText("Categoría objetivo")).toHaveValue("10-12");
    expect(blockItems()).toHaveLength(2);
    expect(screen.getByTestId("structure-total-duration")).toHaveTextContent(
      "6:00",
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: agregar / quitar bloques
// ---------------------------------------------------------------------------

describe("StructureEditor — agregar y quitar bloques", () => {
  it("'Agregar bloque' suma un bloque al conteo y a la duración total", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Agregar bloque" }));

    expect(blockItems()).toHaveLength(2);
    expect(screen.getByTestId("structure-block-count")).toHaveTextContent(
      "2 bloques",
    );
    expect(screen.getByTestId("structure-total-duration")).toHaveTextContent(
      "10:00",
    );
  });

  it("quitar el único bloque muestra el mensaje vacío y deshabilita el envío", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Quitar bloque 1" }));

    expect(
      screen.getByText(
        "Sin bloques. Agregá el primero para armar la estructura.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Agregá al menos un bloque para poder guardar la estructura.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Guardar estructura" }),
    ).toBeDisabled();
  });

  it("quitar un bloque de dos reduce el conteo a uno", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Agregar bloque" }));
    await user.click(screen.getByRole("button", { name: "Quitar bloque 2" }));

    expect(blockItems()).toHaveLength(1);
    expect(screen.getByTestId("structure-block-count")).toHaveTextContent(
      "1 bloque",
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: reordenar bloques
// ---------------------------------------------------------------------------

describe("StructureEditor — reordenar bloques", () => {
  it("'Subir' del primer bloque y 'Bajar' del último están deshabilitados", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(screen.getByRole("button", { name: "Agregar bloque" }));

    expect(screen.getByRole("button", { name: "Subir bloque 1" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Bajar bloque 1" }),
    ).not.toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Subir bloque 2" }),
    ).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Bajar bloque 2" })).toBeDisabled();
  });

  it("clicar 'Subir' en el segundo bloque intercambia el contenido de las filas", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(screen.getByRole("button", { name: "Agregar bloque" }));

    const durationInputs = () =>
      screen.getAllByLabelText("Duración (segundos)") as HTMLInputElement[];
    fireEvent.change(durationInputs()[1], { target: { value: "999" } });
    expect(durationInputs()[1].value).toBe("999");

    await user.click(screen.getByRole("button", { name: "Subir bloque 2" }));

    expect(durationInputs()[0].value).toBe("999");
    expect(durationInputs()[1].value).toBe("300");
  });
});

// ---------------------------------------------------------------------------
// Suite: grupo repetido (FR-002)
// ---------------------------------------------------------------------------

describe("StructureEditor — grupo repetido", () => {
  it("activar 'Parte de un grupo repetido' muestra número de grupo (1) y repeticiones (2) por defecto, y la insignia de grupo", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(
      screen.getByRole("checkbox", { name: "Parte de un grupo repetido" }),
    );

    expect(screen.getByLabelText("Número de grupo")).toHaveValue(1);
    expect(screen.getByLabelText("Repeticiones (×N)")).toHaveValue(2);
    expect(screen.getByText("En grupo repetido")).toBeInTheDocument();
  });

  it("desactivar el grupo repetido vuelve la duración a la base y oculta los inputs", async () => {
    const user = userEvent.setup();
    renderEditor();

    const checkbox = screen.getByRole("checkbox", {
      name: "Parte de un grupo repetido",
    });
    await user.click(checkbox);
    await user.click(checkbox);

    expect(screen.queryByLabelText("Número de grupo")).not.toBeInTheDocument();
    expect(screen.getByTestId("structure-total-duration")).toHaveTextContent(
      "5:00",
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: envío del formulario
// ---------------------------------------------------------------------------

describe("StructureEditor — envío del formulario", () => {
  it("onSubmit recibe el payload con training_session_id, target_age_band y blocks reindexados", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderEditor({ trainingSessionId: 42 });

    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const payload = onSubmit.mock.calls[0][0] as StructureEditorSubmitInput;
    expect(payload.training_session_id).toBe(42);
    expect(payload.target_age_band).toBe("13-15");
    expect(payload.age_gate_confirmed).toBe(false);
    expect(payload.blocks).toEqual([
      expect.objectContaining({
        position: 1,
        block_type: "warmup",
        duration_s: 300,
        target_zone: "Z1",
        target_cadence_rpm: 70,
        repeat_group: null,
        repeat_count: null,
      }),
    ]);
  });

  it("onSubmit no se llama si no hay bloques (botón deshabilitado)", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderEditor();

    const removeBtn = screen.getByRole("button", { name: "Quitar bloque 1" });
    await user.click(removeBtn);
    const submitBtn = screen.getByRole("button", { name: "Guardar estructura" });
    expect(submitBtn).toBeDisabled();
    await user.click(submitBtn);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: isPending / errorMessage
// ---------------------------------------------------------------------------

describe("StructureEditor — isPending", () => {
  it("muestra 'Guardando estructura…' y deshabilita el botón cuando isPending=true", () => {
    renderEditor({ isPending: true });
    expect(
      screen.getByRole("button", { name: "Guardando estructura…" }),
    ).toBeDisabled();
  });
});

describe("StructureEditor — errorMessage", () => {
  it("muestra el mensaje de error genérico con role=alert", () => {
    renderEditor({ errorMessage: "No se pudo guardar la estructura." });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo guardar la estructura.",
    );
  });

  it("no muestra role=alert cuando errorMessage es null", () => {
    renderEditor({ errorMessage: null });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: compuerta por edad (FR-006/FR-007)
// ---------------------------------------------------------------------------

describe("StructureEditor — compuerta por edad confirmable (FR-007)", () => {
  it("abre AgeGateDialog modo confirmation al recibir age_gate_confirmation_required", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "age_gate_confirmation_required",
          "Confirmá explícitamente la estructura para la categoría 10-12 antes de guardar.",
        ),
      );
    renderEditor({ onSubmit });

    await user.selectOptions(
      screen.getByLabelText("Categoría objetivo"),
      "10-12",
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    expect(
      await screen.findByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Confirmá explícitamente la estructura para la categoría 10-12 antes de guardar.",
      ),
    ).toBeInTheDocument();
  });

  it("'Confirmar estructura' reenvía con age_gate_confirmed: true", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValueOnce(
        makeIntervalValidationError(
          "age_gate_confirmation_required",
          "Confirmá explícitamente.",
        ),
      )
      .mockResolvedValueOnce(undefined);
    renderEditor({ onSubmit });

    await user.selectOptions(
      screen.getByLabelText("Categoría objetivo"),
      "10-12",
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    await screen.findByRole("heading", {
      name: "Confirmá la estructura para esta categoría",
    });
    await user.click(
      screen.getByRole("button", { name: "Confirmar estructura" }),
    );

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    const retryPayload = onSubmit.mock.calls[1][0] as StructureEditorSubmitInput;
    expect(retryPayload.age_gate_confirmed).toBe(true);
    expect(
      screen.queryByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).not.toBeInTheDocument();
  });
});

describe("StructureEditor — bloqueo duro Z3+ (FR-006)", () => {
  it("abre AgeGateDialog modo blocked con las posiciones señaladas, sin reintento automático", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "age_gate_z3_blocked",
          "Intensidad Z3 o superior no está disponible para la categoría 10-12.",
          [1],
        ),
      );
    renderEditor({ onSubmit });

    await user.selectOptions(
      screen.getByLabelText("Categoría objetivo"),
      "10-12",
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    expect(
      await screen.findByRole("heading", {
        name: "Intensidad no permitida para esta categoría",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ajustá la zona de/).closest("p")!.textContent,
    ).toContain("el bloque");

    await user.click(screen.getByRole("button", { name: "Entendido" }));

    expect(
      screen.queryByRole("heading", {
        name: "Intensidad no permitida para esta categoría",
      }),
    ).not.toBeInTheDocument();
    // Bloqueo duro: nunca se reintenta automáticamente.
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Suite: errores inline por posición
// ---------------------------------------------------------------------------

describe("StructureEditor — errores inline por posición", () => {
  it("cadence_below_minimum marca el campo de cadencia del bloque señalado", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "cadence_below_minimum",
          "La cadencia mínima es 60 rpm para todas las categorías.",
          [1],
        ),
      );
    renderEditor({ onSubmit });

    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    await waitFor(() => {
      expect(
        screen.getByText("La cadencia mínima es 60 rpm para todas las categorías."),
      ).toBeInTheDocument();
    });
  });

  it("invalid_repeat_group marca el campo de repeticiones del bloque señalado", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "invalid_repeat_group",
          "Grupo inválido.",
          [1],
        ),
      );
    renderEditor({ onSubmit });

    // Activa el grupo repetido para que el campo de repeticiones exista en el DOM.
    await user.click(
      screen.getByRole("checkbox", { name: "Parte de un grupo repetido" }),
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));

    await waitFor(() => {
      expect(
        screen.getByText("Revisá la configuración del grupo de repeticiones."),
      ).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("StructureEditor — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado inicial", async () => {
    const { container } = renderEditor();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con errorMessage", async () => {
    const { container } = renderEditor({
      errorMessage: "Error al guardar la estructura.",
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando isPending=true", async () => {
    const { container } = renderEditor({ isPending: true });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con el diálogo de compuerta por edad (confirmation) abierto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "age_gate_confirmation_required",
          "Confirmá explícitamente.",
        ),
      );
    const { container } = renderEditor({ onSubmit });

    await user.selectOptions(
      screen.getByLabelText("Categoría objetivo"),
      "10-12",
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));
    await screen.findByRole("heading", {
      name: "Confirmá la estructura para esta categoría",
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con el diálogo de bloqueo Z3+ abierto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        makeIntervalValidationError(
          "age_gate_z3_blocked",
          "Intensidad Z3 o superior no está disponible.",
          [1],
        ),
      );
    const { container } = renderEditor({ onSubmit });

    await user.selectOptions(
      screen.getByLabelText("Categoría objetivo"),
      "10-12",
    );
    await user.click(screen.getByRole("button", { name: "Guardar estructura" }));
    await screen.findByRole("heading", {
      name: "Intensidad no permitida para esta categoría",
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
