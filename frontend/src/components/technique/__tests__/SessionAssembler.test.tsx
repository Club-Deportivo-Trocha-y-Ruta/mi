/**
 * Tests para SessionAssembler (US3 / T032):
 *   - Renderiza los tres segmentos (calentamiento, principal, vuelta a la calma).
 *   - Estado inicial: sin ejercicios → mensaje "Sin ejercicios" por segmento.
 *   - Estado inicial: botón de envío deshabilitado cuando no hay items.
 *   - Mensaje de alerta "Agrega al menos un ejercicio" visible con items=0.
 *   - Agregar ejercicio a un segmento lo muestra en la lista de ese segmento.
 *   - Agregar ejercicio lo quita del selector (no se puede duplicar en mismo segmento).
 *   - Quitar ejercicio lo devuelve al selector.
 *   - Reordenar: botón "Subir" deshabilitado en posición 1; "Bajar" en posición última.
 *   - Reordenar: mover item hacia arriba/abajo reordena la lista.
 *   - Botón de envío habilitado cuando hay al menos un item y form válido.
 *   - onSubmit recibe payload con items en order posicional correcto.
 *   - isPending=true: botón dice "Guardando sesión…" y está deshabilitado.
 *   - errorMessage muestra alerta debajo del botón.
 *   - Convocados: los atletas se muestran como toggles con aria-pressed.
 *   - Convocados: alternar un atleta cambia aria-pressed y su ID aparece en payload.
 *   - MixedAgeNotice: se renderiza cuando se le pasa mixes_age_bands=true.
 *   - MixedAgeNotice: no se renderiza cuando mixes_age_bands=false o undefined.
 *   - a11y: jest-axe sin violaciones en estado inicial.
 *   - a11y: jest-axe sin violaciones con ejercicios agregados.
 *
 * Estrategia: render puro sin red — los props son listas estáticas, onSubmit es vi.fn().
 * No se necesita MSW ni QueryClient porque SessionAssembler no hace fetch directo.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { SessionAssembler } from "../SessionAssembler";
import { MixedAgeNotice } from "../MixedAgeNotice";
import { makeExerciseListItem } from "@/test/msw/techniqueHandlers";
import { Sex } from "@/types/enums";
import type { ExerciseListItem, AssembleSessionInput } from "@/types/technique.types";
import type { AthleteOut } from "@/types/athlete.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios; nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

const EX_SLALOM: ExerciseListItem = makeExerciseListItem({
  id: 1,
  slug: "slalom-ficticio",
  name: "Slalom Ficticio",
  age_bands: ["10-12"],
});

const EX_GYMKHANA: ExerciseListItem = makeExerciseListItem({
  id: 2,
  slug: "gymkhana-ficticia",
  name: "Gymkhana Ficticia",
  difficulty: "media",
  is_gymkhana: true,
  age_bands: ["13-15"],
});

const EX_EQUILIBRIO: ExerciseListItem = makeExerciseListItem({
  id: 3,
  slug: "equilibrio-ficticio",
  name: "Equilibrio Ficticio",
  age_bands: ["10-12"],
});

const EXERCISES: ExerciseListItem[] = [EX_SLALOM, EX_GYMKHANA, EX_EQUILIBRIO];

const ATHLETE_A: AthleteOut = {
  id: 101,
  user_id: 201,
  first_name: "Juan Ficticio",
  last_name: "Pérez Ficticio",
  birth_date: "2013-03-15",
  sex: Sex.M,
  club_join_date: "2022-01-10",
  years_in_club: 4,
  age_decimal: 13.3,
  category: "Junior",
  club_id: 1,
  created_at: "2022-01-10T00:00:00Z",
};

const ATHLETE_B: AthleteOut = {
  id: 102,
  user_id: 202,
  first_name: "Ana Ficticia",
  last_name: "García Ficticia",
  birth_date: "2015-07-20",
  sex: Sex.F,
  club_join_date: "2023-03-01",
  years_in_club: 2,
  age_decimal: 10.9,
  category: "Infantil",
  club_id: 1,
  created_at: "2023-03-01T00:00:00Z",
};

const ATHLETES = [ATHLETE_A, ATHLETE_B];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface OverrideProps {
  exercises?: ExerciseListItem[];
  athletes?: AthleteOut[];
  onSubmit?: (input: AssembleSessionInput) => void;
  isPending?: boolean;
  errorMessage?: string | null;
}

function renderAssembler(overrides: OverrideProps = {}) {
  const props = {
    exercises: EXERCISES,
    athletes: ATHLETES,
    onSubmit: vi.fn<(input: AssembleSessionInput) => void>(),
    isPending: false,
    errorMessage: null,
    ...overrides,
  };
  return { ...render(<SessionAssembler {...props} />), onSubmit: props.onSubmit };
}

/** Agrega un ejercicio a un segmento via el selector picker. */
async function addExerciseToSegment(
  user: ReturnType<typeof userEvent.setup>,
  segmentLabel: string,
  exerciseName: string,
) {
  const selectorLabel = `Agregar ejercicio a ${segmentLabel}`;
  const select = screen.getByLabelText(selectorLabel) as HTMLSelectElement;
  await user.selectOptions(select, exerciseName);

  // The "Agregar" button is the sibling of the select — find by proximity
  const container = select.closest("div") as HTMLElement;
  const addBtn = within(container).getByRole("button", { name: "Agregar" });
  await user.click(addBtn);
}

/**
 * Rellena los campos obligatorios de metadatos de sesión para pasar la validación Zod.
 * Usa fireEvent.change para los inputs tipo date/time/number: en jsdom los inputs
 * type=date y type=time no responden a keystrokes de userEvent como lo haría un
 * navegador real.
 */
function fillSessionMeta() {
  fireEvent.change(screen.getByLabelText("Fecha"), { target: { value: "2026-07-15" } });
  fireEvent.change(screen.getByLabelText("Hora de inicio"), { target: { value: "09:00" } });
  fireEvent.change(screen.getByLabelText("Duración (minutos)"), { target: { value: "90" } });
  fireEvent.change(screen.getByLabelText("Lugar"), { target: { value: "Cancha Ficticia del Club" } });
  fireEvent.change(screen.getByLabelText("Foco técnico"), { target: { value: "Equilibrio y control direccional" } });
  fireEvent.change(screen.getByLabelText("Objetivos"), {
    target: { value: "Desarrollar estabilidad en el manillar en terreno plano" },
  });
}

// ---------------------------------------------------------------------------
// Suite: estructura inicial
// ---------------------------------------------------------------------------

describe("SessionAssembler — estructura inicial", () => {
  it("renderiza los tres encabezados de segmento", () => {
    renderAssembler();

    expect(screen.getByText("Calentamiento")).toBeInTheDocument();
    expect(screen.getByText("Principal")).toBeInTheDocument();
    expect(screen.getByText("Vuelta a la calma")).toBeInTheDocument();
  });

  it("muestra mensaje 'Sin ejercicios' en cada segmento vacío", () => {
    renderAssembler();

    const emptyMessages = screen.getAllByText("Sin ejercicios. Agrega desde el selector.");
    // Three segments × 1 message each
    expect(emptyMessages).toHaveLength(3);
  });

  it("el botón de envío está deshabilitado con todos los segmentos vacíos", () => {
    renderAssembler();

    const submitBtn = screen.getByRole("button", { name: "Guardar sesión técnica" });
    expect(submitBtn).toBeDisabled();
  });

  it("muestra alerta con role=status indicando que se debe agregar al menos un ejercicio", () => {
    renderAssembler();

    const statusMsg = screen.getByRole("status");
    expect(statusMsg).toHaveTextContent(
      "Agrega al menos un ejercicio para poder guardar la sesión.",
    );
  });

  it("renderiza el formulario con aria-label 'Armar sesión técnica'", () => {
    renderAssembler();

    expect(screen.getByRole("form", { name: "Armar sesión técnica" })).toBeInTheDocument();
  });

  it("renderiza el selector de ejercicios para cada segmento", () => {
    renderAssembler();

    expect(screen.getByLabelText("Agregar ejercicio a Calentamiento")).toBeInTheDocument();
    expect(screen.getByLabelText("Agregar ejercicio a Principal")).toBeInTheDocument();
    expect(screen.getByLabelText("Agregar ejercicio a Vuelta a la calma")).toBeInTheDocument();
  });

  it("el botón 'Agregar' de cada segmento está deshabilitado si no hay selección", () => {
    renderAssembler();

    const addButtons = screen.getAllByRole("button", { name: "Agregar" });
    expect(addButtons).toHaveLength(3);
    addButtons.forEach((btn) => {
      expect(btn).toBeDisabled();
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: agregar ejercicios
// ---------------------------------------------------------------------------

describe("SessionAssembler — agregar ejercicios", () => {
  it("al agregar un ejercicio aparece en la lista del segmento correspondiente", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");

    // The item appears in an ordered list inside the Calentamiento section
    const calientaSection = screen
      .getByText("Calentamiento")
      .closest("[aria-labelledby]") as HTMLElement;
    expect(within(calientaSection).getByText("Slalom Ficticio")).toBeInTheDocument();
  });

  it("el ejercicio agregado deja de estar disponible en el mismo picker", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");

    const calentamientoSelect = screen.getByLabelText(
      "Agregar ejercicio a Calentamiento",
    ) as HTMLSelectElement;
    const optionTexts = Array.from(calentamientoSelect.options).map((o) => o.text);
    expect(optionTexts).not.toContain("Slalom Ficticio");
  });

  it("el ejercicio puede seguir eligiéndose en el picker de otro segmento", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");

    const principalSelect = screen.getByLabelText(
      "Agregar ejercicio a Principal",
    ) as HTMLSelectElement;
    const optionTexts = Array.from(principalSelect.options).map((o) => o.text);
    expect(optionTexts).toContain("Slalom Ficticio");
  });

  it("el botón de envío se habilita al agregar un ejercicio (aunque los meta-campos aún vacíos)", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    // The button is no longer disabled due to totalItems > 0
    const submitBtn = screen.getByRole("button", { name: "Guardar sesión técnica" });
    expect(submitBtn).not.toBeDisabled();
  });

  it("la alerta 'Agrega al menos un ejercicio' desaparece al agregar uno", async () => {
    const user = userEvent.setup();
    renderAssembler();

    expect(screen.getByRole("status")).toBeInTheDocument();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("el Badge de conteo aparece en el segmento cuando hay ejercicios", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    // The badge shows "2" next to "Principal"
    const principalHeading = screen.getByRole("heading", { name: /Principal/ });
    expect(principalHeading.textContent).toContain("2");
  });
});

// ---------------------------------------------------------------------------
// Suite: quitar ejercicios
// ---------------------------------------------------------------------------

describe("SessionAssembler — quitar ejercicios", () => {
  it("quitar un ejercicio lo elimina de la lista del segmento", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");

    // The exercise should be in the Calentamiento ordered list
    const list = screen.getByRole("list", { name: "Ejercicios de Calentamiento" });
    expect(within(list).getByText("Slalom Ficticio")).toBeInTheDocument();

    const removeBtn = screen.getByRole("button", { name: "Quitar Slalom Ficticio" });
    await user.click(removeBtn);

    // After removal, the ordered list is gone (segment back to empty state)
    expect(screen.queryByRole("list", { name: "Ejercicios de Calentamiento" })).not.toBeInTheDocument();
  });

  it("quitar un ejercicio lo devuelve al picker del mismo segmento", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");
    await user.click(screen.getByRole("button", { name: "Quitar Slalom Ficticio" }));

    const calentamientoSelect = screen.getByLabelText(
      "Agregar ejercicio a Calentamiento",
    ) as HTMLSelectElement;
    const optionTexts = Array.from(calentamientoSelect.options).map((o) => o.text);
    expect(optionTexts).toContain("Slalom Ficticio");
  });

  it("quitar el único ejercicio restablece el botón de submit a deshabilitado", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    expect(
      screen.getByRole("button", { name: "Guardar sesión técnica" }),
    ).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Quitar Slalom Ficticio" }));

    expect(
      screen.getByRole("button", { name: "Guardar sesión técnica" }),
    ).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: reordenar ejercicios
// ---------------------------------------------------------------------------

describe("SessionAssembler — reordenar ejercicios", () => {
  it("el botón 'Subir' del primer item está deshabilitado", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    const upButtons = screen.getAllByRole("button", { name: /Subir / });
    // First item's "Subir" must be disabled
    expect(upButtons[0]).toBeDisabled();
    // Second item's "Subir" is enabled
    expect(upButtons[1]).not.toBeDisabled();
  });

  it("el botón 'Bajar' del último item está deshabilitado", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    const downButtons = screen.getAllByRole("button", { name: /Bajar / });
    // First item's "Bajar" is enabled
    expect(downButtons[0]).not.toBeDisabled();
    // Last item's "Bajar" must be disabled
    expect(downButtons[1]).toBeDisabled();
  });

  it("clicar 'Subir' en el segundo item lo mueve a la posición 1", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    // Before: Slalom(1), Gymkhana(2)
    const listBefore = screen.getByRole("list", { name: "Ejercicios de Principal" });
    const itemsBefore = within(listBefore).getAllByRole("listitem");
    expect(itemsBefore[0]).toHaveTextContent("Slalom Ficticio");
    expect(itemsBefore[1]).toHaveTextContent("Gymkhana Ficticia");

    await user.click(screen.getByRole("button", { name: "Subir Gymkhana Ficticia" }));

    // After: Gymkhana(1), Slalom(2)
    const listAfter = screen.getByRole("list", { name: "Ejercicios de Principal" });
    const itemsAfter = within(listAfter).getAllByRole("listitem");
    expect(itemsAfter[0]).toHaveTextContent("Gymkhana Ficticia");
    expect(itemsAfter[1]).toHaveTextContent("Slalom Ficticio");
  });

  it("clicar 'Bajar' en el primer item lo mueve a la posición 2", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");

    await user.click(screen.getByRole("button", { name: "Bajar Slalom Ficticio" }));

    const list = screen.getByRole("list", { name: "Ejercicios de Principal" });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Gymkhana Ficticia");
    expect(items[1]).toHaveTextContent("Slalom Ficticio");
  });
});

// ---------------------------------------------------------------------------
// Suite: submit y payload
// ---------------------------------------------------------------------------

describe("SessionAssembler — envío del formulario", () => {
  it("onSubmit recibe el payload con los items en el orden posicional correcto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <SessionAssembler
        exercises={EXERCISES}
        athletes={[]}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    fillSessionMeta();
    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");
    await addExerciseToSegment(user, "Principal", "Equilibrio Ficticio");

    await user.click(screen.getByRole("button", { name: "Guardar sesión técnica" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const payload = onSubmit.mock.calls[0][0];

    // Verify segment ordering: calentamiento → principal
    expect(payload.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          exercise_id: EX_SLALOM.id,
          segment: "calentamiento",
          position: 1,
        }),
        expect.objectContaining({
          exercise_id: EX_GYMKHANA.id,
          segment: "principal",
          position: 1,
        }),
        expect.objectContaining({
          exercise_id: EX_EQUILIBRIO.id,
          segment: "principal",
          position: 2,
        }),
      ]),
    );
  });

  it("onSubmit incluye scheduled_start_time con segundos (:00)", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <SessionAssembler
        exercises={EXERCISES}
        athletes={[]}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    fillSessionMeta();
    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");

    await user.click(screen.getByRole("button", { name: "Guardar sesión técnica" }));

    const payload = onSubmit.mock.calls[0][0];
    expect(payload.scheduled_start_time).toMatch(/^\d{2}:\d{2}:00$/);
  });

  it("onSubmit incluye los convocados seleccionados", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <SessionAssembler
        exercises={EXERCISES}
        athletes={ATHLETES}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    fillSessionMeta();
    await addExerciseToSegment(user, "Principal", "Slalom Ficticio");

    // Select athlete A only
    await user.click(
      screen.getByRole("button", { name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}` }),
    );

    await user.click(screen.getByRole("button", { name: "Guardar sesión técnica" }));

    const payload = onSubmit.mock.calls[0][0];
    expect(payload.convocados_athlete_ids).toContain(ATHLETE_A.id);
    expect(payload.convocados_athlete_ids).not.toContain(ATHLETE_B.id);
  });

  it("onSubmit no se llama si no hay ejercicios en ningún segmento", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <SessionAssembler
        exercises={EXERCISES}
        athletes={[]}
        onSubmit={onSubmit}
        isPending={false}
        errorMessage={null}
      />,
    );

    fillSessionMeta();
    // Submit button is disabled — click should not fire
    const submitBtn = screen.getByRole("button", { name: "Guardar sesión técnica" });
    expect(submitBtn).toBeDisabled();
    await user.click(submitBtn);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado isPending
// ---------------------------------------------------------------------------

describe("SessionAssembler — estado isPending", () => {
  it("el botón muestra 'Guardando sesión…' cuando isPending=true", () => {
    renderAssembler({ isPending: true });

    expect(
      screen.getByRole("button", { name: "Guardando sesión…" }),
    ).toBeInTheDocument();
  });

  it("el botón está deshabilitado cuando isPending=true", () => {
    renderAssembler({ isPending: true });

    expect(
      screen.getByRole("button", { name: "Guardando sesión…" }),
    ).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: errorMessage
// ---------------------------------------------------------------------------

describe("SessionAssembler — errorMessage", () => {
  it("muestra el mensaje de error con role=alert cuando errorMessage está definido", () => {
    renderAssembler({ errorMessage: "No se pudo guardar la sesión. Intenta de nuevo." });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No se pudo guardar la sesión. Intenta de nuevo.");
  });

  it("no muestra ningún role=alert cuando errorMessage es null", () => {
    renderAssembler({ errorMessage: null });

    // The only role="status" present should be the empty-items warning, not an alert
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: convocados
// ---------------------------------------------------------------------------

describe("SessionAssembler — convocados", () => {
  it("muestra la sección de convocados cuando hay atletas", () => {
    renderAssembler();

    expect(screen.getByRole("group", { name: "Seleccionar deportistas convocados" })).toBeInTheDocument();
  });

  it("no muestra la sección de convocados cuando athletes=[]", () => {
    renderAssembler({ athletes: [] });

    expect(
      screen.queryByRole("group", { name: "Seleccionar deportistas convocados" }),
    ).not.toBeInTheDocument();
  });

  it("cada atleta aparece como botón con aria-pressed=false inicialmente", () => {
    renderAssembler();

    const btnA = screen.getByRole("button", {
      name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}`,
    });
    expect(btnA).toHaveAttribute("aria-pressed", "false");
  });

  it("clicar un atleta cambia aria-pressed a true", async () => {
    const user = userEvent.setup();
    renderAssembler();

    const btnA = screen.getByRole("button", {
      name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}`,
    });
    await user.click(btnA);

    expect(btnA).toHaveAttribute("aria-pressed", "true");
  });

  it("clicar un atleta seleccionado lo deselecciona (aria-pressed vuelve a false)", async () => {
    const user = userEvent.setup();
    renderAssembler();

    const btnA = screen.getByRole("button", {
      name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}`,
    });
    await user.click(btnA); // select
    await user.click(btnA); // deselect

    expect(btnA).toHaveAttribute("aria-pressed", "false");
  });

  it("el badge de 'X seleccionados' aparece al seleccionar atletas", async () => {
    const user = userEvent.setup();
    renderAssembler();

    await user.click(
      screen.getByRole("button", {
        name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}`,
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: `${ATHLETE_B.first_name} ${ATHLETE_B.last_name}`,
      }),
    );

    expect(screen.getByText("2 seleccionados")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: MixedAgeNotice (componente standalone — usado en SessionBuilderPage
//  tras recibir el resultado de la mutación)
// ---------------------------------------------------------------------------

describe("MixedAgeNotice", () => {
  it("renderiza el aviso cuando mixes_age_bands=true", () => {
    render(<MixedAgeNotice mixes_age_bands={true} />);

    expect(
      screen.getByText("Sesión con franjas de edad mixtas"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Recuerda adaptar las instrucciones/),
    ).toBeInTheDocument();
  });

  it("usa role=alert para que los lectores de pantalla lo anuncien inmediatamente", () => {
    render(<MixedAgeNotice mixes_age_bands={true} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("no renderiza nada cuando mixes_age_bands=false", () => {
    const { container } = render(<MixedAgeNotice mixes_age_bands={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("no renderiza nada cuando mixes_age_bands no se pasa (undefined)", () => {
    const { container } = render(<MixedAgeNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("la sesión que mezcla franjas 10-12 y 13-15 activa el aviso", () => {
    // This is a pure display test: when the parent passes mixes_age_bands=true
    // (computed by the backend after POST /api/technique/sessions),
    // the notice must render.
    render(<MixedAgeNotice mixes_age_bands={true} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sesión con franjas de edad mixtas",
    );
  });

  it("no tiene violaciones de accesibilidad cuando está visible", async () => {
    const { container } = render(<MixedAgeNotice mixes_age_bands={true} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad cuando no renderiza", async () => {
    const { container } = render(<MixedAgeNotice mixes_age_bands={false} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad — SessionAssembler
// ---------------------------------------------------------------------------

describe("SessionAssembler — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado inicial (sin ejercicios)", async () => {
    const { container } = renderAssembler();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con ejercicios en los tres segmentos", async () => {
    const user = userEvent.setup();
    const { container } = renderAssembler();

    await addExerciseToSegment(user, "Calentamiento", "Slalom Ficticio");
    await addExerciseToSegment(user, "Principal", "Gymkhana Ficticia");
    await addExerciseToSegment(user, "Vuelta a la calma", "Equilibrio Ficticio");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con atletas seleccionados", async () => {
    const user = userEvent.setup();
    const { container } = renderAssembler();

    await user.click(
      screen.getByRole("button", {
        name: `${ATHLETE_A.first_name} ${ATHLETE_A.last_name}`,
      }),
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando isPending=true", async () => {
    const { container } = renderAssembler({ isPending: true });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando hay un errorMessage", async () => {
    const { container } = renderAssembler({
      errorMessage: "Error al guardar la sesión.",
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});
