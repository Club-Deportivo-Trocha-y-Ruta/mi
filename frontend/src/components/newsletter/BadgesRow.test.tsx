/**
 * BadgesRow.test.tsx — feature 038, T301.
 *
 * Cubre: las insignias muestran siempre `label` (legible en español) y
 * nunca `code` (clave interna cruda) como texto visible.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { buildStageLogFullMonth } from "@/test/fixtures/stageLog";
import { BadgesRow } from "./BadgesRow";

describe("BadgesRow", () => {
  it("no renderiza nada con una lista vacía", () => {
    const { container } = render(<BadgesRow badges={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("muestra el label legible de cada insignia y nunca su code", () => {
    const { badges } = buildStageLogFullMonth();
    render(<BadgesRow badges={badges} />);

    const chips = screen.getAllByTestId("badge-chip");
    expect(chips).toHaveLength(badges.length);

    badges.forEach((badge, idx) => {
      expect(chips[idx]).toHaveTextContent(badge.label);
      // El code (p. ej. "attendance_90", "streak_10") nunca debe aparecer
      // como texto visible — solo el label ya traducido.
      expect(chips[idx].textContent).not.toContain(badge.code);
    });
  });

  it("snapshot: labels legibles, nunca códigos crudos", () => {
    const badges = [
      { code: "attendance_100", label: "Asistencia 100 %", icon: "award", earned_at: "2026-06-01" },
      { code: "top10", label: "Top 10", icon: "star", earned_at: "2026-06-14" },
      { code: "mtp", label: "Mejor tiempo personal", icon: "flame", earned_at: "2026-06-14" },
      { code: "first_podium", label: "Primer podio", icon: "award", earned_at: "2026-06-14" },
    ];
    render(<BadgesRow badges={badges} />);

    for (const badge of badges) {
      expect(screen.getByText(badge.label)).toBeInTheDocument();
    }
    // Ninguno de los codes crudos aparece como texto en el DOM.
    const container = screen.getByTestId("badges-row");
    for (const badge of badges) {
      expect(container.textContent).not.toContain(badge.code);
    }
  });
});
