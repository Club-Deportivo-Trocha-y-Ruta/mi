/**
 * Tests para SeasonCompletionChips (feature 044, US6 — T076).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SeasonCompletionChips } from "@/components/race/history/SeasonCompletionChips";

describe("SeasonCompletionChips", () => {
  it("renderiza una chip 'temporada · terminadas de arrancadas' por temporada, en orden ascendente", () => {
    render(
      <SeasonCompletionChips
        seasons={[
          { season: 2025, started: 7, finished: 6 },
          { season: 2024, started: 5, finished: 5 },
        ]}
      />,
    );
    const list = screen.getByTestId("season-completion-chips");
    const items = list.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("2024 · 5 de 5");
    expect(items[1]).toHaveTextContent("2025 · 6 de 7");
  });

  it("no renderiza nada sin temporadas", () => {
    const { container } = render(<SeasonCompletionChips seasons={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
