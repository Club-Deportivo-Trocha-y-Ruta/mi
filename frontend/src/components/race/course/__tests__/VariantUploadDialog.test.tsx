/**
 * Tests para VariantUploadDialog (feature 043 — perfil de circuito, T029).
 *
 * Cubre:
 *  - Copy de detección exacta para las 3 ramas de `DetectionMethod`
 *    (`closed_loop`, `manual`, `single`) — texto verbatim de
 *    `ui-course.md` §2; `single` no pregunta (`quickstart.md` §6 paso 2).
 *  - Un error de subida (422 `too_short`) se muestra inline en español,
 *    nunca el texto crudo del backend.
 *  - Cada control interactivo, en las 4 etapas del flujo, trae la clase
 *    Tailwind `min-h-12` (objetivo táctil ≥48px) — `getBoundingClientRect`
 *    no es confiable en jsdom, así que se verifica la clase (mismo patrón
 *    que `DurationPicker.test.tsx`).
 *  - 0 violaciones jest-axe con el sheet abierto.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import {
  makeCourseRead,
  makeCourseVariant,
  raceCourseTooShortHandler,
} from "@/test/msw/raceCourseHandlers";
import { VariantUploadDialog } from "@/components/race/course/VariantUploadDialog";

const BASE = "*/api/race-analysis/race-events";
const TOUCH_TARGET_RE = /min-h-\[48px\]|min-h-12/;

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function makeGpxFile(name = "vuelta.gpx"): File {
  return new File(["<gpx></gpx>"], name, { type: "application/gpx+xml" });
}

/** Selecciona un GPX en el input visible (etapa "form"). */
async function selectFile(user: ReturnType<typeof userEvent.setup>) {
  const input = screen.getByTestId("variant-upload-file") as HTMLInputElement;
  await user.upload(input, makeGpxFile());
}

function renderDialog() {
  return wrap(
    <VariantUploadDialog
      raceEventId={41}
      open={true}
      onOpenChange={() => {}}
      defaultLabel="Circuito completo"
    />,
  );
}

// ---------------------------------------------------------------------------
// Copy de detección — closed_loop / manual / single
// ---------------------------------------------------------------------------

describe("VariantUploadDialog — copy de detección", () => {
  it("closed_loop: 'Detectamos {N} vueltas de {km} km ({m} m de desnivel). ¿Es correcto?'", async () => {
    // Fixture feliz por defecto: makeCourseVariant() → closed_loop, 3 vueltas,
    // 4.2 km, 110 m de desnivel.
    const user = userEvent.setup();
    renderDialog();

    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));

    const question = await screen.findByTestId("variant-upload-question");
    expect(question).toHaveTextContent(
      "Detectamos 3 vueltas de 4.2 km (110 m de desnivel). ¿Es correcto?",
    );
  });

  it("closed_loop sin elevación: usa 'sin dato' en vez de null/undefined", async () => {
    mswServer.use(
      http.post(`${BASE}/:id/course/variants`, () =>
        HttpResponse.json(
          makeCourseRead({
            variants: [
              makeCourseVariant({
                lap_distance_km: 2.5,
                elevation_gain_m: null,
                has_elevation: false,
                detection: {
                  method: "closed_loop",
                  laps_detected: 2,
                  total_distance_m: 5000,
                },
              }),
            ],
          }),
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderDialog();
    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));

    const question = await screen.findByTestId("variant-upload-question");
    expect(question).toHaveTextContent(
      "Detectamos 2 vueltas de 2.5 km (sin dato m de desnivel). ¿Es correcto?",
    );
  });

  it("manual: 'No detectamos una vuelta cerrada; ... ({km} km). Si grabaste varias vueltas, indícalo.'", async () => {
    mswServer.use(
      http.post(`${BASE}/:id/course/variants`, () =>
        HttpResponse.json(
          makeCourseRead({
            variants: [
              makeCourseVariant({
                lap_distance_km: 5.1,
                elevation_gain_m: 80,
                detection: {
                  method: "manual",
                  laps_detected: 1,
                  total_distance_m: 5100,
                },
              }),
            ],
          }),
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderDialog();
    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));

    const question = await screen.findByTestId("variant-upload-question");
    expect(question).toHaveTextContent(
      "No detectamos una vuelta cerrada; se tomó toda la grabación como una vuelta (5.1 km). Si grabaste varias vueltas, indícalo.",
    );
  });

  it("single: NO pregunta — pasa directo al mensaje de éxito ('Variante guardada: {km} km.')", async () => {
    mswServer.use(
      http.post(`${BASE}/:id/course/variants`, () =>
        HttpResponse.json(
          makeCourseRead({
            variants: [
              makeCourseVariant({
                lap_distance_km: 3.8,
                detection: {
                  method: "single",
                  laps_detected: 1,
                  total_distance_m: 3800,
                },
              }),
            ],
          }),
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderDialog();
    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));

    const success = await screen.findByTestId("variant-upload-success");
    expect(success).toHaveTextContent("Variante guardada: 3.8 km.");
    expect(
      screen.queryByTestId("variant-upload-question"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Error inline — nunca texto crudo del backend
// ---------------------------------------------------------------------------

describe("VariantUploadDialog — error de subida", () => {
  it("422 too_short muestra el mensaje fijo en español, inline", async () => {
    mswServer.use(raceCourseTooShortHandler);

    const user = userEvent.setup();
    renderDialog();
    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));

    const error = await screen.findByTestId("variant-upload-error");
    expect(error).toHaveTextContent(
      "El recorrido es demasiado corto para ser una vuelta (menos de 300 m).",
    );
    // La etapa sigue en "form" — el error no avanza el flujo.
    expect(
      screen.queryByTestId("variant-upload-question"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("variant-upload-success"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Objetivos táctiles ≥48px — las 4 etapas
// ---------------------------------------------------------------------------

describe("VariantUploadDialog — objetivos táctiles (≥48px)", () => {
  it("cada control interactivo de las 4 etapas trae la clase min-h-12", async () => {
    const user = userEvent.setup();
    renderDialog();

    // Etapa "form"
    expect(screen.getByTestId("variant-upload-label").className).toMatch(
      TOUCH_TARGET_RE,
    );
    expect(screen.getByTestId("variant-upload-file").className).toMatch(
      TOUCH_TARGET_RE,
    );
    expect(
      screen.getByRole("button", { name: /^Cancelar$/i }).className,
    ).toMatch(TOUCH_TARGET_RE);
    expect(screen.getByTestId("variant-upload-submit").className).toMatch(
      TOUCH_TARGET_RE,
    );

    await selectFile(user);
    await user.click(screen.getByTestId("variant-upload-submit"));
    await screen.findByTestId("variant-upload-question");

    // Etapa "question" (closed_loop, fixture feliz por defecto)
    expect(
      screen.getByTestId("variant-upload-indicate-laps").className,
    ).toMatch(TOUCH_TARGET_RE);
    expect(screen.getByTestId("variant-upload-confirm").className).toMatch(
      TOUCH_TARGET_RE,
    );

    await user.click(screen.getByTestId("variant-upload-indicate-laps"));

    // Etapa "laps-input"
    expect(
      screen.getByTestId("variant-upload-recorded-laps").className,
    ).toMatch(TOUCH_TARGET_RE);
    expect(
      screen.getByTestId("variant-upload-laps-submit").className,
    ).toMatch(TOUCH_TARGET_RE);

    await user.type(screen.getByTestId("variant-upload-recorded-laps"), "2");
    await user.click(screen.getByTestId("variant-upload-laps-submit"));

    // Etapa "success" (recorded_laps ya enviado → no vuelve a preguntar)
    const closeBtn = await screen.findByTestId("variant-upload-close");
    expect(closeBtn.className).toMatch(TOUCH_TARGET_RE);
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("VariantUploadDialog — accesibilidad", () => {
  it("0 violaciones jest-axe con el sheet abierto (etapa form)", async () => {
    renderDialog();
    await screen.findByTestId("variant-upload-file");
    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
