/**
 * Tests para BlockAssembler (US2 / T027; guardrail de franja de edad US3 / T032):
 *   - Estado inicial: sin entradas → mensaje "Sin ejercicios" y submit deshabilitado.
 *   - Agregar/quitar ejercicios: entra a la lista, se quita del selector, submit se habilita.
 *   - Reordenar: "Subir"/"Bajar" deshabilitados en los extremos; mueven la entrada.
 *   - onSubmit recibe el payload con entries posicionales correctas.
 *   - isPending=true: botón "Guardando bloque…" deshabilitado.
 *   - errorMessage: alerta visible bajo el botón.
 *   - Indicador de duración — casos límite 29/30/31 minutos totales:
 *       * computeDurationStatus (función pura) para los tres estados.
 *       * Integración vía UI: editar la duración de la entrada única para
 *         alcanzar 29 (within/verde), 30 (at/ámbar) y 31 (over/ámbar) frente
 *         a la meta por defecto de 30 min — indicador informativo, nunca
 *         bloquea el guardado (FR-009).
 *   - Guardrail de franja de edad (FR-011, US3, T032): cuando onSubmit rechaza
 *     con 422 AGE_BAND_GUARDRAIL se abre AgeBandGuardrailDialog —
 *       * "Cancelar" cierra el diálogo sin persistir: la lista de entradas
 *         del bloque queda sin cambios (sin insignia de anulación).
 *       * "Confirmar anulación" marca la entrada con is_age_override: true,
 *         reintenta el guardado, y la lista muestra la insignia de excepción
 *         de edad para esa entrada.
 *   - a11y: jest-axe sin violaciones en estado inicial, con entradas y con el
 *     diálogo de guardrail abierto.
 *
 * Mirror de `components/technique/__tests__/SessionAssembler.test.tsx` (feature 018).
 * Estrategia: render puro sin red — props son listas estáticas, onSubmit es vi.fn().
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import {
  BlockAssembler,
  computeDurationStatus,
  type BlockAssemblerSubmitInput,
} from "../BlockAssembler";
import { makeExerciseListItem } from "@/test/msw/strengthHandlers";
import type { StrengthExerciseListItem } from "@/schemas/strength.schemas";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios; nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

const EX_SENTADILLA: StrengthExerciseListItem = makeExerciseListItem({
  id: 1,
  slug: "sentadilla-ficticia",
  name: "Sentadilla Ficticia",
  suggested_duration_min: 10,
  age_bands: ["10-12"],
});

const EX_PRESS: StrengthExerciseListItem = makeExerciseListItem({
  id: 2,
  slug: "press-ficticio",
  name: "Press Ficticio",
  suggested_duration_min: 15,
  age_bands: ["13-15"],
});

const EX_PLANCHA: StrengthExerciseListItem = makeExerciseListItem({
  id: 3,
  slug: "plancha-ficticia",
  name: "Plancha Ficticia",
  suggested_duration_min: 5,
  age_bands: ["10-12"],
});

const EXERCISES: StrengthExerciseListItem[] = [EX_SENTADILLA, EX_PRESS, EX_PLANCHA];

/**
 * Error 422 AGE_BAND_GUARDRAIL simulado — misma forma que `extractAgeBandGuardrail`
 * espera de Axios: `error.isAxiosError === true` + `response.data.detail.code`.
 */
function makeAgeBandGuardrailError(message = "Ejercicio fuera de la franja de edad.") {
  return {
    isAxiosError: true,
    response: {
      status: 422,
      data: {
        detail: {
          code: "AGE_BAND_GUARDRAIL",
          detail: message,
        },
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface OverrideProps {
  exercises?: StrengthExerciseListItem[];
  onSubmit?: (input: BlockAssemblerSubmitInput) => void;
  isPending?: boolean;
  errorMessage?: string | null;
}

function renderAssembler(overrides: OverrideProps = {}) {
  const props = {
    exercises: EXERCISES,
    onSubmit: vi.fn<(input: BlockAssemblerSubmitInput) => void>(),
    isPending: false,
    errorMessage: null,
    ...overrides,
  };
  return { ...render(<BlockAssembler {...props} />), onSubmit: props.onSubmit };
}

/** Agrega un ejercicio al bloque via el selector picker. */
async function addExercise(
  user: ReturnType<typeof userEvent.setup>,
  exerciseName: string,
) {
  const select = screen.getByLabelText(
    "Agregar ejercicio al bloque",
  ) as HTMLSelectElement;
  await user.selectOptions(select, exerciseName);
  await user.click(screen.getByRole("button", { name: "Agregar" }));
}

/** Cambia la duración (minutos) de la única entrada agregada al bloque. */
function setEntryDuration(exerciseId: number, minutes: number) {
  const input = screen.getByLabelText(
    new RegExp(`Duración de .* \\(minutos\\)`),
  ) as HTMLInputElement;
  fireEvent.change(input, { target: { value: String(minutes) } });
  void exerciseId;
}

// ---------------------------------------------------------------------------
// Suite: estructura inicial
// ---------------------------------------------------------------------------

describe("BlockAssembler — estructura inicial", () => {
  it("muestra mensaje 'Sin ejercicios' cuando no hay entradas", () => {
    renderAssembler();
    expect(
      screen.getByText("Sin ejercicios. Agrega desde el selector."),
    ).toBeInTheDocument();
  });

  it("el botón de envío está deshabilitado sin entradas", () => {
    renderAssembler();
    expect(
      screen.getByRole("button", { name: "Guardar bloque de fuerza" }),
    ).toBeDisabled();
  });

  it("muestra alerta con role=status indicando que se debe agregar al menos un ejercicio", () => {
    renderAssembler();
    // Hay dos elementos role=status en el estado inicial: el indicador de
    // duración en vivo y este mensaje — se valida el texto directamente.
    const statusEls = screen.getAllByRole("status");
    expect(statusEls.length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText("Agrega al menos un ejercicio para poder guardar el bloque."),
    ).toBeInTheDocument();
  });

  it("renderiza el formulario con aria-label 'Armar bloque de fuerza'", () => {
    renderAssembler();
    expect(
      screen.getByRole("form", { name: "Armar bloque de fuerza" }),
    ).toBeInTheDocument();
  });

  it("el indicador de duración muestra el total en 0 min frente a la meta por defecto (30)", () => {
    renderAssembler();
    expect(screen.getByTestId("block-total-minutes")).toHaveTextContent("0");
  });
});

// ---------------------------------------------------------------------------
// Suite: agregar / quitar ejercicios
// ---------------------------------------------------------------------------

describe("BlockAssembler — agregar y quitar ejercicios", () => {
  it("al agregar un ejercicio aparece en la lista del bloque", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");

    expect(
      screen.getByRole("list", { name: "Ejercicios del bloque" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Sentadilla Ficticia")).toBeInTheDocument();
  });

  it("el ejercicio agregado deja de estar disponible en el picker", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");

    const select = screen.getByLabelText(
      "Agregar ejercicio al bloque",
    ) as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.text);
    expect(optionTexts).not.toContain("Sentadilla Ficticia");
  });

  it("el botón de envío se habilita al agregar un ejercicio", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");

    expect(
      screen.getByRole("button", { name: "Guardar bloque de fuerza" }),
    ).not.toBeDisabled();
  });

  it("quitar el único ejercicio restablece el mensaje vacío y deshabilita el submit", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    await user.click(screen.getByRole("button", { name: "Quitar Sentadilla Ficticia" }));

    expect(
      screen.getByText("Sin ejercicios. Agrega desde el selector."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Guardar bloque de fuerza" }),
    ).toBeDisabled();
  });

  it("quitar un ejercicio lo devuelve al picker", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    await user.click(screen.getByRole("button", { name: "Quitar Sentadilla Ficticia" }));

    const select = screen.getByLabelText(
      "Agregar ejercicio al bloque",
    ) as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.text);
    expect(optionTexts).toContain("Sentadilla Ficticia");
  });
});

// ---------------------------------------------------------------------------
// Suite: reordenar ejercicios
// ---------------------------------------------------------------------------

describe("BlockAssembler — reordenar ejercicios", () => {
  it("el botón 'Subir' del primer item está deshabilitado y 'Bajar' del último también", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    await addExercise(user, "Press Ficticio");

    const upButtons = screen.getAllByRole("button", { name: /Subir / });
    const downButtons = screen.getAllByRole("button", { name: /Bajar / });

    expect(upButtons[0]).toBeDisabled();
    expect(upButtons[1]).not.toBeDisabled();
    expect(downButtons[0]).not.toBeDisabled();
    expect(downButtons[1]).toBeDisabled();
  });

  it("clicar 'Subir' en el segundo item lo mueve a la posición 1", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    await addExercise(user, "Press Ficticio");

    await user.click(screen.getByRole("button", { name: "Subir Press Ficticio" }));

    const list = screen.getByRole("list", { name: "Ejercicios del bloque" });
    const items = Array.from(list.querySelectorAll("li")).map((li) => li.textContent);
    expect(items[0]).toContain("Press Ficticio");
    expect(items[1]).toContain("Sentadilla Ficticia");
  });
});

// ---------------------------------------------------------------------------
// Suite: envío del formulario
// ---------------------------------------------------------------------------

describe("BlockAssembler — envío del formulario", () => {
  it("onSubmit recibe el payload con entries en el orden posicional correcto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <BlockAssembler
        exercises={EXERCISES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    await user.type(screen.getByLabelText("Nombre del bloque"), "Bloque ficticio");
    await addExercise(user, "Sentadilla Ficticia");
    await addExercise(user, "Press Ficticio");

    await user.click(screen.getByRole("button", { name: "Guardar bloque de fuerza" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const payload = onSubmit.mock.calls[0][0] as BlockAssemblerSubmitInput;
    expect(payload.name).toBe("Bloque ficticio");
    expect(payload.entries).toEqual([
      expect.objectContaining({ exercise_id: EX_SENTADILLA.id, position: 0 }),
      expect.objectContaining({ exercise_id: EX_PRESS.id, position: 1 }),
    ]);
  });

  it("onSubmit no se llama si no hay ejercicios (botón deshabilitado)", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <BlockAssembler
        exercises={EXERCISES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    const submitBtn = screen.getByRole("button", { name: "Guardar bloque de fuerza" });
    expect(submitBtn).toBeDisabled();
    await user.click(submitBtn);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado isPending / errorMessage
// ---------------------------------------------------------------------------

describe("BlockAssembler — estado isPending", () => {
  it("el botón muestra 'Guardando bloque…' y está deshabilitado cuando isPending=true", () => {
    renderAssembler({ isPending: true });
    expect(
      screen.getByRole("button", { name: "Guardando bloque…" }),
    ).toBeDisabled();
  });
});

describe("BlockAssembler — errorMessage", () => {
  it("muestra el mensaje de error con role=alert", () => {
    renderAssembler({ errorMessage: "No se pudo guardar el bloque." });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo guardar el bloque.",
    );
  });

  it("no muestra ningún role=alert cuando errorMessage es null", () => {
    renderAssembler({ errorMessage: null });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: indicador de duración — casos límite 29/30/31 min (FR-009)
// ---------------------------------------------------------------------------

describe("computeDurationStatus — función pura (límites 29/30/31)", () => {
  it("29 de 30 → 'within' (dentro de la meta)", () => {
    expect(computeDurationStatus(29, 30)).toBe("within");
  });

  it("30 de 30 → 'at' (en el límite de la meta)", () => {
    expect(computeDurationStatus(30, 30)).toBe("at");
  });

  it("31 de 30 → 'over' (por encima de la meta)", () => {
    expect(computeDurationStatus(31, 30)).toBe("over");
  });
});

describe("BlockAssembler — indicador de duración en vivo (integración UI)", () => {
  it("29 min totales frente a la meta de 30 muestra el badge 'Dentro de la meta' (success)", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    setEntryDuration(EX_SENTADILLA.id, 29);

    expect(screen.getByTestId("block-total-minutes")).toHaveTextContent("29");
    const badge = screen.getByTestId("duration-indicator");
    expect(badge).toHaveTextContent("Dentro de la meta");
  });

  it("30 min totales frente a la meta de 30 muestra el badge 'En el límite de la meta' (warning)", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    setEntryDuration(EX_SENTADILLA.id, 30);

    expect(screen.getByTestId("block-total-minutes")).toHaveTextContent("30");
    const badge = screen.getByTestId("duration-indicator");
    expect(badge).toHaveTextContent("En el límite de la meta");
  });

  it("31 min totales frente a la meta de 30 muestra el badge 'Por encima de la meta' (warning, no bloqueante)", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    setEntryDuration(EX_SENTADILLA.id, 31);

    expect(screen.getByTestId("block-total-minutes")).toHaveTextContent("31");
    const badge = screen.getByTestId("duration-indicator");
    expect(badge).toHaveTextContent("Por encima de la meta");

    // El indicador es informativo — el guardado no queda bloqueado por superar la meta.
    expect(
      screen.getByRole("button", { name: "Guardar bloque de fuerza" }),
    ).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: guardrail de franja de edad (FR-011, US3, T032)
// ---------------------------------------------------------------------------
//
// La franja de edad objetivo por defecto del formulario es "10-12"
// (ver defaultValues de BlockAssembler). EX_PRESS solo admite "13-15", por
// lo que agregarlo y enviar el formulario con la franja por defecto dispara
// el guardrail simulado por `onSubmit` (mockRejectedValue con el error 422
// AGE_BAND_GUARDRAIL) — el mismo contrato que usa `extractAgeBandGuardrail`.

describe("BlockAssembler — guardrail de franja de edad (US3)", () => {
  it("warn→cancel: cierra el diálogo sin persistir y la lista de entradas queda sin cambios", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(makeAgeBandGuardrailError());
    render(
      <BlockAssembler
        exercises={EXERCISES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    await user.type(screen.getByLabelText("Nombre del bloque"), "Bloque ficticio");
    await addExercise(user, "Press Ficticio");
    await user.click(screen.getByRole("button", { name: "Guardar bloque de fuerza" }));

    expect(
      await screen.findByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    // Diálogo cerrado
    expect(
      screen.queryByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).not.toBeInTheDocument();

    // Lista de entradas sin cambios: sigue teniendo la única entrada, sin
    // insignia de anulación de edad, y no se reintentó el guardado.
    const list = screen.getByRole("list", { name: "Ejercicios del bloque" });
    expect(list.querySelectorAll("li")).toHaveLength(1);
    expect(screen.getByText("Press Ficticio")).toBeInTheDocument();
    expect(screen.queryByText("Excepción de edad")).not.toBeInTheDocument();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("warn→confirm: agrega la entrada con is_age_override true y muestra la insignia de excepción", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValueOnce(makeAgeBandGuardrailError())
      .mockResolvedValueOnce(undefined);
    render(
      <BlockAssembler
        exercises={EXERCISES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    await user.type(screen.getByLabelText("Nombre del bloque"), "Bloque ficticio");
    await addExercise(user, "Press Ficticio");
    await user.click(screen.getByRole("button", { name: "Guardar bloque de fuerza" }));

    expect(
      await screen.findByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirmar anulación" }));

    // El diálogo se cierra y BlockAssembler reintenta el guardado con la
    // entrada marcada is_age_override: true.
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    expect(
      screen.queryByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).not.toBeInTheDocument();

    const retryPayload = onSubmit.mock.calls[1][0] as BlockAssemblerSubmitInput;
    expect(retryPayload.entries).toEqual([
      expect.objectContaining({
        exercise_id: EX_PRESS.id,
        is_age_override: true,
      }),
    ]);

    // La entrada muestra la insignia de excepción de edad en la lista.
    expect(
      screen.getByTestId(`age-override-badge-${EX_PRESS.id}`),
    ).toBeInTheDocument();
    expect(screen.getByText("Excepción de edad")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("BlockAssembler — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado inicial (sin ejercicios)", async () => {
    const { container } = renderAssembler();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con ejercicios agregados", async () => {
    const user = userEvent.setup();
    const { container } = renderAssembler();

    await addExercise(user, "Sentadilla Ficticia");
    await addExercise(user, "Press Ficticio");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando isPending=true", async () => {
    const { container } = renderAssembler({ isPending: true });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando hay un errorMessage", async () => {
    const { container } = renderAssembler({
      errorMessage: "Error al guardar el bloque.",
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con el diálogo de guardrail de franja de edad abierto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(makeAgeBandGuardrailError());
    const { container } = render(
      <BlockAssembler
        exercises={EXERCISES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    await user.type(screen.getByLabelText("Nombre del bloque"), "Bloque ficticio");
    await addExercise(user, "Press Ficticio");
    await user.click(screen.getByRole("button", { name: "Guardar bloque de fuerza" }));

    expect(
      await screen.findByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).toBeInTheDocument();

    expect(await axe(container)).toHaveNoViolations();
  });
});
