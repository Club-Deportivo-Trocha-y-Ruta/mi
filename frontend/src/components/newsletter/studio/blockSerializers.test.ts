import { describe, it, expect } from "vitest";

import {
  countWords,
  parseAnalystReading,
  parseFamilyCompass,
  parseObservations,
  serializeAnalystReading,
  serializeFamilyCompass,
  serializeObservations,
} from "@/components/newsletter/studio/blockSerializers";
import type { Observation } from "@/types/stageLog.types";

describe("countWords", () => {
  it("cuenta palabras separadas por espacios", () => {
    expect(countWords("Un mes de progreso constante")).toBe(5);
  });

  it("devuelve 0 para texto vacío o nulo", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   ")).toBe(0);
    expect(countWords(null)).toBe(0);
    expect(countWords(undefined)).toBe(0);
  });
});

describe("serializeObservations / parseObservations", () => {
  const original: Observation[] = [
    { claim: "Asistencia alta", evidence: "9 de 10 sesiones", block_ref: "attendance" },
    { claim: "Mejoró la técnica", evidence: "4.1/5 vs 3.5", block_ref: "technical" },
    { claim: "Buena carrera", evidence: "P2 en la válida", block_ref: "race" },
  ];

  it("serializa y reconstruye 3 observaciones preservando block_ref por índice", () => {
    const text = serializeObservations(original);
    const parsed = parseObservations(text, original);
    expect(parsed).toHaveLength(3);
    expect(parsed[0]).toEqual(original[0]);
    expect(parsed[1].block_ref).toBe("technical");
    expect(parsed[2].block_ref).toBe("race");
  });

  it("aplica la edición del coach al claim/evidence conservando block_ref", () => {
    const edited = "Asistencia excelente\n10 de 10 sesiones\n\nMejoró la técnica\n4.1/5 vs 3.5\n\nBuena carrera\nP2 en la válida";
    const parsed = parseObservations(edited, original);
    expect(parsed[0].claim).toBe("Asistencia excelente");
    expect(parsed[0].evidence).toBe("10 de 10 sesiones");
    expect(parsed[0].block_ref).toBe("attendance");
  });

  it("usa 'attendance' como fallback de block_ref si el coach agrega una observación extra", () => {
    const original2: Observation[] = [original[0]];
    const text = "Uno\nEvidencia 1\n\nDos\nEvidencia 2";
    const parsed = parseObservations(text, original2);
    expect(parsed).toHaveLength(2);
    expect(parsed[1].block_ref).toBe("attendance");
  });
});

describe("serializeAnalystReading / parseAnalystReading", () => {
  it("hace round-trip de headline_family y action_family", () => {
    const reading = { headline_family: "Buen ritmo en la válida", action_family: "Sostener el trabajo de frenada" };
    const text = serializeAnalystReading(reading);
    expect(text).toContain("Titular: Buen ritmo en la válida");
    expect(text).toContain("Acción: Sostener el trabajo de frenada");
    expect(parseAnalystReading(text)).toEqual(reading);
  });

  it("serializa vacío cuando reading es null", () => {
    expect(serializeAnalystReading(null)).toBe("");
  });
});

describe("serializeFamilyCompass / parseFamilyCompass", () => {
  it("hace round-trip de los 3 campos", () => {
    const compass = {
      conversation_question: "¿Qué fue lo más difícil de este mes?",
      monthly_challenge: "Practicar la frenada en curva 2 veces por semana",
      what_to_watch: "La postura de pedaleo en la próxima válida",
    };
    const text = serializeFamilyCompass(compass);
    expect(parseFamilyCompass(text)).toEqual(compass);
  });

  it("serializa vacío cuando compass es null", () => {
    expect(serializeFamilyCompass(null)).toBe("");
  });
});
