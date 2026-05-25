/**
 * Tests de accesibilidad para los componentes del módulo Boletín mensual.
 * Cubre NewsletterNarrativeEditor y NewsletterPreviewBlocks contra jest-axe.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { NewsletterNarrativeEditor } from "./NewsletterNarrativeEditor";
import { NewsletterPreviewBlocks } from "./NewsletterPreviewBlocks";
import type { AiNarrative } from "@/types/athleteNewsletter.types";

expect.extend(toHaveNoViolations);

const sampleNarrative: AiNarrative = {
  strengths: "Buena cadencia y técnica en bajadas técnicas.",
  area_to_develop: "Mejorar transferencia de peso en curvas cerradas.",
  milestone: "Completó el circuito técnico sin pies al suelo.",
  model: "gemini-2.5-flash-lite",
  prompt_version: "v1",
  confidence: "medium",
};

describe("NewsletterNarrativeEditor — accesibilidad", () => {
  it("sin violaciones axe en modo edición", async () => {
    const { container } = render(
      <NewsletterNarrativeEditor
        aiNarrative={sampleNarrative}
        currentOverrides={null}
        disabled={false}
        isPending={false}
        onSave={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en modo solo lectura (approved/sent)", async () => {
    const { container } = render(
      <NewsletterNarrativeEditor
        aiNarrative={sampleNarrative}
        currentOverrides={null}
        disabled={true}
        isPending={false}
        onSave={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe con alerta de confianza baja", async () => {
    const { container } = render(
      <NewsletterNarrativeEditor
        aiNarrative={{ ...sampleNarrative, confidence: "low" }}
        currentOverrides={null}
        disabled={false}
        isPending={false}
        onSave={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("NewsletterPreviewBlocks — accesibilidad", () => {
  it("sin violaciones axe con bloques mínimos", async () => {
    const { container } = render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 92, count_present: 6, count_total: 7 },
        }}
        badges={null}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe con todos los bloques presentes", async () => {
    const { container } = render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 92, count_present: 6, count_total: 7, streak_sessions: 3 },
          technical_load: {
            avg_rpe: 5.2,
            hours_per_week: 4.5,
            rubric: { effort: 4, attitude: 5, technique: 4 },
            focus_areas: ["Frenado", "Cadencia"],
          },
          races: {
            results: [{ race_name: "Válida IV", position: 5, category: "JUV-M" }],
          },
          calendar: {
            upcoming: [{ name: "Cto. Departamental", date: "2026-06-26", phase: "A" }],
          },
          support_at_home: {
            hydration: "Asegurar 2 litros al día.",
            sleep: "Dormir 9 horas mínimo.",
          },
        }}
        badges={[
          { badge_type: "attendance_90", label: "Asistencia 90%" },
          { badge_type: "first_podium", label: "Primer podio" },
        ]}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe con estado vacío", async () => {
    const { container } = render(
      <NewsletterPreviewBlocks emailBlocks={null} badges={null} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
