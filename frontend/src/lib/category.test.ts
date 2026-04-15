import { describe, it, expect } from "vitest";
import { computeAgeDecimal, getCategory } from "./category";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// computeAgeDecimal
// Referencia: backend TestAgeDecimal
// ---------------------------------------------------------------------------

describe("computeAgeDecimal", () => {
  describe("cuando se calcula la edad decimal con fechas explícitas", () => {
    it("debería retornar entre 12.5 y 13.0 para nacido 2013-06-15 evaluado 2026-04-14", () => {
      // Referencia directa: test_basic_calculation del backend
      const birth = new Date(2013, 5, 15); // junio = mes 5 (0-indexed)
      const ref = new Date(2026, 3, 14);   // abril = mes 3
      const age = computeAgeDecimal(birth, ref);
      expect(age).toBeGreaterThan(12.5);
      expect(age).toBeLessThan(13.0);
    });

    it("debería retornar exactamente 10.0 para nacido 2016-01-01 evaluado 2026-01-01", () => {
      // Referencia: test_exact_year del backend — tolerancia 0.02
      const birth = new Date(2016, 0, 1);
      const ref = new Date(2026, 0, 1);
      const age = computeAgeDecimal(birth, ref);
      expect(Math.abs(age - 10.0)).toBeLessThan(0.02);
    });

    it("debería retornar 5.0 para exactamente 5 años cumplidos", () => {
      const birth = new Date(2020, 5, 15);
      const ref = new Date(2025, 5, 15);
      const age = computeAgeDecimal(birth, ref);
      // 365.25 días/año — tolerancia pequeña
      expect(Math.abs(age - 5.0)).toBeLessThan(0.02);
    });

    it("debería retornar un número positivo para cualquier fecha pasada", () => {
      const birth = new Date(2010, 0, 1);
      const ref = new Date(2020, 0, 1);
      const age = computeAgeDecimal(birth, ref);
      expect(age).toBeGreaterThan(0);
    });

    it("debería retornar un valor negativo si la referencia es anterior al nacimiento", () => {
      const birth = new Date(2020, 0, 1);
      const ref = new Date(2018, 0, 1);
      const age = computeAgeDecimal(birth, ref);
      expect(age).toBeLessThan(0);
    });
  });

  describe("cuando se usa fecha de referencia por defecto", () => {
    it("debería retornar un valor positivo cuando nació en el pasado", () => {
      // Referencia: test_uses_today_by_default del backend
      const birth = new Date(2016, 0, 1);
      const age = computeAgeDecimal(birth);
      expect(age).toBeGreaterThan(0);
    });

    it("debería usar la fecha actual como referencia por defecto", () => {
      const birth = new Date(2013, 0, 1);
      const now = new Date();
      const ageDefault = computeAgeDecimal(birth);
      const ageExplicit = computeAgeDecimal(birth, now);
      // La diferencia debe ser mínima (mismo instante de ejecución)
      expect(Math.abs(ageDefault - ageExplicit)).toBeLessThan(0.01);
    });
  });

  describe("precisión del resultado", () => {
    it("debería retornar el valor con 1 decimal (toFixed(1))", () => {
      const birth = new Date(2015, 5, 20);
      const ref = new Date(2026, 3, 14);
      const age = computeAgeDecimal(birth, ref);
      // toFixed(1) → máximo 1 decimal
      // Verificamos que el valor es exactamente representable con 1 decimal
      expect(Number(age.toFixed(1))).toBe(age);
    });
  });
});

// ---------------------------------------------------------------------------
// getCategory
// Referencia: backend TestCategory — test_fcc_2026_categories
// NOTA: el frontend usa "Teteros con pedales", el backend usa "Teteros"
//       Se testea lo que el frontend retorna realmente.
// ---------------------------------------------------------------------------

describe("getCategory", () => {
  describe("categorías unisex (Teteros)", () => {
    it("debería retornar 'Teteros con pedales' para nacido 2022 masculino", () => {
      expect(getCategory(2022, Sex.M)).toBe("Teteros con pedales");
    });

    it("debería retornar 'Teteros con pedales' para nacido 2023 femenino", () => {
      expect(getCategory(2023, Sex.F)).toBe("Teteros con pedales");
    });

    it("debería retornar 'Teteros con pedales' para nacido 2025", () => {
      expect(getCategory(2025, Sex.M)).toBe("Teteros con pedales");
    });
  });

  describe("Pre-Infantil A (2020-2021)", () => {
    it("debería retornar 'Pre-Infantil A' para nacido 2021 masculino", () => {
      expect(getCategory(2021, Sex.M)).toBe("Pre-Infantil A");
    });

    it("debería retornar 'Pre-Infantil A femenino' para nacido 2020 femenino", () => {
      expect(getCategory(2020, Sex.F)).toBe("Pre-Infantil A femenino");
    });
  });

  describe("Pre-Infantil B (2018-2019)", () => {
    it("debería retornar 'Pre-Infantil B' para nacido 2019 masculino", () => {
      expect(getCategory(2019, Sex.M)).toBe("Pre-Infantil B");
    });

    it("debería retornar 'Pre-Infantil B femenino' para nacido 2018 femenino", () => {
      expect(getCategory(2018, Sex.F)).toBe("Pre-Infantil B femenino");
    });
  });

  describe("Infantil A (2016-2017)", () => {
    it("debería retornar 'Infantil A' para nacido 2017 masculino", () => {
      expect(getCategory(2017, Sex.M)).toBe("Infantil A");
    });

    it("debería retornar 'Infantil A femenino' para nacido 2016 femenino", () => {
      expect(getCategory(2016, Sex.F)).toBe("Infantil A femenino");
    });
  });

  describe("Infantil B (2014-2015)", () => {
    it("debería retornar 'Infantil B' para nacido 2015 masculino", () => {
      expect(getCategory(2015, Sex.M)).toBe("Infantil B");
    });

    it("debería retornar 'Infantil B femenino' para nacido 2014 femenino", () => {
      expect(getCategory(2014, Sex.F)).toBe("Infantil B femenino");
    });
  });

  describe("Pre-juvenil A (2012-2013)", () => {
    it("debería retornar 'Pre-juvenil A' para nacido 2013 masculino", () => {
      expect(getCategory(2013, Sex.M)).toBe("Pre-juvenil A");
    });

    it("debería retornar 'Pre-juvenil A femenino' para nacido 2012 femenino", () => {
      expect(getCategory(2012, Sex.F)).toBe("Pre-juvenil A femenino");
    });
  });

  describe("Pre-juvenil B (2010-2011)", () => {
    it("debería retornar 'Pre-juvenil B' para nacido 2011 masculino", () => {
      expect(getCategory(2011, Sex.M)).toBe("Pre-juvenil B");
    });

    it("debería retornar 'Pre-juvenil B femenino' para nacido 2010 femenino", () => {
      expect(getCategory(2010, Sex.F)).toBe("Pre-juvenil B femenino");
    });
  });

  describe("Junior (2008-2009)", () => {
    it("debería retornar 'Junior' para nacido 2009 masculino", () => {
      expect(getCategory(2009, Sex.M)).toBe("Junior");
    });

    it("debería retornar 'Junior femenino' para nacido 2008 femenino", () => {
      expect(getCategory(2008, Sex.F)).toBe("Junior femenino");
    });
  });

  describe("Elite (≤ 2007)", () => {
    it("debería retornar 'Elite' para nacido 2007 masculino", () => {
      expect(getCategory(2007, Sex.M)).toBe("Elite");
    });

    it("debería retornar 'Elite femenina' para nacido 2000 femenino", () => {
      expect(getCategory(2000, Sex.F)).toBe("Elite femenina");
    });

    it("debería retornar 'Elite' para nacido 1990 masculino", () => {
      // El backend tiene Master para estos años — el frontend NO tiene Master
      // Verificamos que el frontend retorna Elite para todos los años <= 2007
      expect(getCategory(1990, Sex.M)).toBe("Elite");
    });
  });

  describe("casos de borde en años límite", () => {
    it("debería clasificar correctamente el año más antiguo de cada rango", () => {
      // Año más bajo de Infantil A = 2016
      expect(getCategory(2016, Sex.M)).toBe("Infantil A");
      // Año más alto de Infantil A = 2017
      expect(getCategory(2017, Sex.M)).toBe("Infantil A");
    });

    it("debería retornar 'Categoría no definida' para año sin regla (no debería ocurrir con < 2022)", () => {
      // Actualmente todos los años <= 2022 tienen cobertura
      // Probamos un año muy futuro que aún no tiene regla
      // El año 2030 supera minYear=2022, pero la regla Teteros no tiene maxYear → cubre todo
      // Por tanto 2030 → Teteros con pedales
      expect(getCategory(2030, Sex.M)).toBe("Teteros con pedales");
    });
  });
});
