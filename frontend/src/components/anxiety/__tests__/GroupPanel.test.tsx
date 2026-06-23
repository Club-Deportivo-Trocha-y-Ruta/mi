/**
 * Tests para GroupPanel (US5): cuatro buckets de triage + alertas + a11y.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { GroupPanel } from "../GroupPanel";
import type { GroupTriage } from "@/types/anxiety.types";

expect.extend(toHaveNoViolations);

const TRIAGE: GroupTriage = {
  event_id: 1,
  buckets: {
    somatic_high: [
      { athlete_id: 10, assessment_id: 100, cognitive: 20, somatic: 35, selfconfidence: 30, flags: [] },
    ],
    cognitive_high: [],
    confidence_low: [
      { athlete_id: 11, assessment_id: 101, cognitive: 35, somatic: 30, selfconfidence: 12, flags: ["Atención: conversación individual."] },
    ],
    favorable: [
      { athlete_id: 12, assessment_id: 102, cognitive: 15, somatic: 15, selfconfidence: 35, flags: [] },
    ],
  },
  alerts: [
    { athlete_id: 11, assessment_id: 101, cognitive: 35, somatic: 30, selfconfidence: 12, flags: ["Atención: conversación individual."] },
  ],
};

describe("GroupPanel", () => {
  it("renderiza los cuatro buckets con sus conteos", () => {
    render(<GroupPanel triage={TRIAGE} />);
    expect(screen.getByText(/Activación somática alta \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Preocupación cognitiva alta \(0\)/)).toBeInTheDocument();
    expect(screen.getByText(/Confianza baja \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Perfil favorable \(1\)/)).toBeInTheDocument();
  });

  it("muestra la sección de alertas", () => {
    render(<GroupPanel triage={TRIAGE} />);
    expect(screen.getByText(/Alertas \(1\)/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<GroupPanel triage={TRIAGE} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
