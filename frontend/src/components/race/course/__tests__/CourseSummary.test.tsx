/**
 * Tests para CourseSummary (feature 043 — perfil de circuito, T054/US5).
 *
 * `CourseSummary` es la tarjeta de reconocimiento de pista, de solo lectura,
 * compartida por la pestaña Circuito del coach Y ambas páginas de padres
 * (`ParentCompetitionResultsPage`, `ParentEventDetailPage` — ver sus propios
 * `.test.tsx`, extendidos en este mismo feature). Este archivo cubre
 * exclusivamente la lógica de composición del propio componente — el mapa y
 * el perfil de elevación (`CourseMap`/`ElevationProfile`) ya están cubiertos
 * en sus propios archivos de test, así que aquí se mockean como stand-ins
 * triviales (mismo criterio que `EvolutionChart.test.tsx` mockea
 * "recharts": no repetir cobertura de internals ya probados en otro lado).
 *
 * Contrato fijado por este archivo (no hay implementación todavía — TDD-red):
 *   - `hasCourseData=false` → no renderiza nada (`null`).
 *   - Raíz: `data-testid="course-summary"`.
 *   - Por variante: `data-testid="course-summary-figures-{variantId}"` con
 *     distancia (km), desnivel (m, o "sin dato" en minúscula — solo cuando
 *     `has_elevation=true`; se omite el desnivel por completo si es `false`,
 *     porque `VariantBlock` ya muestra "Sin altimetría en la grabación") y
 *     vueltas (si algún setup referencia esa variante — se omite la palabra
 *     "vueltas" si ninguno lo hace).
 *   - `has_elevation=false` → texto fijo "Sin altimetría en la grabación" en
 *     vez de `ElevationProfile`; `CourseMap` se sigue mostrando siempre.
 *   - Tabla de vueltas por categoría: `data-testid="course-summary-setup-row-{categoryId}"`,
 *     con `data-highlighted="true"` cuando `category_id` está en
 *     `myCategories`; "Tu hijo/a: {nombre}" cuando `athleteNamesById`
 *     resuelve el atleta, "Categoría de tu atleta" en cualquier otro caso
 *     (prop ausente o sin esa entrada) — nunca crashea ni imprime
 *     "undefined".
 *   - Descripción: `data-testid="course-summary-description"` con
 *     sub-testids `-terrain` / `-difficulty` / `-sectors` / `-notes`, cada
 *     uno presente SOLO si el campo correspondiente no es null/vacío (sin
 *     placeholder "sin dato"/"— sin registro —", a diferencia de
 *     `CourseDescriptionCard`).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

vi.mock("@/components/race/course/CourseMap", () => ({
  CourseMap: ({ label }: { label: string }) => (
    <div data-testid="mock-course-map" data-label={label} />
  ),
}));

vi.mock("@/components/race/course/ElevationProfile", () => ({
  ElevationProfile: ({ elevationGainM }: { elevationGainM: number }) => (
    <div data-testid="mock-elevation-profile" data-gain={elevationGainM} />
  ),
}));

import { CourseSummary } from "@/components/race/course/CourseSummary";
import {
  makeCourseSetup,
  makeCourseVariant,
} from "@/test/msw/raceCourseHandlers";
import type { CourseDescription, MyCategory } from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VARIANT_WITH_ELEVATION = makeCourseVariant({
  id: 7,
  label: "Circuito completo",
  lap_distance_km: 4.2,
  elevation_gain_m: 110,
  has_elevation: true,
});

const VARIANT_NO_ELEVATION = makeCourseVariant({
  id: 8,
  label: "Recorrido reducido",
  lap_distance_km: 2.5,
  elevation_gain_m: null,
  has_elevation: false,
});

const SETUP_HIGHLIGHTED = makeCourseSetup({
  category_id: 12,
  category_code: "INF_M",
  category_label: "Infantil masculino",
  laps: 3,
  variant_id: 7,
});

const SETUP_OTHER = makeCourseSetup({
  category_id: 13,
  category_code: "INF_F",
  category_label: "Infantil femenino",
  laps: 2,
  variant_id: 8,
});

const FULL_DESCRIPTION: CourseDescription = {
  terrain_type: "mixto",
  technical_difficulty: 4,
  key_sectors: ["subida_larga", "rock_garden"],
  course_notes: "Buen agarre en curvas de tierra",
};

const EMPTY_DESCRIPTION: CourseDescription = {
  terrain_type: null,
  technical_difficulty: null,
  key_sectors: [],
  course_notes: null,
};

const MY_CATEGORIES: MyCategory[] = [{ athlete_id: 305, category_id: 12 }];

// ---------------------------------------------------------------------------
// hasCourseData=false
// ---------------------------------------------------------------------------

describe("CourseSummary — hasCourseData=false", () => {
  it("no renderiza nada (returns null) — nunca un CTA de estado vacío (eso es de VariantsCard/CourseDescriptionCard)", () => {
    const { container } = render(
      <CourseSummary
        hasCourseData={false}
        variants={[]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("course-summary")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Figuras por variante
// ---------------------------------------------------------------------------

describe("CourseSummary — figuras por variante", () => {
  it("muestra distancia, desnivel y vueltas (derivadas del setup que referencia la variante)", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION]}
        setups={[SETUP_HIGHLIGHTED]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    const figures = await screen.findByTestId(
      `course-summary-figures-${VARIANT_WITH_ELEVATION.id}`,
    );
    expect(figures).toHaveTextContent("4.2 km");
    expect(figures).toHaveTextContent("110");
    expect(figures).toHaveTextContent(/desnivel/i);
    expect(figures).toHaveTextContent("3");
    expect(figures).toHaveTextContent(/vueltas/i);
  });

  it("omite el desnivel por completo cuando has_elevation=false (ya lo cubre 'Sin altimetría en la grabación'), y omite 'vueltas' si ningún setup referencia la variante", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_NO_ELEVATION]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    const figures = await screen.findByTestId(
      `course-summary-figures-${VARIANT_NO_ELEVATION.id}`,
    );
    expect(figures).toHaveTextContent("2.5 km");
    expect(figures).not.toHaveTextContent(/desnivel/i);
    expect(figures).not.toHaveTextContent(/vueltas/i);
  });
});

// ---------------------------------------------------------------------------
// mapOnly (pestaña del coach)
// ---------------------------------------------------------------------------

describe("CourseSummary — mapOnly", () => {
  it("solo muestra mapa + perfil de la primera variante: sin cifras, vueltas ni descripción", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION, VARIANT_NO_ELEVATION]}
        setups={[SETUP_HIGHLIGHTED, SETUP_OTHER]}
        description={FULL_DESCRIPTION}
        myCategories={[]}
        mapOnly
      />,
    );
    expect(await screen.findByTestId("mock-course-map")).toBeInTheDocument();
    expect(await screen.findByTestId("mock-elevation-profile")).toBeInTheDocument();
    expect(
      screen.queryByTestId(`course-summary-variant-${VARIANT_NO_ELEVATION.id}`),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId(/^course-summary-figures-/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("course-summary-setups")).not.toBeInTheDocument();
    expect(screen.queryByTestId("course-summary-description")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Mapa + perfil de elevación
// ---------------------------------------------------------------------------

describe("CourseSummary — mapa + perfil de elevación", () => {
  it("has_elevation=true: renderiza CourseMap y ElevationProfile (lazy) para esa variante", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    const map = await screen.findByTestId("mock-course-map");
    expect(map).toHaveAttribute("data-label", "Circuito completo");
    const profile = await screen.findByTestId("mock-elevation-profile");
    expect(profile).toHaveAttribute("data-gain", "110");
    expect(
      screen.queryByText("Sin altimetría en la grabación"),
    ).not.toBeInTheDocument();
  });

  it("has_elevation=false: muestra 'Sin altimetría en la grabación' en vez de ElevationProfile, pero sigue mostrando CourseMap", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_NO_ELEVATION]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    await screen.findByTestId("mock-course-map");
    expect(
      screen.getByText("Sin altimetría en la grabación"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("mock-elevation-profile"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Vueltas por categoría — tabla presentacional (NO CategorySetupTable)
// ---------------------------------------------------------------------------

describe("CourseSummary — vueltas por categoría", () => {
  function renderTwoVariantsAndSetups(overrides?: {
    athleteNamesById?: Record<number, string>;
    myCategories?: MyCategory[];
  }) {
    return render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION, VARIANT_NO_ELEVATION]}
        setups={[SETUP_HIGHLIGHTED, SETUP_OTHER]}
        description={EMPTY_DESCRIPTION}
        myCategories={overrides?.myCategories ?? []}
        athleteNamesById={overrides?.athleteNamesById}
      />,
    );
  }

  it("cada fila muestra la categoría, las vueltas y la etiqueta de la variante resuelta por variant_id", async () => {
    renderTwoVariantsAndSetups();
    const rowA = await screen.findByTestId(
      `course-summary-setup-row-${SETUP_HIGHLIGHTED.category_id}`,
    );
    expect(rowA).toHaveTextContent("Infantil masculino");
    expect(rowA).toHaveTextContent("3");
    expect(rowA).toHaveTextContent("Circuito completo");

    const rowB = screen.getByTestId(
      `course-summary-setup-row-${SETUP_OTHER.category_id}`,
    );
    expect(rowB).toHaveTextContent("Infantil femenino");
    expect(rowB).toHaveTextContent("2");
    expect(rowB).toHaveTextContent("Recorrido reducido");
  });

  it("resalta la fila cuya category_id está en myCategories y muestra 'Tu hijo/a: {nombre}' cuando athleteNamesById lo resuelve", async () => {
    renderTwoVariantsAndSetups({
      myCategories: MY_CATEGORIES,
      athleteNamesById: { 305: "Ana" },
    });
    const highlighted = await screen.findByTestId(
      `course-summary-setup-row-${SETUP_HIGHLIGHTED.category_id}`,
    );
    expect(highlighted).toHaveAttribute("data-highlighted", "true");
    expect(highlighted).toHaveTextContent("Tu hijo/a: Ana");

    const other = screen.getByTestId(
      `course-summary-setup-row-${SETUP_OTHER.category_id}`,
    );
    expect(other.getAttribute("data-highlighted")).not.toBe("true");
    expect(other).not.toHaveTextContent("Tu hijo/a");
  });

  it("sin athleteNamesById: la fila resaltada usa el rótulo neutral 'Categoría de tu atleta' — nunca crashea ni muestra 'undefined'", async () => {
    renderTwoVariantsAndSetups({ myCategories: MY_CATEGORIES });
    const highlighted = await screen.findByTestId(
      `course-summary-setup-row-${SETUP_HIGHLIGHTED.category_id}`,
    );
    expect(highlighted).toHaveAttribute("data-highlighted", "true");
    expect(highlighted).toHaveTextContent("Categoría de tu atleta");
    expect(highlighted.textContent ?? "").not.toMatch(/undefined/i);
  });

  it("athleteNamesById presente pero sin la entrada del atleta resaltado: mismo rótulo neutral, sin crashear", async () => {
    renderTwoVariantsAndSetups({
      myCategories: MY_CATEGORIES,
      athleteNamesById: { 999: "Otro Nombre" },
    });
    const highlighted = await screen.findByTestId(
      `course-summary-setup-row-${SETUP_HIGHLIGHTED.category_id}`,
    );
    expect(highlighted).toHaveTextContent("Categoría de tu atleta");
    expect(highlighted.textContent ?? "").not.toMatch(/undefined/i);
  });

  it("sin myCategories (coach/admin, siempre []): ninguna fila se resalta", async () => {
    renderTwoVariantsAndSetups({ myCategories: [] });
    const rowA = await screen.findByTestId(
      `course-summary-setup-row-${SETUP_HIGHLIGHTED.category_id}`,
    );
    const rowB = screen.getByTestId(
      `course-summary-setup-row-${SETUP_OTHER.category_id}`,
    );
    expect(rowA.getAttribute("data-highlighted")).not.toBe("true");
    expect(rowB.getAttribute("data-highlighted")).not.toBe("true");
  });
});

// ---------------------------------------------------------------------------
// Descripción del circuito — recap de solo lectura (sin placeholders)
// ---------------------------------------------------------------------------

describe("CourseSummary — descripción del circuito", () => {
  it("con los 4 campos llenos, muestra los 4 usando las etiquetas ya establecidas (TERRAIN_TYPE_LABELS/KEY_SECTOR_LABELS)", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION]}
        setups={[]}
        description={FULL_DESCRIPTION}
        myCategories={[]}
      />,
    );
    const description = await screen.findByTestId(
      "course-summary-description",
    );
    expect(
      within(description).getByTestId("course-summary-description-terrain"),
    ).toHaveTextContent("Mixto");
    expect(
      within(description).getByTestId(
        "course-summary-description-difficulty",
      ),
    ).toHaveTextContent("4 — Técnico");
    const sectors = within(description).getByTestId(
      "course-summary-description-sectors",
    );
    expect(sectors).toHaveTextContent("Subida larga");
    expect(sectors).toHaveTextContent("Rock garden");
    expect(
      within(description).getByTestId("course-summary-description-notes"),
    ).toHaveTextContent("Buen agarre en curvas de tierra");
  });

  it("campos null/vacíos se omiten por completo — sin placeholder 'sin dato'/'— sin registro —' (a diferencia de CourseDescriptionCard)", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    await screen.findByTestId("course-summary");
    expect(
      screen.queryByTestId("course-summary-description-terrain"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("course-summary-description-difficulty"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("course-summary-description-sectors"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("course-summary-description-notes"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/— sin registro —/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^sin dato$/i)).not.toBeInTheDocument();
  });

  it("descripción parcial (solo terreno) muestra únicamente ese campo", async () => {
    render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION]}
        setups={[]}
        description={{ ...EMPTY_DESCRIPTION, terrain_type: "trocha" }}
        myCategories={[]}
      />,
    );
    const description = await screen.findByTestId(
      "course-summary-description",
    );
    expect(
      within(description).getByTestId("course-summary-description-terrain"),
    ).toHaveTextContent("Trocha");
    expect(
      within(description).queryByTestId(
        "course-summary-description-difficulty",
      ),
    ).not.toBeInTheDocument();
    expect(
      within(description).queryByTestId("course-summary-description-sectors"),
    ).not.toBeInTheDocument();
    expect(
      within(description).queryByTestId("course-summary-description-notes"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("CourseSummary — accesibilidad", () => {
  it("0 violaciones jest-axe en estado 'datos completos'", async () => {
    const { container } = render(
      <CourseSummary
        hasCourseData
        variants={[VARIANT_WITH_ELEVATION, VARIANT_NO_ELEVATION]}
        setups={[SETUP_HIGHLIGHTED, SETUP_OTHER]}
        description={FULL_DESCRIPTION}
        myCategories={MY_CATEGORIES}
        athleteNamesById={{ 305: "Ana" }}
      />,
    );
    await screen.findByTestId("mock-course-map");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe cuando hasCourseData=false (render nulo, trivialmente sin violaciones)", async () => {
    const { container } = render(
      <CourseSummary
        hasCourseData={false}
        variants={[]}
        setups={[]}
        description={EMPTY_DESCRIPTION}
        myCategories={[]}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
