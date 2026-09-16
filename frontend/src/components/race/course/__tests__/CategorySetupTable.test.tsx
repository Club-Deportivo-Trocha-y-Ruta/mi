/**
 * Tests para CategorySetupTable (feature 043 — perfil de circuito, T029).
 *
 * Cubre:
 *  - Banner "Sugerido desde la válida anterior": aparece SOLO cuando
 *    `setups` está vacío y `suggestedSetups` no lo está.
 *  - Filas en blanco se omiten del payload enviado (`PUT .../setups`).
 *  - Vueltas fuera de rango (>20) muestran un error inline vía Zod, no un
 *    globo nativo de HTML5 — el `<form>` tiene `noValidate`.
 */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { makeCourseRead, makeCourseVariant } from "@/test/msw/raceCourseHandlers";
import { CategorySetupTable } from "@/components/race/course/CategorySetupTable";
import type {
  CourseSetup,
  CourseVariant,
  SuggestedSetup,
} from "@/types/raceCourse.types";

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

const VARIANT: CourseVariant = makeCourseVariant({ id: 7, label: "Circuito completo" });

const SETUP: CourseSetup = {
  category_id: 12,
  category_code: "INF_M",
  category_label: "Infantil masculino",
  laps: 3,
  variant_id: 7,
};

const SUGGESTED: SuggestedSetup = {
  category_id: 12,
  category_label: "Infantil masculino",
  laps: 3,
  variant_label: "Circuito completo",
  source_event_id: 38,
};

// ---------------------------------------------------------------------------
// Banner "Sugerido desde la válida anterior"
// ---------------------------------------------------------------------------

describe("CategorySetupTable — banner de sugerencia", () => {
  it("aparece cuando setups está vacío y suggestedSetups no lo está; botón 'Confirmar vueltas'", () => {
    wrap(
      <CategorySetupTable
        raceEventId={41}
        setups={[]}
        suggestedSetups={[SUGGESTED]}
        variants={[VARIANT]}
        resultCategories={[{ category_id: 12, label: "Infantil masculino" }]}
      />,
    );

    expect(
      screen.getByTestId("course-setup-suggested-banner"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("course-setup-save")).toHaveTextContent(
      "Confirmar vueltas",
    );
  });

  it("NO aparece cuando setups ya tiene filas, aunque haya suggestedSetups; botón 'Guardar'", () => {
    wrap(
      <CategorySetupTable
        raceEventId={41}
        setups={[SETUP]}
        suggestedSetups={[SUGGESTED]}
        variants={[VARIANT]}
        resultCategories={[{ category_id: 12, label: "Infantil masculino" }]}
      />,
    );

    expect(
      screen.queryByTestId("course-setup-suggested-banner"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("course-setup-save")).toHaveTextContent(
      "Guardar",
    );
  });

  it("NO aparece cuando ambos (setups y suggestedSetups) están vacíos", () => {
    wrap(
      <CategorySetupTable
        raceEventId={41}
        setups={[]}
        suggestedSetups={[]}
        variants={[VARIANT]}
        resultCategories={[{ category_id: 12, label: "Infantil masculino" }]}
      />,
    );

    expect(
      screen.queryByTestId("course-setup-suggested-banner"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Filas en blanco omitidas del payload
// ---------------------------------------------------------------------------

describe("CategorySetupTable — filas en blanco omitidas", () => {
  it("solo envía las categorías con vueltas indicadas; la fila en blanco no viaja en el payload", async () => {
    let capturedBody: { setups: Array<Record<string, number>> } | null = null;
    mswServer.use(
      http.put(`${BASE}/:id/course/setups`, async ({ request }) => {
        capturedBody = (await request.json()) as typeof capturedBody;
        return HttpResponse.json(makeCourseRead());
      }),
    );

    const user = userEvent.setup();
    wrap(
      <CategorySetupTable
        raceEventId={41}
        setups={[]}
        suggestedSetups={[]}
        variants={[VARIANT]}
        resultCategories={[
          { category_id: 12, label: "Infantil masculino" },
          { category_id: 13, label: "Juvenil masculino" },
        ]}
      />,
    );

    // Categoría 12: se completa (vueltas + variante).
    fireEvent.change(screen.getByTestId("course-setup-laps-12"), {
      target: { value: "3" },
    });
    await user.selectOptions(
      screen.getByTestId("course-setup-variant-12"),
      String(VARIANT.id),
    );

    // Categoría 13: se deja en blanco (ni vueltas ni variante).

    await user.click(screen.getByTestId("course-setup-save"));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody!.setups).toEqual([
      { category_id: 12, laps: 3, variant_id: VARIANT.id },
    ]);
  });
});

// ---------------------------------------------------------------------------
// Validación — vueltas fuera de rango (error inline, no HTML5 nativo)
// ---------------------------------------------------------------------------

describe("CategorySetupTable — validación de vueltas fuera de rango", () => {
  it("25 vueltas (máximo 20) muestra un error inline vía Zod y NO dispara la mutation", async () => {
    let putCalled = false;
    mswServer.use(
      http.put(`${BASE}/:id/course/setups`, () => {
        putCalled = true;
        return HttpResponse.json(makeCourseRead());
      }),
    );

    const user = userEvent.setup();
    const { container } = wrap(
      <CategorySetupTable
        raceEventId={41}
        setups={[]}
        suggestedSetups={[]}
        variants={[VARIANT]}
        resultCategories={[{ category_id: 12, label: "Infantil masculino" }]}
      />,
    );

    // El <form> desactiva la validación nativa del navegador — la etapa de
    // validación es exclusivamente el schema Zod, nunca un globo HTML5.
    const form = container.querySelector("form");
    expect(form).not.toBeNull();
    expect(form!.noValidate).toBe(true);

    fireEvent.change(screen.getByTestId("course-setup-laps-12"), {
      target: { value: "25" },
    });
    await user.selectOptions(
      screen.getByTestId("course-setup-variant-12"),
      String(VARIANT.id),
    );

    await user.click(screen.getByTestId("course-setup-save"));

    const error = await screen.findByTestId("course-setup-row-error-12");
    expect(error).toHaveTextContent("Máximo 20 vueltas");
    expect(error).toHaveAttribute("role", "alert");
    expect(putCalled).toBe(false);
  });
});
