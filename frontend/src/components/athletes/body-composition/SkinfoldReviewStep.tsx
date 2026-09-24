import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { computeSiteValue } from "@/lib/bodyComposition/readings";
import { SKINFOLD_SITE_ORDER } from "@/lib/bodyComposition/siteDiagrams";
import type { SkinfoldWizardFormValues } from "@/schemas/bodyComposition.schema";
import type { SkinfoldSite } from "@/types/bodyComposition.types";

/**
 * SkinfoldReviewStep — último paso del asistente de captura de pliegues
 * cutáneos (feature 046, T027): tabla de revisión sitio → valor, previsualización
 * de Σ4/Σ6 y confirmación final.
 *
 * Puramente de presentación: recibe los `sites` ya validados por RHF
 * (`skinfoldWizardFormSchema`, T014) y no vuelve a validar nada — sólo
 * calcula el valor de cada sitio (`computeSiteValue`, misma función que
 * `SkinfoldSiteStep`, T026) para mostrar la previsualización de Σ4/Σ6 que
 * el backend recalculará de forma autoritativa al guardar.
 */
export interface SkinfoldReviewStepProps {
  sites: SkinfoldWizardFormValues["sites"];
  onSubmit: () => void;
  isSubmitting?: boolean;
}

const SITE_LABEL_ES: Record<SkinfoldSite, string> = {
  triceps: "Tríceps",
  biceps: "Bíceps",
  subscapular: "Subescapular",
  medial_calf: "Pantorrilla medial",
  iliac_crest: "Cresta ilíaca",
  supraspinale: "Supraespinal",
};

/** Sitios que componen Σ4 (data-model.md §1). */
const SUM4_SITES: readonly SkinfoldSite[] = [
  "triceps",
  "biceps",
  "subscapular",
  "medial_calf",
];

function siteValueOrNull(site: SkinfoldWizardFormValues["sites"][SkinfoldSite]): number | null {
  if (site.declined) return null;
  return computeSiteValue(site.readings);
}

function readingsCount(site: SkinfoldWizardFormValues["sites"][SkinfoldSite]): number {
  return site.declined ? 0 : site.readings.length;
}

function formatMm(value: number): string {
  return `${value.toFixed(1)} mm`;
}

/** Suma de un subconjunto de sitios, o `null` si alguno está declinado ("suma incompleta"). */
function sumOrNull(
  sites: SkinfoldWizardFormValues["sites"],
  siteKeys: readonly SkinfoldSite[],
): number | null {
  let total = 0;
  for (const key of siteKeys) {
    const value = siteValueOrNull(sites[key]);
    if (value === null) return null;
    total += value;
  }
  return total;
}

export function SkinfoldReviewStep({ sites, onSubmit, isSubmitting = false }: SkinfoldReviewStepProps) {
  const sum4 = sumOrNull(sites, SUM4_SITES);
  const sum6 = sumOrNull(sites, SKINFOLD_SITE_ORDER);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-charcoal">Revisar medición</h2>
        <p className="text-sm text-mid-gray">
          Confirma los valores antes de guardar. Puedes volver a cualquier
          sitio para corregirlo.
        </p>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Sitio</TableHead>
            <TableHead>Valor</TableHead>
            <TableHead>Lecturas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {SKINFOLD_SITE_ORDER.map((site) => {
            const siteData = sites[site];
            const value = siteValueOrNull(siteData);
            return (
              <TableRow key={site}>
                <TableCell className="font-medium text-charcoal">
                  {SITE_LABEL_ES[site]}
                </TableCell>
                <TableCell>
                  {value === null ? (
                    <span className="text-mid-gray">Omitido</span>
                  ) : (
                    formatMm(value)
                  )}
                </TableCell>
                <TableCell>{readingsCount(siteData)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <div className="flex flex-col gap-1 rounded-control bg-light-gray p-4 text-sm">
        <div className="flex justify-between">
          <span className="text-charcoal">Σ4 (tríceps + bíceps + subescapular + pantorrilla)</span>
          <span className="font-semibold text-charcoal">
            {sum4 === null ? "Suma incompleta" : formatMm(sum4)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-charcoal">Σ6 (los seis sitios)</span>
          <span className="font-semibold text-charcoal">
            {sum6 === null ? "Suma incompleta" : formatMm(sum6)}
          </span>
        </div>
      </div>

      <div className="flex justify-end">
        <Button type="button" size="lg" onClick={onSubmit} disabled={isSubmitting}>
          Guardar medición
        </Button>
      </div>
    </div>
  );
}
