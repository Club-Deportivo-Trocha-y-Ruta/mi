/**
 * Tests para CourseDescriptionCard (feature 043, User Story 3, T044).
 *
 * Cubre:
 *  - Estado vacío (0/4 campos): coach/admin ve "Describir la pista"; para
 *    el rol parent (`readOnly`) el componente no renderiza nada (ver
 *    `CourseDescriptionCard.tsx` — decisión explícita del sibling task: sin
 *    sentido mostrarle un CTA de edición que no puede usar).
 *  - Estado parcial (1-3/4 campos): botón "Completar".
 *  - Estado completo (4/4 campos): botón "Editar" + los 4 valores
 *    renderizados.
 *  - 0 violaciones jest-axe en los tres estados.
 *
 * El sheet de edición (`EditCourseDescriptionDialog`) se monta lazy y solo
 * cuando `editOpen` es true — ningún test de este archivo hace clic en los
 * botones de edición, así que no hace falta envolver con `QueryClientProvider`
 * ni mockear el sheet (se mantiene igual de simple que
 * `RaceConditionsCard.test.tsx`, su análogo directo).
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { CourseDescriptionCard } from "@/components/race/course/CourseDescriptionCard";
import type { CourseDescription } from "@/types/raceCourse.types";

const EMPTY: Partial<CourseDescription> = {
  terrain_type: null,
  technical_difficulty: null,
  key_sectors: [],
  course_notes: null,
};

const PARTIAL: Partial<CourseDescription> = {
  // 2 de 4 campos llenos: terrain_type + key_sectors no vacío.
  terrain_type: "mixto",
  technical_difficulty: null,
  key_sectors: ["rock_garden"],
  course_notes: null,
};

const COMPLETE: Partial<CourseDescription> = {
  terrain_type: "mixto",
  technical_difficulty: 4,
  key_sectors: ["subida_larga", "rock_garden"],
  course_notes: "Sube técnica al inicio.",
};

// ---------------------------------------------------------------------------
// Estado vacío
// ---------------------------------------------------------------------------

describe("CourseDescriptionCard — estado vacío", () => {
  it("coach/admin: muestra el CTA 'Describir la pista'", () => {
    render(<CourseDescriptionCard raceEventId={41} description={EMPTY} />);

    const card = screen.getByTestId("course-description-card-empty");
    expect(card).toBeInTheDocument();
    expect(
      within(card).getByText("Descripción del circuito no registrada"),
    ).toBeInTheDocument();
    const btn = within(card).getByTestId("course-description-describe-btn");
    expect(btn).toHaveTextContent("Describir la pista");
  });

  it("parent (readOnly): no renderiza nada en estado vacío", () => {
    const { container } = render(
      <CourseDescriptionCard raceEventId={41} description={EMPTY} readOnly />,
    );

    expect(
      screen.queryByTestId("course-description-card-empty"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Descripción del circuito no registrada"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("course-description-describe-btn"),
    ).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it("acepta `description` null/undefined sin romper (defensive default)", () => {
    render(<CourseDescriptionCard raceEventId={41} description={null} />);
    expect(
      screen.getByTestId("course-description-card-empty"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado parcial
// ---------------------------------------------------------------------------

describe("CourseDescriptionCard — estado parcial", () => {
  it("coach/admin: botón 'Completar' + valores llenos + placeholders para lo faltante", () => {
    render(<CourseDescriptionCard raceEventId={41} description={PARTIAL} />);

    const card = screen.getByTestId("course-description-card-partial");
    expect(card).toBeInTheDocument();

    const btn = within(card).getByTestId("course-description-edit-btn");
    expect(btn).toHaveTextContent("Completar");

    expect(within(card).getByText("Mixto")).toBeInTheDocument();
    expect(within(card).getByText("Rock garden")).toBeInTheDocument();

    // Dificultad y notas no registradas → placeholder visible para coach.
    const placeholders = within(card).getAllByText(/— sin registro —/);
    expect(placeholders.length).toBeGreaterThanOrEqual(2);
  });

  it("parent (readOnly): solo muestra los campos llenos, sin placeholders ni botón", () => {
    render(
      <CourseDescriptionCard
        raceEventId={41}
        description={PARTIAL}
        readOnly
      />,
    );

    const card = screen.getByTestId("course-description-card-partial");
    expect(within(card).getByText("Mixto")).toBeInTheDocument();
    expect(within(card).getByText("Rock garden")).toBeInTheDocument();
    expect(
      within(card).queryByText(/— sin registro —/),
    ).not.toBeInTheDocument();
    expect(
      within(card).queryByTestId("course-description-edit-btn"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado completo
// ---------------------------------------------------------------------------

describe("CourseDescriptionCard — estado completo", () => {
  it("coach/admin: botón 'Editar' + los 4 campos renderizados", () => {
    render(<CourseDescriptionCard raceEventId={41} description={COMPLETE} />);

    const card = screen.getByTestId("course-description-card-complete");
    expect(card).toBeInTheDocument();

    const btn = within(card).getByTestId("course-description-edit-btn");
    expect(btn).toHaveTextContent("Editar");

    expect(within(card).getByText("Mixto")).toBeInTheDocument();
    expect(within(card).getByText("4 — Técnico")).toBeInTheDocument();
    expect(
      within(card).getByText("Subida larga, Rock garden"),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Sube técnica al inicio."),
    ).toBeInTheDocument();

    // Estado completo no debe mostrar placeholders de "sin registro".
    expect(
      within(card).queryByText(/— sin registro —/),
    ).not.toBeInTheDocument();
  });

  it("parent (readOnly): ve los 4 valores pero no el botón de edición", () => {
    render(
      <CourseDescriptionCard
        raceEventId={41}
        description={COMPLETE}
        readOnly
      />,
    );

    const card = screen.getByTestId("course-description-card-complete");
    expect(within(card).getByText("Mixto")).toBeInTheDocument();
    expect(within(card).getByText("4 — Técnico")).toBeInTheDocument();
    expect(
      within(card).getByText("Subida larga, Rock garden"),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Sube técnica al inicio."),
    ).toBeInTheDocument();
    expect(
      within(card).queryByTestId("course-description-edit-btn"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("CourseDescriptionCard — accesibilidad", () => {
  it("estado vacío: 0 violaciones jest-axe", async () => {
    const { container } = render(
      <CourseDescriptionCard raceEventId={41} description={EMPTY} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("estado parcial: 0 violaciones jest-axe", async () => {
    const { container } = render(
      <CourseDescriptionCard raceEventId={41} description={PARTIAL} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("estado completo: 0 violaciones jest-axe", async () => {
    const { container } = render(
      <CourseDescriptionCard raceEventId={41} description={COMPLETE} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
