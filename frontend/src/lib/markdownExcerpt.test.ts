import { describe, it, expect } from "vitest";

import { toPlainExcerpt } from "@/lib/markdownExcerpt";

describe("toPlainExcerpt", () => {
  it("elimina la línea de header (no solo los '#')", () => {
    const result = toPlainExcerpt("## Hallazgo principal\nEl bajón táctico del cierre.");
    expect(result).toBe("El bajón táctico del cierre.");
    expect(result).not.toContain("#");
    expect(result).not.toContain("Hallazgo principal");
  });

  it("quita énfasis con cierre (negrita/cursiva)", () => {
    expect(toPlainExcerpt("El bajón **táctico** del cierre")).toBe(
      "El bajón táctico del cierre",
    );
    expect(toPlainExcerpt("El bajón _táctico_ del cierre")).toBe(
      "El bajón táctico del cierre",
    );
  });

  it("quita marcadores de énfasis truncados sin cierre (excerpt cortado a 200 chars)", () => {
    const result = toPlainExcerpt("## Hallazgo principal\nEl bajón **táctico");
    expect(result).toBe("El bajón táctico");
    expect(result).not.toContain("*");
  });

  it("quita código en línea (backticks)", () => {
    expect(toPlainExcerpt("Revisa `cadencia` en la subida")).toBe(
      "Revisa cadencia en la subida",
    );
  });

  it("convierte links [texto](url) en solo el texto", () => {
    expect(toPlainExcerpt("Ver [el resumen](https://ejemplo.com)")).toBe(
      "Ver el resumen",
    );
  });

  it("quita marcadores de lista al inicio de línea", () => {
    expect(toPlainExcerpt("- primero\n- segundo")).toBe("primero segundo");
    expect(toPlainExcerpt("1. primero\n2. segundo")).toBe("primero segundo");
  });

  it("quita marcadores de blockquote al inicio de línea", () => {
    expect(toPlainExcerpt("> una cita")).toBe("una cita");
  });

  it("colapsa espacios en blanco múltiples", () => {
    expect(toPlainExcerpt("uno   \n\n  dos")).toBe("uno dos");
  });

  it("devuelve cadena vacía cuando solo hay headers", () => {
    expect(toPlainExcerpt("## Hallazgo principal")).toBe("");
  });

  it("no rompe con texto plano sin markdown", () => {
    expect(toPlainExcerpt("Tercer lugar, progreso en frenada.")).toBe(
      "Tercer lugar, progreso en frenada.",
    );
  });
});
