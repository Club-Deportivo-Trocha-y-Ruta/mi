/**
 * Aviso de cambios para las familias (feature 045, T063, research R-14).
 *
 * El percentil pasa a calcularse con los tiempos y la referencia principal es
 * la brecha con la mediana de la categoría, así que algunas cifras de meses
 * anteriores se ven distintas. En vez de un correo aparte, el coach lo avisa
 * en la `coach_note` de la bitácora: `BlockPanel` ofrece «Insertar aviso de
 * cambios», que abre el editor de esa nota con este texto ya escrito. El coach
 * lo edita y lo guarda; nada se envía automáticamente.
 *
 * Copy en español neutro (Colombia). Es la versión CONDENSADA de
 * `contracts/ui-copy.md` (74 palabras): el backend limita `coach_note` a 60
 * palabras — `AthleteNewsletterPatch` responde 422 y `StageLog` la trunca al
 * leer — así que el texto del contrato completo no se podría guardar. Los
 * cuatro puntos se conservan: referencia a la mediana, percentil por tiempo
 * (cifras viejas distintas), resultados sin cambios y dónde verlo. El test de
 * este módulo fija ≤60 palabras y ≤600 caracteres.
 */
import { useState } from "react";

export const CHANGE_NOTICE_TEXT =
  "Actualizamos cómo mostramos los resultados: ahora la referencia principal es la brecha con la mediana de su categoría, qué tan cerca estuvo del tiempo típico del grupo. El percentil se calcula con los tiempos, así que algunas cifras de meses anteriores pueden verse distintas. Los resultados no cambiaron, solo la forma de leerlos. Todo está en la pestaña «Carreras».";

/**
 * Clave de localStorage donde se recuerda que ESTE coach descartó la oferta.
 * Versionada (`v1`) y por usuario: un navegador compartido no mezcla coaches.
 * Sólo se guarda el descarte, no la inserción — el coach puede usar el aviso en
 * la bitácora de cada atleta hasta que lo descarte.
 */
export function changeNoticeDismissKey(userId: number | string): string {
  return `tyr:045-notice-dismissed:v1:${userId}`;
}

/** `true` si el coach ya descartó la oferta. Sin storage (modo privado) → `false`. */
function readDismissed(userId: number | string): boolean {
  if (typeof window === "undefined" || !window.localStorage) return false;
  try {
    return window.localStorage.getItem(changeNoticeDismissKey(userId)) === "1";
  } catch {
    return false;
  }
}

/** Mejor esfuerzo: si el storage falla, el descarte igual rige en memoria. */
function writeDismissed(userId: number | string): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(changeNoticeDismissKey(userId), "1");
  } catch {
    // Cuota o modo privado — ver comentario arriba.
  }
}

export interface ChangeNoticeOffer {
  /** `false` sin usuario (no hay clave por coach a la que atar el descarte). */
  canOffer: boolean;
  dismissed: boolean;
  dismiss: () => void;
}

/**
 * Estado de la oferta para un coach. Sin `userId` nunca se ofrece: sin clave
 * por usuario, un descarte se filtraría a otro coach del mismo navegador.
 */
export function useChangeNoticeOffer(
  userId: number | string | null | undefined,
): ChangeNoticeOffer {
  const [dismissedInMemory, setDismissedInMemory] = useState(false);
  const hasUser = userId !== null && userId !== undefined;
  const dismissed =
    dismissedInMemory || (hasUser && readDismissed(userId));

  function dismiss() {
    if (hasUser) writeDismissed(userId);
    setDismissedInMemory(true);
  }

  return { canOffer: hasUser, dismissed, dismiss };
}
