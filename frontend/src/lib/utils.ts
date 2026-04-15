import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Enmascara un número de teléfono mostrando solo los últimos 4 dígitos.
 * Ejemplo: "+57 311 234 5678" → "+57 311 ···-5678"
 * Si el string tiene menos de 4 caracteres, retorna "···".
 */
export function maskPhone(phone: string | null): string {
  if (!phone) return "—";
  const trimmed = phone.trim();
  if (trimmed.length < 4) return "···";
  const last4 = trimmed.slice(-4);
  const prefix = trimmed.slice(0, trimmed.length - 4);
  return `${prefix}···-${last4}`;
}
