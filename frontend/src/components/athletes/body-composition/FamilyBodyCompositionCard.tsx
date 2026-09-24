/**
 * FamilyBodyCompositionCard — tarjeta narrativa para familias (feature 046,
 * US4, T051), mirroring `FamilyBandCards.tsx`: ícono + etiqueta familiar
 * (`StatusBadge`) y una sola frase narrativa — **nunca** cifras (%BF, Σ mm)
 * ni la banda del coach (`docs/21-body-composition/research-safeguards-referral.md`
 * §5, `contracts/skinfolds-api.md` §5). Recibe el bloque ya resuelto por el
 * backend (`BodyCompositionFamilySummary`); no hace fetch ni gestiona
 * loading/error — eso es responsabilidad del contenedor (`GrowthTab`).
 */
import { Info } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { BodyCompositionFamilySummary, FamilyBand } from "@/types/bodyComposition.types";

export interface FamilyBodyCompositionCardProps {
  /** Bloque `body_composition` de `GrowthSummaryOut` para padres, o `null`. */
  summary: BodyCompositionFamilySummary | null;
}

const NO_DATA_MESSAGE = "Aún no hay datos suficientes para mostrar esta medida.";

const FAMILY_BAND_TONE: Record<FamilyBand, "success" | "warning"> = {
  verde: "success",
  ambar: "warning",
};

export function FamilyBodyCompositionCard({ summary }: FamilyBodyCompositionCardProps) {
  const hasData = summary?.has_data ?? false;

  return (
    <Card data-testid="family-body-composition-card">
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center gap-1">
          <p className="text-sm text-mid-gray">Composición corporal</p>
          <Tooltip>
            <TooltipTrigger asChild>
              {/*
                Área táctil de 48×48 (constitution III) con márgenes
                negativos, mismo patrón que `FamilyBandCards.tsx::BandCard`.
              */}
              <button
                type="button"
                aria-label="Más información sobre Composición corporal"
                className="-m-3.5 inline-flex h-12 w-12 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                <Info size={13} aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">
              Suma de pliegues cutáneos tomada por el entrenador; se muestra solo como banda
            </TooltipContent>
          </Tooltip>
        </div>

        {hasData && summary?.family_band && summary.family_label ? (
          <>
            <StatusBadge
              status={FAMILY_BAND_TONE[summary.family_band]}
              label={summary.family_label}
            />
            {summary.family_sentence && (
              <p className="text-sm text-mid-gray">{summary.family_sentence}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-mid-gray">{NO_DATA_MESSAGE}</p>
        )}
      </CardContent>
    </Card>
  );
}
