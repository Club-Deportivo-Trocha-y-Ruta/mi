/**
 * Tests para VariantsCard (feature 043 — perfil de circuito, T029).
 *
 * Cubre:
 *  - `readOnly=false` (coach/admin): botones de acción visibles ("Agregar
 *    variante", renombrar, reemplazar archivo, borrar).
 *  - `readOnly=true` (parent): solo la lista, sin ningún botón de acción.
 *  - 409 `variant_in_use` al borrar: el diálogo de confirmación muestra las
 *    categorías afectadas (texto interpolado por el backend), sin cerrarse.
 */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import {
  makeCourseVariant,
  raceCourseVariantInUseHandler,
} from "@/test/msw/raceCourseHandlers";
import { VariantsCard } from "@/components/race/course/VariantsCard";
import type { CourseVariant } from "@/types/raceCourse.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

const VARIANT: CourseVariant = makeCourseVariant();

// ---------------------------------------------------------------------------
// RBAC — coach vs parent/readOnly
// ---------------------------------------------------------------------------

describe("VariantsCard — RBAC", () => {
  it("coach/admin (readOnly=false, default): muestra 'Agregar variante' y acciones por fila", () => {
    wrap(<VariantsCard raceEventId={41} variants={[VARIANT]} />);

    expect(screen.getByTestId("course-variants-add-btn")).toBeInTheDocument();
    expect(
      screen.getByTestId(`course-variant-rename-btn-${VARIANT.id}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`course-variant-replace-btn-${VARIANT.id}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`course-variant-delete-btn-${VARIANT.id}`),
    ).toBeInTheDocument();
  });

  it("parent (readOnly=true): NO muestra ningún botón de acción, solo la lista", () => {
    wrap(<VariantsCard raceEventId={41} variants={[VARIANT]} readOnly />);

    expect(
      screen.queryByTestId("course-variants-add-btn"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(`course-variant-rename-btn-${VARIANT.id}`),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(`course-variant-replace-btn-${VARIANT.id}`),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(`course-variant-delete-btn-${VARIANT.id}`),
    ).not.toBeInTheDocument();
    // La lista en sí sigue visible para el padre/madre.
    expect(screen.getByText(VARIANT.label)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 409 variant_in_use al borrar
// ---------------------------------------------------------------------------

describe("VariantsCard — 409 variant_in_use al borrar", () => {
  it("el diálogo de confirmación muestra las categorías que usan la variante, sin cerrarse", async () => {
    mswServer.use(raceCourseVariantInUseHandler);
    const user = userEvent.setup();
    wrap(<VariantsCard raceEventId={41} variants={[VARIANT]} />);

    await user.click(
      screen.getByTestId(`course-variant-delete-btn-${VARIANT.id}`),
    );
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /^Eliminar$/i }));

    // Texto interpolado por el backend (`raceCourseVariantInUseHandler`),
    // usado tal cual — nunca el texto fijo de la tabla de errores.
    await waitFor(() =>
      expect(
        within(dialog).getByText(
          /No se puede eliminar: la usan Infantil masculino, Infantil femenino\./,
        ),
      ).toBeInTheDocument(),
    );
    // El diálogo NO se cierra en error.
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});
