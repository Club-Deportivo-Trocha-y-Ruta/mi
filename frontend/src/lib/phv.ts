import { type Sex, MaturationStatus } from "@/types/enums";

export interface PHVInput {
  sex: Sex;
  ageDecimal: number;
  weightKg: number;
  standingHeightCm: number;
  sittingHeightCm: number;
}

export interface PHVResult {
  legLengthCm: number;
  legSittingRatio: number;
  maturityOffset: number;
  ageAtPhv: number;
  maturationStatus: MaturationStatus;
  trainingImplications: string;
}

/**
 * Replica exacta de la formula Mirwald (2002) del backend (services/phv.py).
 * Retorna null si algun campo es 0 o invalido.
 */
export function calculatePHV(input: PHVInput): PHVResult | null {
  const { sex, ageDecimal, weightKg, standingHeightCm, sittingHeightCm } = input;

  if (
    ageDecimal <= 0 ||
    weightKg <= 0 ||
    standingHeightCm <= 0 ||
    sittingHeightCm <= 0
  ) {
    return null;
  }

  const legLength = standingHeightCm - sittingHeightCm;
  if (legLength <= 0) return null;

  const ratio = legLength / sittingHeightCm;

  let mo: number;
  if (sex === "M") {
    mo =
      -9.236 +
      0.0002708 * (legLength * sittingHeightCm) -
      0.001663 * (ageDecimal * legLength) +
      0.007216 * (ageDecimal * sittingHeightCm) +
      0.02292 * ((weightKg / standingHeightCm) * 100);
  } else {
    mo =
      -9.376 +
      0.0001882 * (legLength * sittingHeightCm) +
      0.0022 * (ageDecimal * legLength) +
      0.005841 * (ageDecimal * sittingHeightCm) -
      0.002658 * (ageDecimal * weightKg) +
      0.07693 * ((weightKg / standingHeightCm) * 100);
  }

  const ageAtPhv = ageDecimal - mo;

  let maturationStatus: MaturationStatus;
  let trainingImplications: string;

  if (mo < -1.0) {
    maturationStatus = MaturationStatus.PrePHV;
    trainingImplications =
      "Habilidades, juego, coordinacion. Fuerza solo peso corporal. Sin intervalos estructurados.";
  } else if (mo > 1.0) {
    maturationStatus = MaturationStatus.PostPHV;
    trainingImplications =
      "Puede iniciar fuerza progresiva. Entrenamiento mas estructurado permitido.";
  } else {
    maturationStatus = MaturationStatus.CircaPHV;
    trainingImplications =
      "EN ESTIRON: reducir volumen repetitivo. Revisar bici cada 4-6 sem. Vigilar Osgood-Schlatter.";
  }

  return {
    legLengthCm: Math.round(legLength * 10) / 10,
    legSittingRatio: Math.round(ratio * 10000) / 10000,
    maturityOffset: Math.round(mo * 100) / 100,
    ageAtPhv: Math.round(ageAtPhv * 100) / 100,
    maturationStatus,
    trainingImplications,
  };
}
