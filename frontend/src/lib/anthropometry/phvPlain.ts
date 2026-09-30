import { MaturationStatus } from "@/types/enums";

/** Etiqueta en lenguaje llano de la etapa de maduración (feature 048). */
export const PHV_PLAIN_LABEL: Record<MaturationStatus, string> = {
  [MaturationStatus.PrePHV]: "Aún no llega al estirón",
  [MaturationStatus.CircaPHV]: "Está en pleno estirón",
  [MaturationStatus.PostPHV]: "Ya pasó el estirón",
};

export function phvPlainLabel(status: MaturationStatus): string {
  return PHV_PLAIN_LABEL[status];
}
