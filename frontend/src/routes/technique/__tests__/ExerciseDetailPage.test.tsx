/**
 * Tests para ExerciseDetailPage (T023 — criterios de aceptación T022).
 *
 * Cubre:
 *  - Renderiza habilidades, franjas de edad, dificultad, materiales y how_to.
 *  - Ejercicio sin material muestra "Sin material".
 *  - Ejercicio con materiales reales los lista.
 *  - Gymkhana con layout_ascii monta CircuitLayout (role="img" presente).
 *  - Ejercicio no-gymkhana no monta CircuitLayout.
 *  - Estado de carga muestra skeleton (aria-busy=true).
 *  - Estado de error 404 muestra mensaje amigable sin botón reintentar.
 *  - Estado de error genérico muestra mensaje con botón reintentar.
 *  - Badges de Juego y Gymkhana aparecen cuando las banderas están activas.
 *  - Zero violaciones de accesibilidad en estado de datos.
 *
 * Estrategia: vi.mock sobre @/hooks/technique/useTechnique para devolver
 * estados controlados sin red real. renderWithProviders provee QueryClient
 * + MemoryRouter. El id se inyecta vía ruta /technique/exercises/1.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { ExerciseDetailPage } from "../ExerciseDetailPage";
import type { ExerciseDetail } from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseTechniqueExercise = vi.fn();

vi.mock("@/hooks/technique/useTechnique", () => ({
  useTechniqueExercise: (...args: unknown[]) =>
    mockUseTechniqueExercise(...args),
}));

/**
 * @/api/technique se importa en ExerciseDetailPage solo para mapTechniqueError.
 * El mock evita que el módulo cargue @/schemas/technique.schemas, que falla en
 * tiempo de módulo por incompatibilidad de Zod v4 con .partial() + .superRefine()
 * en exerciseUpdateSchema (pre-existing issue, fuera de alcance de T023).
 */
vi.mock("@/api/technique", () => {
  const mapTechniqueError = (error: unknown) => {
    // Inspección mínima para los casos de test: 404 → not_found, resto → unknown
    const status =
      (error as { isAxiosError?: boolean; response?: { status?: number } })
        ?.response?.status;
    if (status === 404)
      return { kind: "not_found", message: "No se encontró el ejercicio o recurso solicitado." };
    return { kind: "unknown", message: "Ocurrió un error inesperado." };
  };
  return { mapTechniqueError };
});

// ---------------------------------------------------------------------------
// Fixture base — datos ficticios, nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

const EXERCISE_FICTICIO: ExerciseDetail = {
  id: 42,
  slug: "frenada-trasera-ficticia",
  name: "Frenada Trasera Ficticia",
  summary: "Técnica de frenada trasera — ejercicio ficticio.",
  difficulty: "media",
  is_game: false,
  is_gymkhana: false,
  age_bands: ["10-12", "13-15"],
  skills: [
    { code: "FR", slug: "frenado", name: "Frenado" },
    { code: "EQ", slug: "equilibrio", name: "Equilibrio" },
  ],
  materials: [
    { slug: "conos", name: "Conos", is_none: false },
    { slug: "cinta-delimitadora", name: "Cinta delimitadora", is_none: false },
  ],
  is_seeded: true,
  is_hidden: false,
  how_to:
    "Coloca los conos ficticios en línea recta.\nPresiona el freno trasero de forma progresiva.",
  layout_ascii: null,
  layout_alt: null,
  layout_json: null,
  confidence: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const EXERCISE_SIN_MATERIAL: ExerciseDetail = {
  ...EXERCISE_FICTICIO,
  id: 43,
  slug: "equilibrio-estatico-ficticio",
  name: "Equilibrio Estático Ficticio",
  materials: [{ slug: "sin_material", name: "Sin material", is_none: true }],
};

const EXERCISE_GYMKHANA: ExerciseDetail = {
  ...EXERCISE_FICTICIO,
  id: 44,
  slug: "gymkhana-conos-ficticia",
  name: "Gymkhana de Conos Ficticia",
  is_gymkhana: true,
  layout_ascii: "S --> [C1] --> [C2] --> F",
  layout_alt: "Gymkhana ficticia: Salida, dos conos, llegada.",
};

const EXERCISE_JUEGO: ExerciseDetail = {
  ...EXERCISE_FICTICIO,
  id: 45,
  slug: "juego-relevos-ficticio",
  name: "Juego de Relevos Ficticio",
  is_game: true,
};

// ---------------------------------------------------------------------------
// Helper: renderiza la página con la ruta correcta
// ---------------------------------------------------------------------------

function renderPage(exerciseId: number | string = 42) {
  return renderWithProviders(
    <Routes>
      <Route
        path="/technique/exercises/:id"
        element={<ExerciseDetailPage />}
      />
    </Routes>,
    { initialEntries: [`/technique/exercises/${exerciseId}`] },
  );
}

// ---------------------------------------------------------------------------
// Reset del mock antes de cada test
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests — estado de carga
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — estado cargando", () => {
  it("muestra skeleton con aria-busy=true mientras carga", () => {
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();
    const skeleton = screen.getByRole("status", {
      name: "Cargando ejercicio…",
    });
    expect(skeleton).toHaveAttribute("aria-busy", "true");
  });
});

// ---------------------------------------------------------------------------
// Tests — datos disponibles (ejercicio con materiales)
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — datos disponibles", () => {
  beforeEach(() => {
    mockUseTechniqueExercise.mockReturnValue({
      data: EXERCISE_FICTICIO,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renderiza el nombre del ejercicio", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: "Frenada Trasera Ficticia" }),
    ).toBeInTheDocument();
  });

  it("muestra las habilidades técnicas como badges", () => {
    renderPage();
    const skillsSection = screen
      .getByText("Habilidades técnicas")
      .closest("section");
    expect(skillsSection).not.toBeNull();
    expect(skillsSection?.textContent).toContain("Frenado");
    expect(skillsSection?.textContent).toContain("Equilibrio");
  });

  it("muestra las franjas de edad correctamente localizadas", () => {
    renderPage();
    const ageBandsSection = screen
      .getByText("Franjas de edad")
      .closest("section");
    expect(ageBandsSection).not.toBeNull();
    expect(ageBandsSection?.textContent).toContain("10-12 años");
    expect(ageBandsSection?.textContent).toContain("13-15 años");
  });

  it("muestra el nivel de dificultad en español", () => {
    renderPage();
    // La sección tiene aria-label="Nivel de dificultad"; la etiqueta visible es "Dificultad"
    const difficultySection = screen.getByRole("region", {
      name: "Nivel de dificultad",
    });
    expect(difficultySection).toBeInTheDocument();
    expect(difficultySection.textContent).toContain("Media");
  });

  it("muestra los materiales reales como badges", () => {
    renderPage();
    const materialsSection = screen
      .getByText("Materiales")
      .closest("section");
    expect(materialsSection).not.toBeNull();
    expect(materialsSection?.textContent).toContain("Conos");
    expect(materialsSection?.textContent).toContain("Cinta delimitadora");
  });

  it("renderiza la sección 'Cómo realizarlo' con el how_to", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: "Cómo realizarlo" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Coloca los conos ficticios/),
    ).toBeInTheDocument();
  });

  it("no renderiza CircuitLayout para ejercicio no-gymkhana", () => {
    renderPage();
    // role="img" solo aparece cuando CircuitLayout está montado
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("no muestra el badge 'Juego' cuando is_game=false", () => {
    renderPage();
    expect(screen.queryByText("Juego")).not.toBeInTheDocument();
  });

  it("no muestra el badge 'Gymkhana' cuando is_gymkhana=false", () => {
    renderPage();
    expect(screen.queryByText("Gymkhana")).not.toBeInTheDocument();
  });

  it("tiene zero violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Tests — ejercicio sin material (FR-009)
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — ejercicio sin material", () => {
  it("muestra 'Sin material' cuando todos los materiales tienen is_none=true", () => {
    mockUseTechniqueExercise.mockReturnValue({
      data: EXERCISE_SIN_MATERIAL,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage(43);
    const materialsSection = screen
      .getByText("Materiales")
      .closest("section");
    expect(materialsSection).not.toBeNull();
    expect(materialsSection?.textContent).toContain("Sin material");
  });

  it("muestra 'Sin material' cuando la lista de materiales está vacía", () => {
    mockUseTechniqueExercise.mockReturnValue({
      data: { ...EXERCISE_FICTICIO, materials: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();
    const materialsSection = screen
      .getByText("Materiales")
      .closest("section");
    expect(materialsSection?.textContent).toContain("Sin material");
  });

  it("no tiene violaciones de accesibilidad para ejercicio sin material", async () => {
    mockUseTechniqueExercise.mockReturnValue({
      data: EXERCISE_SIN_MATERIAL,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    const { container } = renderPage(43);
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Tests — gymkhana con layout_ascii
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — gymkhana con circuito", () => {
  beforeEach(() => {
    mockUseTechniqueExercise.mockReturnValue({
      data: EXERCISE_GYMKHANA,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("monta CircuitLayout: el <pre> tiene role='img'", () => {
    renderPage(44);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("el aria-label del diagrama coincide con layout_alt", () => {
    renderPage(44);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Gymkhana ficticia: Salida, dos conos, llegada.",
    );
  });

  it("muestra el badge 'Gymkhana'", () => {
    renderPage(44);
    expect(screen.getByText("Gymkhana")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con CircuitLayout montado", async () => {
    const { container } = renderPage(44);
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Tests — badges condicionales
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — badges de tipo", () => {
  it("muestra badge 'Juego' cuando is_game=true", () => {
    mockUseTechniqueExercise.mockReturnValue({
      data: EXERCISE_JUEGO,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage(45);
    expect(screen.getByText("Juego")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — estado de error
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — estado de error", () => {
  it("muestra mensaje 404 sin botón reintentar para 'no encontrado'", () => {
    // Simula un error 404 de Axios
    const axiosError = Object.assign(new Error("Not Found"), {
      isAxiosError: true,
      response: { status: 404, data: { detail: "Not Found" } },
    });
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: axiosError,
      refetch: vi.fn(),
    });
    renderPage();
    expect(
      screen.getByText("No se encontró este ejercicio o fue eliminado."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Reintentar/i }),
    ).not.toBeInTheDocument();
  });

  it("muestra mensaje genérico con botón Reintentar para error 500", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    const serverError = Object.assign(new Error("Server Error"), {
      isAxiosError: true,
      response: { status: 500, data: { detail: "Server Error" } },
    });
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: serverError,
      refetch,
    });
    renderPage();
    const retryButton = screen.getByRole("button", { name: /Reintentar/i });
    expect(retryButton).toBeInTheDocument();
    await user.click(retryButton);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("el estado de error tiene role='alert'", () => {
    const err = Object.assign(new Error("err"), {
      isAxiosError: true,
      response: { status: 500 },
    });
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: err,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en estado de error", async () => {
    const err = Object.assign(new Error("err"), {
      isAxiosError: true,
      response: { status: 500 },
    });
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: err,
      refetch: vi.fn(),
    });
    const { container } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Tests — id inválido
// ---------------------------------------------------------------------------

describe("ExerciseDetailPage — id inválido", () => {
  beforeEach(() => {
    // El hook no debe llamarse cuando id es 0; lo configuramos con enabled=false
    mockUseTechniqueExercise.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("muestra mensaje de id no válido para ruta con texto no numérico", () => {
    renderPage("abc");
    expect(
      screen.getByText("El identificador del ejercicio no es válido."),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en estado de id inválido", async () => {
    const { container } = renderPage("abc");
    expect(await axe(container)).toHaveNoViolations();
  });
});
