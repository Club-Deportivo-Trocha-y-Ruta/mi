/**
 * Tests — FamilyStageCard (feature 040, US4, T058).
 *
 * Contrato: `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`
 * (mockup §5.2 de `docs/18-growth-module-redesign/proposal.md`) — una frase
 * de etapa en lenguaje familiar (copia exacta de `phvParentMessage`,
 * `routes/parents/MyAthleteDetailPage.tsx:98`) más la fecha de evaluación
 * ofuscada a "mes año" (Ley 1581 — nunca el día exacto).
 *
 * Datos: sintéticos, sin nombre ni fecha de nacimiento reales de un menor.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { FamilyStageCard } from "@/components/athletes/growth/FamilyStageCard";
import { MaturationStatus, Sex } from "@/types/enums";

describe("FamilyStageCard", () => {
  it("expone data-testid=family-stage-card en la raíz", () => {
    render(
      <FamilyStageCard
        stage={MaturationStatus.PostPHV}
        latestEvaluationDate="2026-08-14"
        sex={Sex.M}
      />,
    );
    expect(screen.getByTestId("family-stage-card")).toBeInTheDocument();
  });

  it("muestra el título fijo del contrato 'Etapa de desarrollo'", () => {
    render(
      <FamilyStageCard
        stage={MaturationStatus.PostPHV}
        latestEvaluationDate="2026-08-14"
        sex={Sex.M}
      />,
    );
    expect(screen.getByText("Etapa de desarrollo")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Frase por etapa — copia exacta de `phvParentMessage`, con el pronombre
  // correcto según el sexo del atleta.
  // -------------------------------------------------------------------------

  it("Pre-PHV + hijo: 'Tu hijo está en etapa de desarrollo temprano'", () => {
    render(
      <FamilyStageCard stage={MaturationStatus.PrePHV} latestEvaluationDate={null} sex={Sex.M} />,
    );
    expect(
      screen.getByText("Tu hijo está en etapa de desarrollo temprano"),
    ).toBeInTheDocument();
  });

  it("Circa-PHV + hija: 'Tu hija está en su pico de crecimiento — etapa clave'", () => {
    render(
      <FamilyStageCard stage={MaturationStatus.CircaPHV} latestEvaluationDate={null} sex={Sex.F} />,
    );
    expect(
      screen.getByText("Tu hija está en su pico de crecimiento — etapa clave"),
    ).toBeInTheDocument();
  });

  it("Post-PHV + hijo: 'El crecimiento de tu hijo se está estabilizando'", () => {
    render(
      <FamilyStageCard stage={MaturationStatus.PostPHV} latestEvaluationDate={null} sex={Sex.M} />,
    );
    expect(
      screen.getByText("El crecimiento de tu hijo se está estabilizando"),
    ).toBeInTheDocument();
  });

  it("Post-PHV + hija: usa 'hija', no 'hijo'", () => {
    render(
      <FamilyStageCard stage={MaturationStatus.PostPHV} latestEvaluationDate={null} sex={Sex.F} />,
    );
    expect(
      screen.getByText("El crecimiento de tu hija se está estabilizando"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/tu hijo/i)).not.toBeInTheDocument();
  });

  it("stage=null (sin mediciones) no renderiza nada", () => {
    const { container } = render(
      <FamilyStageCard stage={null} latestEvaluationDate={null} sex={Sex.M} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  // -------------------------------------------------------------------------
  // Privacidad — la fecha se ofusca a "mes año", nunca el día exacto.
  // -------------------------------------------------------------------------

  it("ofusca la fecha de evaluación a 'mes año' (ej. 'ago 2026'), nunca el día exacto", () => {
    render(
      <FamilyStageCard
        stage={MaturationStatus.PostPHV}
        latestEvaluationDate="2026-08-14"
        sex={Sex.M}
      />,
    );
    expect(screen.getByText("Evaluado en ago 2026")).toBeInTheDocument();
    expect(screen.queryByText(/14/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026-08-14/)).not.toBeInTheDocument();
  });

  it("sin fecha de evaluación no muestra la línea 'Evaluado en'", () => {
    render(
      <FamilyStageCard stage={MaturationStatus.PostPHV} latestEvaluationDate={null} sex={Sex.M} />,
    );
    expect(screen.queryByText(/Evaluado en/)).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(
      <FamilyStageCard
        stage={MaturationStatus.CircaPHV}
        latestEvaluationDate="2026-08-14"
        sex={Sex.F}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
