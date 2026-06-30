/**
 * Tests de integración para CircuitLayout (T014 — feature 019 Phase A, US1).
 *
 * Foco: comportamiento de selección de renderer (FR-010):
 *   layout_json ausente + layout_ascii presente → fallback <pre> legacy (sin error).
 *   layout_json presente                        → <CircuitDiagram> SVG (BLOCKED on T017).
 *   Ambos ausentes                              → null (paridad con feature 018).
 *
 * Los tests del fallback ASCII (layout_json=null) pasan CON la implementación
 * actual de CircuitLayout porque es el comportamiento feature-018 intacto.
 *
 * Los tests que asumen layout_json presente → SVG estarán BLOQUEADOS hasta que
 * T017 actualice CircuitLayout.tsx para elegir <CircuitDiagram> en ese caso.
 *
 * Tests de accesibilidad y paridad de la <pre> legacy están en
 * __tests__/CircuitLayout.test.tsx (feature 018); aquí solo se cubre la lógica
 * de selección de renderer introducida por feature 019.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CircuitLayout } from "./CircuitLayout";
import type { ExerciseDetail, GymkhanaLayout } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios (no PII de menores reales)
// ---------------------------------------------------------------------------

const FICTITIOUS_LAYOUT_JSON: GymkhanaLayout = {
  width: 100,
  height: 80,
  elements: [
    { kind: "cone",  x: 10, y: 10 },
    { kind: "gate",  x: 50, y: 40 },
    { kind: "arrow", x: 80, y: 70, rotation: 90 },
  ],
};

const BASE_GYMKHANA: ExerciseDetail = {
  id: 42,
  slug: "gymkhana-ficticia-t014",
  name: "Gymkhana Ficticia T014",
  summary: "Datos ficticios para tests de selección de renderer.",
  difficulty: "media",
  is_game: false,
  is_gymkhana: true,
  age_bands: ["10-12"],
  skills: [{ code: "EQ", slug: "equilibrio", name: "Equilibrio" }],
  materials: [{ slug: "conos", name: "Conos", is_none: false }],
  is_seeded: true,
  is_hidden: false,
  how_to: "Instrucciones ficticias para el ejercicio de prueba.",
  layout_ascii: "S --> [ ] --> ( ) --> F",
  layout_alt: "Circuito ficticio: salida, obstáculo, llegada.",
  layout_json: null,
  confidence: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function exercise(overrides?: Partial<ExerciseDetail>): ExerciseDetail {
  return { ...BASE_GYMKHANA, ...overrides };
}

// ---------------------------------------------------------------------------
// Grupo 1 — fallback ASCII (layout_json = null, layout_ascii presente)
// Estos tests pasan con la implementación actual de CircuitLayout (feature 018).
// ---------------------------------------------------------------------------

describe("CircuitLayout — fallback ASCII cuando layout_json es null", () => {
  it("renderiza el <pre> legacy cuando layout_json es null y layout_ascii existe", () => {
    render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: "S --> [ ] --> F" })}
      />,
    );
    // The ASCII block is exposed as role="img" on the <pre> per feature 018 contract
    const pre = screen.getByRole("img");
    expect(pre.tagName).toBe("PRE");
  });

  it("el <pre> contiene el texto ASCII del croquis original", () => {
    const ASCII = "S --> [ ] --> ( ) --> F";
    render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: ASCII })}
      />,
    );
    const pre = screen.getByRole("img");
    expect(pre.textContent).toContain(ASCII);
  });

  it("no renderiza un <svg> cuando layout_json es null (sin CircuitDiagram)", () => {
    const { container } = render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: "S --> F" })}
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("no arroja error durante el render del fallback ASCII", () => {
    expect(() =>
      render(
        <CircuitLayout
          exercise={exercise({ layout_json: null, layout_ascii: "S --> F" })}
        />,
      ),
    ).not.toThrow();
  });

  it("muestra la leyenda aunque layout_json sea null", () => {
    render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: "S --> F" })}
      />,
    );
    expect(screen.getByText("Leyenda del circuito")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Grupo 2 — ambos ausentes → null (paridad feature 018)
// ---------------------------------------------------------------------------

describe("CircuitLayout — retorna null cuando no hay layout disponible", () => {
  it("retorna null cuando layout_json y layout_ascii son null", () => {
    const { container } = render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: null })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("retorna null cuando is_gymkhana es false aunque layout_ascii exista", () => {
    const { container } = render(
      <CircuitLayout
        exercise={exercise({
          is_gymkhana: false,
          layout_json: null,
          layout_ascii: "S --> F",
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("retorna null cuando layout_ascii es solo espacios y layout_json es null", () => {
    const { container } = render(
      <CircuitLayout
        exercise={exercise({ layout_json: null, layout_ascii: "   " })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

// ---------------------------------------------------------------------------
// Grupo 3 — layout_json presente → <CircuitDiagram> SVG (BLOCKED ON T017)
//
// These tests will FAIL until CircuitLayout.tsx is updated (T017) to
// prefer <CircuitDiagram> when layout_json is non-null.
// ---------------------------------------------------------------------------

describe("CircuitLayout — CircuitDiagram SVG cuando layout_json está presente (BLOCKED T017)", () => {
  it("renderiza un <svg> (no un <pre>) cuando layout_json está presente", () => {
    const { container } = render(
      <CircuitLayout
        exercise={exercise({
          layout_json: FICTITIOUS_LAYOUT_JSON,
          layout_ascii: "S --> [ ] --> F", // also present — should be bypassed
        })}
      />,
    );
    // After T017: <svg> should be present
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("NO renderiza la <pre> legacy cuando layout_json está presente", () => {
    render(
      <CircuitLayout
        exercise={exercise({
          layout_json: FICTITIOUS_LAYOUT_JSON,
          layout_ascii: "S --> [ ] --> F",
        })}
      />,
    );
    // The <pre role="img"> must be absent when the SVG renderer is active
    const preEls = document.querySelectorAll("pre[role='img']");
    expect(preEls).toHaveLength(0);
  });

  it("no arroja error cuando layout_json está presente y layout_ascii es null", () => {
    expect(() =>
      render(
        <CircuitLayout
          exercise={exercise({
            layout_json: FICTITIOUS_LAYOUT_JSON,
            layout_ascii: null,
          })}
        />,
      ),
    ).not.toThrow();
  });

  it("retorna null cuando is_gymkhana=false aunque layout_json esté presente", () => {
    // RBAC note: non-gymkhana exercises never show a circuit diagram regardless.
    const { container } = render(
      <CircuitLayout
        exercise={exercise({
          is_gymkhana: false,
          layout_json: FICTITIOUS_LAYOUT_JSON,
          layout_ascii: null,
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
