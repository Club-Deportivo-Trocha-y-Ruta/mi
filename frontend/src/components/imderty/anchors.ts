/**
 * Anclas de la feature 047 compartidas entre la ficha del atleta y la
 * página de la planilla, sin que una importe los componentes de la otra.
 *
 * `IMDERTY_PROFILE_ANCHOR_ID` es el `id` de `ImdertyProfileCard`. Los
 * enlaces «Ver atleta» del panel de disponibilidad (`ReadinessPanel.tsx`)
 * apuntan a `/athletes/{id}?tab=imderty#imderty-profile`: la tarjeta vive
 * en la pestaña «Perfil IMDERTY» (solo admin/coach). La forma legada
 * `/athletes/{id}#imderty-profile` (sin `tab`) la sigue abriendo:
 * `AthleteDetailPage` la normaliza a `?tab=imderty`.
 */
export const IMDERTY_PROFILE_ANCHOR_ID = "imderty-profile";

/** Ruta de la ficha del atleta, en la pestaña y el ancla IMDERTY. */
export function imdertyProfileHref(athleteId: number): string {
  return `/athletes/${athleteId}?tab=imderty#${IMDERTY_PROFILE_ANCHOR_ID}`;
}
