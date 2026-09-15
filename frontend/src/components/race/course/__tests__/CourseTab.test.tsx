/**
 * Tests para CourseTab (feature 043 — perfil de circuito, T029).
 *
 * Cubre:
 *  - Estado vacío (`makeEmptyCourseRead()`).
 *  - Estado completo (`makeCourseRead()`): variantes + vueltas por
 *    categoría visibles.
 *  - `readOnly` se propaga a `VariantsCard` (oculta "Agregar variante") y
 *    a la propia tarjeta vacía (oculta sus acciones — bugfix: antes se
 *    mostraban también para el rol parent, contra `ui-course.md` §2:
 *    "coach/admin only").
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { raceCourseEmptyHandler } from "@/test/msw/raceCourseHandlers";
import { CourseTab } from "@/components/race/course/CourseTab";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

// ---------------------------------------------------------------------------
// Estado vacío
// ---------------------------------------------------------------------------

describe("CourseTab — estado vacío", () => {
  it("coach/admin: muestra 'Sin circuito registrado' + botones de acción", async () => {
    mswServer.use(raceCourseEmptyHandler);
    wrap(<CourseTab raceEventId={41} />);

    expect(await screen.findByTestId("course-tab-empty")).toBeInTheDocument();
    expect(
      screen.getByText("Sin circuito registrado"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("course-tab-add-variant-btn"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("course-tab-describe-btn")).toBeInTheDocument();
  });

  it("readOnly=true (parent): oculta las acciones de edición del estado vacío", async () => {
    mswServer.use(raceCourseEmptyHandler);
    wrap(<CourseTab raceEventId={41} readOnly />);

    expect(await screen.findByTestId("course-tab-empty")).toBeInTheDocument();
    // El título y el texto explicativo siguen visibles.
    expect(screen.getByText("Sin circuito registrado")).toBeInTheDocument();
    // Pero ninguna acción de edición — "coach/admin only" (ui-course.md §2).
    expect(
      screen.queryByTestId("course-tab-add-variant-btn"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("course-tab-describe-btn"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado completo
// ---------------------------------------------------------------------------

describe("CourseTab — estado completo", () => {
  it("renderiza VariantsCard y CategorySetupTable con los datos servidos", async () => {
    // Fixture feliz por defecto (`raceCourseHandlers` registrado global) →
    // `makeCourseRead()`: 1 variante + 1 setup.
    wrap(<CourseTab raceEventId={41} />);

    const variantsCard = await screen.findByTestId("course-variants-card");
    // "Circuito completo" también aparece como <option> del select de
    // variantes en CategorySetupTable — se acota a la tarjeta de variantes.
    expect(within(variantsCard).getByText("Circuito completo")).toBeInTheDocument();
    expect(screen.getByTestId("course-setup-table")).toBeInTheDocument();
    expect(screen.getByText("Infantil masculino")).toBeInTheDocument();
    // Estado vacío no debe coexistir con el completo.
    expect(screen.queryByTestId("course-tab-empty")).not.toBeInTheDocument();
  });

  it("coach/admin (readOnly=false, default): 'Agregar variante' de VariantsCard visible", async () => {
    wrap(<CourseTab raceEventId={41} />);
    expect(await screen.findByTestId("course-variants-card")).toBeInTheDocument();
    expect(screen.getByTestId("course-variants-add-btn")).toBeInTheDocument();
  });

  it("readOnly=true: se propaga a VariantsCard y oculta 'Agregar variante'", async () => {
    wrap(<CourseTab raceEventId={41} readOnly />);
    expect(await screen.findByTestId("course-variants-card")).toBeInTheDocument();
    expect(
      screen.queryByTestId("course-variants-add-btn"),
    ).not.toBeInTheDocument();
  });
});
