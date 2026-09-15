/**
 * Tests para EditCourseDescriptionDialog (feature 043, User Story 3, T044).
 *
 * Cubre:
 *  - El contador de caracteres de "Notas" se actualiza en vivo mientras el
 *    usuario escribe.
 *  - Un valor de 1000+ caracteres en notas dispara el error de Zod inline
 *    (nunca una burbuja nativa del navegador — el `<form>` usa `noValidate`).
 *  - Los 8 checkboxes de "Sectores clave" se renderizan con su etiqueta en
 *    español y son independientemente marcables.
 *  - El grupo de dificultad técnica renderiza las 5 opciones etiquetadas.
 *  - El submit dispara la mutation (interceptada via MSW, no mockeada) con
 *    el shape de body esperado.
 *  - 0 violaciones jest-axe con el sheet abierto.
 *
 * Estrategia: mismo patrón que `EditConditionsDialog.test.tsx` (QueryClient
 * real por test, `axe(document.body)` porque el Sheet de Radix porta fuera
 * del container), pero interceptando el PATCH via `mswServer.use(...)` en
 * vez de `vi.mock("@/api/...")`, siguiendo la convención de este módulo
 * (`raceCourseHandlers` ya registrado globalmente en `test/setup.ts`).
 */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { makeCourseRead } from "@/test/msw/raceCourseHandlers";
import { EditCourseDescriptionDialog } from "@/components/race/course/EditCourseDescriptionDialog";
import type { CourseDescriptionUpdateBody } from "@/types/raceCourse.types";

// jsdom no implementa ResizeObserver — lo necesitan internamente
// `@radix-ui/react-checkbox` y `@radix-ui/react-radio-group` (sectores clave
// y dificultad técnica) para dimensionar su input nativo oculto. Mismo
// patrón defensivo que `GrowthTab.parent.test.tsx`/`PercentileChart.test.tsx`.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

const BASE = "*/api/race-analysis/race-events";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function renderDialog(
  currentDescription: Parameters<
    typeof EditCourseDescriptionDialog
  >[0]["currentDescription"] = null,
) {
  return wrap(
    <EditCourseDescriptionDialog
      raceEventId={41}
      currentDescription={currentDescription}
      open={true}
      onOpenChange={() => {}}
    />,
  );
}

/** Intercepta el PATCH y captura el body enviado, respondiendo 201. */
function captureDescriptionPatch(): { body: CourseDescriptionUpdateBody | null } {
  const captured: { body: CourseDescriptionUpdateBody | null } = { body: null };
  mswServer.use(
    http.patch(`${BASE}/:id/course/description`, async ({ request }) => {
      captured.body = (await request.json()) as CourseDescriptionUpdateBody;
      return HttpResponse.json(makeCourseRead());
    }),
  );
  return captured;
}

// ---------------------------------------------------------------------------
// Contador de caracteres
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — contador de caracteres", () => {
  it("se actualiza en vivo mientras el usuario escribe en Notas", async () => {
    const user = userEvent.setup();
    renderDialog();

    const notes = await screen.findByLabelText("Notas");
    const counter = screen.getByTestId("ecd-notes-counter");
    expect(counter).toHaveTextContent("0/1000");

    await user.type(notes, "Hola");
    expect(counter).toHaveTextContent("4/1000");

    await user.type(notes, " mundo");
    expect(counter).toHaveTextContent("10/1000");
  });
});

// ---------------------------------------------------------------------------
// Validación de notas > 1000 caracteres — error de Zod, sin burbuja nativa
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — validación de notas", () => {
  it("1001 caracteres en notas muestra el error de Zod inline y bloquea el submit", async () => {
    const captured = captureDescriptionPatch();
    const user = userEvent.setup();
    renderDialog();

    const notes = (await screen.findByLabelText("Notas")) as HTMLTextAreaElement;
    // `fireEvent.change` fija `.value` directamente (sin pasar por el
    // tecleo/paste simulado de userEvent, que sí respeta `maxLength` como lo
    // haría un navegador real) — necesario para que el 1001º carácter llegue
    // al estado del form y sea Zod (no el navegador) quien lo rechace.
    fireEvent.change(notes, { target: { value: "a".repeat(1001) } });

    const form = document.getElementById(
      "edit-course-description-form",
    ) as HTMLFormElement;
    // El form nunca delega en la validación nativa del navegador — Zod es la
    // única fuente de mensajes de error visibles.
    expect(form).toHaveAttribute("novalidate");

    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    const alert = await screen.findByText("Máximo 1000 caracteres.");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveAttribute("role", "alert");

    // Ninguna burbuja nativa (`:invalid`) reemplaza el mensaje — es el único
    // texto de error visible, y el submit no llegó a disparar la mutation.
    expect(screen.queryAllByText(/Máximo 1000 caracteres\./)).toHaveLength(1);
    expect(captured.body).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Sectores clave — 8 checkboxes, etiquetas en español, toggle independiente
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — sectores clave", () => {
  const SECTOR_LABELS = [
    "Subida larga",
    "Bajada técnica",
    "Rock garden",
    "Singletrack",
    "Plano rápido",
    "Paso de quebrada",
    "Raíces",
    "Escalones",
  ];

  it("renderiza los 8 checkboxes con su etiqueta en español, todos sin marcar", async () => {
    renderDialog();
    await screen.findByLabelText("Notas");

    for (const label of SECTOR_LABELS) {
      const checkbox = screen.getByRole("checkbox", { name: label });
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).toHaveAttribute("aria-checked", "false");
    }
  });

  it("cada checkbox se marca/desmarca de forma independiente de los demás", async () => {
    const user = userEvent.setup();
    renderDialog();
    await screen.findByLabelText("Notas");

    const subida = screen.getByRole("checkbox", { name: "Subida larga" });
    const rockGarden = screen.getByRole("checkbox", { name: "Rock garden" });
    const raices = screen.getByRole("checkbox", { name: "Raíces" });

    await user.click(subida);
    await user.click(rockGarden);

    expect(subida).toHaveAttribute("aria-checked", "true");
    expect(rockGarden).toHaveAttribute("aria-checked", "true");
    // El resto permanece sin marcar.
    expect(raices).toHaveAttribute("aria-checked", "false");

    // Desmarcar uno no afecta al otro.
    await user.click(subida);
    expect(subida).toHaveAttribute("aria-checked", "false");
    expect(rockGarden).toHaveAttribute("aria-checked", "true");
  });
});

// ---------------------------------------------------------------------------
// Dificultad técnica — 5 opciones etiquetadas
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — dificultad técnica", () => {
  it("renderiza las 5 opciones de dificultad etiquetadas", async () => {
    renderDialog();
    await screen.findByLabelText("Notas");

    const group = screen.getByRole("radiogroup", { name: "Dificultad técnica" });
    const expectedLabels = [
      "1 — Muy fácil",
      "2 — Fácil",
      "3 — Media",
      "4 — Técnico",
      "5 — Muy técnico",
    ];
    for (const label of expectedLabels) {
      expect(within(group).getByRole("radio", { name: label })).toBeInTheDocument();
    }
  });
});

// ---------------------------------------------------------------------------
// Submit — dispara la mutation con el body esperado
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — submit", () => {
  it("sin cambios (valores por defecto): body con los 4 campos en null/vacío", async () => {
    const captured = captureDescriptionPatch();
    const user = userEvent.setup();
    renderDialog();
    await screen.findByLabelText("Notas");

    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() => expect(captured.body).not.toBeNull());
    expect(captured.body).toEqual({
      terrain_type: null,
      technical_difficulty: null,
      key_sectors: [],
      course_notes: null,
    });
  });

  it("con los 4 campos completados: body refleja terreno, dificultad, sectores y notas", async () => {
    const captured = captureDescriptionPatch();
    const user = userEvent.setup();
    renderDialog();
    await screen.findByLabelText("Notas");

    await user.click(screen.getByRole("radio", { name: "Mixto" }));
    await user.click(screen.getByRole("radio", { name: "3 — Media" }));
    await user.click(screen.getByRole("checkbox", { name: "Subida larga" }));
    await user.click(screen.getByRole("checkbox", { name: "Rock garden" }));
    await user.type(screen.getByLabelText("Notas"), "Prueba de descripción.");

    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() => expect(captured.body).not.toBeNull());
    expect(captured.body).toEqual({
      terrain_type: "mixto",
      technical_difficulty: 3,
      key_sectors: ["subida_larga", "rock_garden"],
      course_notes: "Prueba de descripción.",
    });
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("EditCourseDescriptionDialog — accesibilidad", () => {
  it("0 violaciones jest-axe con el sheet abierto", async () => {
    renderDialog();
    await screen.findByLabelText("Notas");
    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
