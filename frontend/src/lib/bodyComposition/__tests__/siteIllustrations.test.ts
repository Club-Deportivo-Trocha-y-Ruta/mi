/**
 * Tests — siteIllustrations (feature 046).
 *
 * `getSiteIllustration` resuelve un import estático por sitio (Vite falla
 * el build si algún `.webp` falta, así que aquí sólo se comprueba la forma
 * del resultado, no la ausencia de archivo).
 */
import { describe, expect, it } from "vitest";

import { SKINFOLD_SITE_ORDER } from "@/lib/bodyComposition/siteDiagrams";
import { SITE_ILLUSTRATION_SIZE, getSiteIllustration } from "@/lib/bodyComposition/siteIllustrations";

describe("getSiteIllustration", () => {
  it("devuelve una URL no vacía para cada sitio", () => {
    for (const site of SKINFOLD_SITE_ORDER) {
      const url = getSiteIllustration(site);
      expect(typeof url).toBe("string");
      expect(url.length).toBeGreaterThan(0);
    }
  });

  it("las ilustraciones son cuadradas de 768 px", () => {
    expect(SITE_ILLUSTRATION_SIZE).toBe(768);
  });
});
