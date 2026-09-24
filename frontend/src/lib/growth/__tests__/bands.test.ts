/**
 * Tests del vocabulario de composición corporal por pliegues (feature 046)
 * añadido a `lib/growth/bands.ts`. Los tests del vocabulario nutricional
 * (`NutritionalStatus`) preexistente viven en `lib/growth/bands.test.ts`
 * (sibling, sin `__tests__`); este archivo es nuevo (T016) y sólo cubre las
 * adiciones de composición corporal, para no chocar con ese archivo mientras
 * otro agente lo edita en paralelo.
 */
import { describe, it, expect } from "vitest";

import {
  BODY_COMPOSITION_BAND_TONE,
  BODY_COMPOSITION_FAMILY_VOCABULARY,
  getBodyCompositionBandTone,
  getBodyCompositionFamilyVocabulary,
  type BodyCompositionCoachBand,
} from "@/lib/growth/bands";

describe("getBodyCompositionBandTone", () => {
  it.each([
    ["verde", "success"],
    ["ambar", "warning"],
    ["rojo", "danger"],
  ] as [BodyCompositionCoachBand, string][])("%s -> %s", (band, tone) => {
    expect(getBodyCompositionBandTone(band)).toBe(tone);
  });

  it("cubre exactamente las tres bandas del coach", () => {
    expect(Object.keys(BODY_COMPOSITION_BAND_TONE).sort()).toEqual([
      "ambar",
      "rojo",
      "verde",
    ]);
  });
});

describe("getBodyCompositionFamilyVocabulary", () => {
  it("verde trae label y frase de la tabla familiar", () => {
    const entry = getBodyCompositionFamilyVocabulary("verde");
    expect(entry.familyLabel).toBe("En su curva esperada");
    expect(entry.tone).toBe("success");
    expect(entry.familySentence).toContain("dentro de lo esperado");
  });

  it("ambar trae label y frase de la tabla familiar", () => {
    const entry = getBodyCompositionFamilyVocabulary("ambar");
    expect(entry.familyLabel).toBe("En observación");
    expect(entry.tone).toBe("warning");
    expect(entry.familySentence).toContain("no es una alarma");
  });

  it("no existe fila rojo en el vocabulario familiar (contract §3c/§4)", () => {
    expect(Object.keys(BODY_COMPOSITION_FAMILY_VOCABULARY).sort()).toEqual([
      "ambar",
      "verde",
    ]);
  });

  it("ninguna frase familiar contiene una cifra (nunca mm ni %)", () => {
    for (const entry of Object.values(BODY_COMPOSITION_FAMILY_VOCABULARY)) {
      expect(entry.familySentence).not.toMatch(/\d/);
    }
  });
});
