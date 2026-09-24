/**
 * Tests — SkinfoldSiteDiagram (feature 046).
 *
 * Un solo camino, determinista (el módulo de ilustraciones se simula, así
 * no depende de que los `.webp` existan en el repo): `<img>` con el `alt`
 * de `siteDiagrams.ts` + insignia "D" superpuesta como HTML accesible.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { SkinfoldSiteDiagram } from "@/components/athletes/body-composition/SkinfoldSiteDiagram";
import { SKINFOLD_SITE_ORDER, getSkinfoldSiteDiagram } from "@/lib/bodyComposition/siteDiagrams";
import { SITE_ILLUSTRATION_SIZE, getSiteIllustration } from "@/lib/bodyComposition/siteIllustrations";

vi.mock("@/lib/bodyComposition/siteIllustrations", () => ({
  SITE_ILLUSTRATION_SIZE: 768,
  getSiteIllustration: vi.fn(),
}));

const mockIllustration = vi.mocked(getSiteIllustration);

describe("SkinfoldSiteDiagram", () => {
  beforeEach(() => {
    mockIllustration.mockImplementation((site) => `/assets/${site}.webp`);
  });

  it.each(SKINFOLD_SITE_ORDER)("renderiza la imagen de %s con el alt de siteDiagrams", (site) => {
    render(<SkinfoldSiteDiagram site={site} />);
    const img = screen.getByRole("img", { name: getSkinfoldSiteDiagram(site).alt });
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", `/assets/${site}.webp`);
  });

  it("reserva el espacio (width/height explícitos) y carga sin retraso", () => {
    render(<SkinfoldSiteDiagram site="triceps" />);
    const img = screen.getByRole("img", { name: getSkinfoldSiteDiagram("triceps").alt });
    expect(img).toHaveAttribute("width", String(SITE_ILLUSTRATION_SIZE));
    expect(img).toHaveAttribute("height", String(SITE_ILLUSTRATION_SIZE));
    expect(img).toHaveAttribute("loading", "eager");
    expect(img).toHaveAttribute("decoding", "async");
  });

  it("superpone la insignia 'D' con el texto accesible 'Lado derecho'", () => {
    render(<SkinfoldSiteDiagram site="biceps" />);
    expect(screen.getByRole("img", { name: "Lado derecho" })).toHaveTextContent("D");
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(<SkinfoldSiteDiagram site="supraspinale" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
