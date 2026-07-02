/**
 * Tests para AthleteProgressPage (US4 / T037-T038):
 *   - `athleteId` inválido en la ruta (no numérico / ≤0) → mensaje de alerta
 *     de identificador inválido, en lugar de intentar cargar el tablero.
 *   - `athleteId` válido → carga (lazy) `ProgressNotesBoard` con el id
 *     tomado del parámetro de ruta y muestra el estado actual del atleta.
 *   - Encabezado y enlace "Perfil del deportista" apuntan al atleta correcto.
 *   - jest-axe sin violaciones en: id inválido, estado de carga (skeleton) y
 *     estado exitoso con datos.
 *
 * Mirror de `components/technique/__tests__/SkillProgressBoard.test.tsx`
 * (feature 018) para el patrón MSW + jest-axe; construye su propio wrapper
 * con `<Routes>` porque la página depende de `useParams`.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

import { AthleteProgressPage } from "@/routes/strength/AthleteProgressPage";
import { mswServer } from "@/test/setup";
import {
  makeAthleteProgress,
  makeCatalogList,
  makeExerciseListItem,
  makeProgressOut,
} from "@/test/msw/strengthHandlers";

expect.extend(toHaveNoViolations);

const ATHLETE_ID = 88; // atleta ficticio

// ---------------------------------------------------------------------------
// Helpers de render
// ---------------------------------------------------------------------------

function renderPage(athleteId: string | number = ATHLETE_ID) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter
        initialEntries={[`/strength/athletes/${athleteId}/progress`]}
      >
        <Routes>
          <Route
            path="/strength/athletes/:athleteId/progress"
            element={<AthleteProgressPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function progressHandler(athleteId: number) {
  return http.get(
    `*/api/strength/athletes/${athleteId}/progress`,
    () =>
      HttpResponse.json(
        makeAthleteProgress([
          makeProgressOut({
            exercise_id: 1,
            exercise_name: "Sentadilla con peso corporal",
            status: "en_progreso",
          }),
        ]),
      ),
  );
}

const catalogHandler = http.get("*/api/strength/exercises", () =>
  HttpResponse.json(
    makeCatalogList([
      makeExerciseListItem({ id: 1, name: "Sentadilla con peso corporal" }),
    ]),
  ),
);

// ---------------------------------------------------------------------------
// athleteId inválido
// ---------------------------------------------------------------------------

describe("AthleteProgressPage — athleteId inválido", () => {
  it("muestra un mensaje de alerta cuando el id no es numérico", async () => {
    renderPage("abc");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "El identificador del deportista no es válido.",
    );
  });

  it("no intenta renderizar el tablero de progreso con un id inválido", async () => {
    renderPage("abc");

    await screen.findByRole("alert");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con id inválido", async () => {
    const { container } = renderPage("abc");

    await screen.findByRole("alert");
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// athleteId válido — encabezado y navegación
// ---------------------------------------------------------------------------

describe("AthleteProgressPage — encabezado y navegación", () => {
  it("muestra el título 'Progreso de fuerza y acondicionamiento'", async () => {
    mswServer.use(progressHandler(ATHLETE_ID), catalogHandler);

    renderPage();

    expect(
      screen.getByRole("heading", {
        name: "Progreso de fuerza y acondicionamiento",
      }),
    ).toBeInTheDocument();
  });

  it("el enlace 'Perfil del deportista' apunta al atleta de la ruta", async () => {
    mswServer.use(progressHandler(ATHLETE_ID), catalogHandler);

    renderPage();

    const link = screen.getByRole("link", {
      name: "Volver al perfil del deportista",
    });
    expect(link).toHaveAttribute("href", `/athletes/${ATHLETE_ID}`);
  });
});

// ---------------------------------------------------------------------------
// athleteId válido — carga y estado exitoso (lazy ProgressNotesBoard)
// ---------------------------------------------------------------------------

describe("AthleteProgressPage — carga del tablero (lazy)", () => {
  it("muestra un skeleton de carga con role=status mientras el chunk/datos cargan", async () => {
    mswServer.use(
      http.get(
        `*/api/strength/athletes/${ATHLETE_ID}/progress`,
        async () => {
          await new Promise(() => {}); // nunca resuelve — mantiene loading
        },
      ),
      catalogHandler,
    );

    renderPage();

    const status = await screen.findByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
  });

  it("renderiza el tablero de progreso con los datos del atleta correcto", async () => {
    mswServer.use(progressHandler(ATHLETE_ID), catalogHandler);

    renderPage();

    const table = await screen.findByRole("table", {
      name: "Estado actual de ejercicios de fuerza — solo este deportista",
    });
    expect(
      screen.getByText("Sentadilla con peso corporal"),
    ).toBeInTheDocument();
    expect(table).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en el skeleton de carga", async () => {
    mswServer.use(
      http.get(
        `*/api/strength/athletes/${ATHLETE_ID}/progress`,
        async () => {
          await new Promise(() => {});
        },
      ),
      catalogHandler,
    );

    const { container } = renderPage();

    await screen.findByRole("status");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad en el estado exitoso con datos", async () => {
    mswServer.use(progressHandler(ATHLETE_ID), catalogHandler);

    const { container } = renderPage();

    await screen.findByRole("table", {
      name: "Estado actual de ejercicios de fuerza — solo este deportista",
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});
