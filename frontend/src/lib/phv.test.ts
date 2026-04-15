import { describe, it, expect } from "vitest";
import { calculatePHV } from "./phv";
import { MaturationStatus, Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Valores de referencia alineados con backend/tests/test_phv.py
// ---------------------------------------------------------------------------

describe("calculatePHV", () => {
  // -------------------------------------------------------------------------
  // Casos de retorno null — entradas inválidas
  // -------------------------------------------------------------------------
  describe("cuando los inputs son inválidos", () => {
    it("debería retornar null si ageDecimal es 0", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 0, weightKg: 40, standingHeightCm: 145, sittingHeightCm: 72 })
      ).toBeNull();
    });

    it("debería retornar null si weightKg es 0", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 12, weightKg: 0, standingHeightCm: 145, sittingHeightCm: 72 })
      ).toBeNull();
    });

    it("debería retornar null si standingHeightCm es 0", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 12, weightKg: 40, standingHeightCm: 0, sittingHeightCm: 72 })
      ).toBeNull();
    });

    it("debería retornar null si sittingHeightCm es 0", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 12, weightKg: 40, standingHeightCm: 145, sittingHeightCm: 0 })
      ).toBeNull();
    });

    it("debería retornar null si ageDecimal es negativo", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: -1, weightKg: 40, standingHeightCm: 145, sittingHeightCm: 72 })
      ).toBeNull();
    });

    it("debería retornar null si legLength es 0 (sentado igual a de pie)", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 12, weightKg: 40, standingHeightCm: 72, sittingHeightCm: 72 })
      ).toBeNull();
    });

    it("debería retornar null si legLength es negativo (sentado mayor a de pie)", () => {
      expect(
        calculatePHV({ sex: Sex.M, ageDecimal: 12, weightKg: 40, standingHeightCm: 70, sittingHeightCm: 72 })
      ).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Cálculo de longitud de pierna y ratio
  // Referencia: test_leg_length_calculation — M, 12y, 45kg, 155cm, 73cm
  //   legLength = 155 - 73 = 82 cm
  //   ratio     = 82 / 73 ≈ 1.1233 (redondeado a 4 decimales)
  // -------------------------------------------------------------------------
  describe("cálculo de longitud de pierna y ratio", () => {
    it("debería calcular legLengthCm como standing - sitting", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 12.0,
        weightKg: 45.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      expect(result!.legLengthCm).toBe(82.0);
    });

    it("debería calcular legSittingRatio redondeado a 4 decimales", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 12.0,
        weightKg: 45.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      expect(result!.legSittingRatio).toBe(Math.round((82.0 / 73.0) * 10000) / 10000);
    });

    it("debería calcular legLengthCm correctamente — M, 10.5y", () => {
      // Referencia: test_male_pre_phv — M, 10.5y, 35kg, 140cm, 73cm
      // legLength = 140 - 73 = 67 cm
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 10.5,
        weightKg: 35.0,
        standingHeightCm: 140.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      expect(result!.legLengthCm).toBe(67.0);
    });
  });

  // -------------------------------------------------------------------------
  // Estado de maduración masculino — Pre-PHV
  // Referencia: test_male_pre_phv — M, 10.5y, 35kg, 140cm, 73cm → Pre-PHV
  // -------------------------------------------------------------------------
  describe("cuando es un varón Pre-PHV", () => {
    it("debería retornar maturationStatus = Pre-PHV dado offset < -1", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 10.5,
        weightKg: 35.0,
        standingHeightCm: 140.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      expect(result!.maturationStatus).toBe(MaturationStatus.PrePHV);
    });

    it("debería incluir implicaciones de entrenamiento para Pre-PHV", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 10.5,
        weightKg: 35.0,
        standingHeightCm: 140.0,
        sittingHeightCm: 73.0,
      });
      expect(result!.trainingImplications).toContain("juego");
    });
  });

  // -------------------------------------------------------------------------
  // Estado de maduración masculino — Post-PHV
  // Referencia: test_male_post_phv — M, 16y, 65kg, 175cm, 85cm → Post-PHV
  // -------------------------------------------------------------------------
  describe("cuando es un varón Post-PHV", () => {
    it("debería retornar maturationStatus = Post-PHV dado offset > 1", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 16.0,
        weightKg: 65.0,
        standingHeightCm: 175.0,
        sittingHeightCm: 85.0,
      });
      expect(result).not.toBeNull();
      expect(result!.maturationStatus).toBe(MaturationStatus.PostPHV);
    });

    it("debería incluir implicaciones de entrenamiento para Post-PHV", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 16.0,
        weightKg: 65.0,
        standingHeightCm: 175.0,
        sittingHeightCm: 85.0,
      });
      expect(result!.trainingImplications).toContain("fuerza progresiva");
    });
  });

  // -------------------------------------------------------------------------
  // Estado de maduración femenino — rango válido
  // Referencia: test_female_circa_phv — F, 12y, 42kg, 155cm, 80cm
  //   debe retornar uno de los tres estados válidos
  // -------------------------------------------------------------------------
  describe("cuando es una atleta femenina", () => {
    it("debería retornar un maturationStatus válido para F 12y", () => {
      const result = calculatePHV({
        sex: Sex.F,
        ageDecimal: 12.0,
        weightKg: 42.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 80.0,
      });
      expect(result).not.toBeNull();
      const validStatuses = [
        MaturationStatus.PrePHV,
        MaturationStatus.CircaPHV,
        MaturationStatus.PostPHV,
      ];
      expect(validStatuses).toContain(result!.maturationStatus);
    });

    it("debería retornar legLengthCm y ageAtPhv para F 12y", () => {
      const result = calculatePHV({
        sex: Sex.F,
        ageDecimal: 12.0,
        weightKg: 42.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 80.0,
      });
      expect(result).not.toBeNull();
      expect(result!.legLengthCm).toBe(75.0); // 155 - 80
      expect(typeof result!.ageAtPhv).toBe("number");
    });

    it("debería retornar Post-PHV para atleta femenina madura (15y, grande)", () => {
      // Atleta femenina con valores grandes debería ser Post-PHV
      const result = calculatePHV({
        sex: Sex.F,
        ageDecimal: 15.0,
        weightKg: 55.0,
        standingHeightCm: 165.0,
        sittingHeightCm: 88.0,
      });
      expect(result).not.toBeNull();
      expect(result!.maturationStatus).toBe(MaturationStatus.PostPHV);
    });

    it("debería usar la fórmula femenina (resultado diferente al masculino con mismos datos)", () => {
      const input = { ageDecimal: 12.0, weightKg: 45.0, standingHeightCm: 155.0, sittingHeightCm: 73.0 };
      const male = calculatePHV({ sex: Sex.M, ...input });
      const female = calculatePHV({ sex: Sex.F, ...input });
      expect(male).not.toBeNull();
      expect(female).not.toBeNull();
      // Las fórmulas son distintas — el offset debe diferir
      expect(male!.maturityOffset).not.toBe(female!.maturityOffset);
    });
  });

  // -------------------------------------------------------------------------
  // ageAtPhv = ageDecimal - maturityOffset
  // Referencia: test_age_at_phv_formula — M, 12.5y, 45kg, 155cm, 73cm
  // -------------------------------------------------------------------------
  describe("cálculo de ageAtPhv", () => {
    it("debería calcular ageAtPhv = ageDecimal - maturityOffset (redondeado a 2 dec)", () => {
      const age = 12.5;
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: age,
        weightKg: 45.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      const expectedAgeAtPhv = Math.round((age - result!.maturityOffset) * 100) / 100;
      expect(result!.ageAtPhv).toBe(expectedAgeAtPhv);
    });

    it("debería redondear maturityOffset a 2 decimales", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 12.5,
        weightKg: 45.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 73.0,
      });
      const asString = result!.maturityOffset.toString();
      const decimals = asString.includes(".") ? asString.split(".")[1].length : 0;
      expect(decimals).toBeLessThanOrEqual(2);
    });
  });

  // -------------------------------------------------------------------------
  // Clasificación por boundary values en maturityOffset
  // Pre-PHV: mo < -1.0
  // Circa-PHV: -1.0 <= mo <= 1.0
  // Post-PHV: mo > 1.0
  // -------------------------------------------------------------------------
  describe("boundary values del maturityOffset", () => {
    it("debería clasificar Circa-PHV con valores que producen offset ~0.49", () => {
      // M, 14.0y, 55kg, 162cm, 80cm → maturityOffset ≈ +0.49 → Circa-PHV
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 14.0,
        weightKg: 55.0,
        standingHeightCm: 162.0,
        sittingHeightCm: 80.0,
      });
      expect(result).not.toBeNull();
      expect(result!.maturityOffset).toBeGreaterThanOrEqual(-1.0);
      expect(result!.maturityOffset).toBeLessThanOrEqual(1.0);
      expect(result!.maturationStatus).toBe(MaturationStatus.CircaPHV);
    });

    it("debería incluir implicaciones de entrenamiento para Circa-PHV", () => {
      // M, 14.0y, 55kg, 162cm, 80cm → maturityOffset ≈ +0.49 → Circa-PHV garantizado
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 14.0,
        weightKg: 55.0,
        standingHeightCm: 162.0,
        sittingHeightCm: 80.0,
      });
      expect(result).not.toBeNull();
      expect(result!.maturationStatus).toBe(MaturationStatus.CircaPHV);
      expect(result!.trainingImplications).toContain("ESTIRON");
    });
  });

  // -------------------------------------------------------------------------
  // Consistencia de la estructura de retorno
  // -------------------------------------------------------------------------
  describe("estructura del resultado", () => {
    it("debería retornar todos los campos requeridos con tipos correctos", () => {
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 12.0,
        weightKg: 45.0,
        standingHeightCm: 155.0,
        sittingHeightCm: 73.0,
      });
      expect(result).not.toBeNull();
      expect(typeof result!.legLengthCm).toBe("number");
      expect(typeof result!.legSittingRatio).toBe("number");
      expect(typeof result!.maturityOffset).toBe("number");
      expect(typeof result!.ageAtPhv).toBe("number");
      expect(typeof result!.maturationStatus).toBe("string");
      expect(typeof result!.trainingImplications).toBe("string");
    });

    it("debería retornar legLengthCm redondeado a 1 decimal", () => {
      // 155.3 - 73.1 = 82.2 exacto → 82.2
      const result = calculatePHV({
        sex: Sex.M,
        ageDecimal: 12.0,
        weightKg: 45.0,
        standingHeightCm: 155.3,
        sittingHeightCm: 73.1,
      });
      expect(result).not.toBeNull();
      expect(result!.legLengthCm).toBe(Math.round((155.3 - 73.1) * 10) / 10);
    });
  });
});
