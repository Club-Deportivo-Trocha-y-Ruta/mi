/**
 * BodyCompositionDetailDialog — detalle por sitio de composición corporal
 * (feature 046, US2, T039), per `contracts/body-composition-reading.md` y
 * `contracts/skinfolds-api.md` §1 (`BodyCompositionOut`).
 *
 * Se construye sobre `components/ui/dialog.tsx` (Radix `Dialog`), que ya
 * resuelve foco atrapado + cierre con Escape + botón de cerrar — mismo
 * criterio que el resto de diálogos del proyecto (`ArchiveAthleteDialog`,
 * `NotifyParentsDialog`).
 *
 * Privacidad (Ley 1581): sólo cifras/fechas/códigos de un menor, nunca
 * nombre — coherente con `BodyCompositionOut`.
 */
import { Sparkline } from "@/components/athletes/growth/Sparkline";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  BodyCompositionOut,
  ReferencePoint,
  SkinfoldSetOut,
  SkinfoldSite,
} from "@/types/bodyComposition.types";

export interface BodyCompositionDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: BodyCompositionOut | undefined;
}

const SITE_LABELS: Record<SkinfoldSite, string> = {
  triceps: "Tríceps",
  biceps: "Bíceps",
  subscapular: "Subescapular",
  medial_calf: "Pantorrilla",
  iliac_crest: "Cresta ilíaca",
  supraspinale: "Supraespinal",
};

const SITE_ORDER: SkinfoldSite[] = [
  "triceps",
  "biceps",
  "subscapular",
  "medial_calf",
  "iliac_crest",
  "supraspinale",
];

const MONTHS_ES_SHORT = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/** Igual a `NextMeasurementCard.tsx::formatDueDate`. */
function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const label = MONTHS_ES_SHORT[Number(month) - 1] ?? month;
  return `${Number(day)} ${label} ${year}`;
}

function formatMmOrIncomplete(value: number | null): string {
  return value === null ? "Suma incompleta" : `${value.toFixed(1)} mm`;
}

/** FR spec.md §71: "falta tríceps" / "falta pantorrilla" cuando falta un insumo de la ecuación. */
function estimateMissingReason(set: SkinfoldSetOut): string | null {
  if (set.sites.triceps.declined) return "Falta tríceps";
  if (set.sites.medial_calf.declined) return "Falta pantorrilla";
  return null;
}

function formatEstimate(set: SkinfoldSetOut): string {
  if (set.body_fat_pct === null) {
    return estimateMissingReason(set) ?? "—";
  }
  return `${set.body_fat_pct.toFixed(1)}% (estimado ±${set.margin_pct} puntos)`;
}

interface ReferenceBadgeProps {
  label: string;
  point: ReferencePoint;
}

function ReferenceBadge({ label, point }: ReferenceBadgeProps) {
  if (point.code === "unavailable" || point.percentile === null) {
    return (
      <p className="text-xs text-mid-gray">
        {label}: sin referencia para esta edad
      </p>
    );
  }
  return (
    <p className="text-xs text-mid-gray">
      {label}: P{Math.round(point.percentile)} ({point.code})
    </p>
  );
}

export function BodyCompositionDetailDialog({
  open,
  onOpenChange,
  data,
}: BodyCompositionDetailDialogProps) {
  const sets = data?.sets ?? [];
  const sortedSets = [...sets].sort((a, b) =>
    b.evaluation_date.localeCompare(a.evaluation_date),
  );
  const perSite = data?.series?.per_site;
  const reading = data?.reading;
  const reference = data?.reference;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Composición corporal — detalle por sitio</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-5">
          <section aria-label="Tendencia por sitio" className="space-y-2">
            <h3 className="text-sm font-medium text-charcoal">Tendencia por sitio</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {SITE_ORDER.map((site) => {
                const points = perSite?.[site] ?? [];
                const values = points.map((p) => p.value);
                const latestSet = sortedSets[0];
                const latestDeclined = latestSet?.sites[site]?.declined ?? false;
                return (
                  <div
                    key={site}
                    className="flex items-center justify-between gap-2 rounded-card bg-surface-raised px-3 py-2 ring-1 ring-hairline"
                  >
                    <span className="text-sm text-charcoal">{SITE_LABELS[site]}</span>
                    <div className="flex items-center gap-2">
                      {latestDeclined && (
                        <span className="text-xs text-mid-gray">Omitido</span>
                      )}
                      {values.length >= 2 && (
                        <Sparkline
                          values={values}
                          ariaLabel={`Evolución del pliegue de ${SITE_LABELS[site]}, últimas ${values.length} tomas`}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section aria-label="Historial de sets" className="space-y-2">
            <h3 className="text-sm font-medium text-charcoal">Historial de tomas</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-xs text-mid-gray">
                    <th className="py-1 pr-3">Fecha</th>
                    <th className="py-1 pr-3">Σ4</th>
                    <th className="py-1 pr-3">Σ6</th>
                    <th className="py-1 pr-3">% grasa (est.)</th>
                    <th className="py-1 pr-3">Caliper</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSets.map((set) => (
                    <tr key={set.record_id} className="border-t border-hairline">
                      <td className="py-1.5 pr-3 text-charcoal">{formatDate(set.evaluation_date)}</td>
                      <td className="py-1.5 pr-3 text-charcoal">{formatMmOrIncomplete(set.sum4_mm)}</td>
                      <td className="py-1.5 pr-3 text-charcoal">{formatMmOrIncomplete(set.sum6_mm)}</td>
                      <td className="py-1.5 pr-3 text-charcoal">{formatEstimate(set)}</td>
                      <td className="py-1.5 pr-3 text-mid-gray">{set.caliper_model}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {reading && (
            <section aria-label="Referencia poblacional" className="space-y-1">
              <h3 className="text-sm font-medium text-charcoal">Referencia poblacional</h3>
              <ReferenceBadge label="Tríceps" point={reading.reference_triceps} />
              <ReferenceBadge label="Subescapular" point={reading.reference_subscapular} />
              {reference && (
                <p className="text-xs text-mid-gray">
                  Referencia: {reference.population}, medida en lado {reference.side};
                  contexto, no veredicto.
                </p>
              )}
            </section>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
