/**
 * NewsletterSelectionBar — barra fija inferior para enviar al boletín los
 * insights seleccionados (solo coach). Movida tal cual desde
 * `AthleteAIAnalysisTab` (Sprint 2 BB4, feature 045 T038): la selección
 * vive en `AnalysisView`; aquí solo el envío y sus tres estados
 * (selección → éxito → error con reintento).
 *
 * Privacidad Ley 1581: solo se monta para `audience="coach"`; la familia
 * nunca ve casillas ni esta barra.
 */
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { useAttachInsightsToNewsletter } from "@/api/athleteNewsletters";
import type { AttachInsightsRequest } from "@/types/athleteNewsletter.types";

export interface NewsletterSelectionBarProps {
  athleteId: number;
  /** Ids de insights seleccionados para el boletín. */
  selection: ReadonlySet<number>;
  /** Vacía la selección (tras enviar con éxito y con «Limpiar»). */
  onClear: () => void;
}

export function NewsletterSelectionBar({
  athleteId,
  selection,
  onClear,
}: NewsletterSelectionBarProps) {
  const attachMutation = useAttachInsightsToNewsletter(athleteId);
  // Último payload enviado, para el botón «Reintentar».
  const lastPayloadRef = useRef<AttachInsightsRequest | null>(null);

  const send = (payload: AttachInsightsRequest) => {
    lastPayloadRef.current = payload;
    attachMutation.mutate(payload, { onSuccess: onClear });
  };

  // Tras el éxito la selección ya se limpió (onSuccess). Se muestra 3 s la
  // confirmación y luego se resetea la mutación para que la barra
  // desaparezca. T013 (feature 036): TanStack Query v5 devuelve un objeto
  // `attachMutation` NUEVO en cada render — depender del objeto completo
  // reiniciaba este timer y la confirmación nunca se limpiaba; `isSuccess`
  // (booleano) y `reset` (estable) son lo único que debe disparar el efecto.
  useEffect(() => {
    if (attachMutation.isSuccess && selection.size === 0) {
      const timer = setTimeout(() => {
        attachMutation.reset();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [attachMutation.isSuccess, attachMutation.reset, selection.size]);

  const visible =
    selection.size > 0 || attachMutation.isSuccess || attachMutation.isError;
  if (!visible) return null;

  return (
    <div
      className="sticky bottom-4 left-0 right-0 z-20 mx-auto flex max-w-2xl items-center justify-between gap-3 rounded-xl bg-charcoal p-3 text-surface shadow-lg"
      data-testid="newsletter-action-bar"
      // T093 (feature 036, US6): la barra cambia de estado sin avisar a un
      // lector de pantalla. Ninguno de los tres estados es lo bastante
      // urgente para "assertive": el envío es reintentable y no hay pérdida
      // de datos en juego.
      role="status"
      aria-live="polite"
    >
      {attachMutation.isError ? (
        <>
          <span className="text-sm text-red-200" data-testid="newsletter-action-bar-error">
            No pudimos agregar al boletín. Intenta de nuevo.
          </span>
          <Button
            variant="default"
            size="sm"
            onClick={() => {
              if (lastPayloadRef.current) send(lastPayloadRef.current);
            }}
            className="min-h-12 bg-surface text-charcoal hover:bg-surface/90"
          >
            Reintentar
          </Button>
        </>
      ) : attachMutation.isSuccess && selection.size === 0 ? (
        <span
          className="text-sm text-emerald-200"
          data-testid="newsletter-action-bar-success"
        >
          Agregados al boletín del mes
        </span>
      ) : (
        <>
          <span className="text-sm">
            {selection.size}{" "}
            {selection.size === 1
              ? "insight seleccionado"
              : "insights seleccionados"}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onClear}
              disabled={attachMutation.isPending}
              className="min-h-12 border-surface/30 text-surface hover:bg-surface/10 hover:text-surface"
            >
              Limpiar
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                const ids = Array.from(selection);
                if (ids.length === 0) return;
                send({ insight_ids: ids });
              }}
              disabled={attachMutation.isPending}
              className="min-h-12 bg-surface text-charcoal hover:bg-surface/90"
              data-testid="newsletter-action-bar-submit"
            >
              {attachMutation.isPending ? "Enviando…" : "Enviar a boletín"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
