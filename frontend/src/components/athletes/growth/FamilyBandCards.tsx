/**
 * FamilyBandCards — dos tarjetas narrativas para familias (feature 040, US4,
 * T058), per `contracts/growth-tab-ui.md` y `data-model.md` §4: "Estatura
 * para su edad" (talla) y "Peso para su estatura" (IMC, con tooltip que
 * aclara el nombre técnico — decisión D3 de `docs/18-growth-module-redesign/proposal.md`).
 *
 * Cada tarjeta muestra únicamente ícono + etiqueta familiar (`StatusBadge`,
 * nunca la etiqueta clínica del coach) y la frase narrativa del vocabulario
 * de bandas — **nunca** Z-score, percentil ni el nombre técnico de la banda
 * (FR-016: "it MUST NOT show Z-scores, percentiles … clinical headline
 * labels"). Recibe `latest` ya resuelto por `useGrowthSummary` (mismo
 * contrato que `GrowthStatusRow` del lado coach) — no hace fetch ni gestiona
 * loading/error/empty; eso es responsabilidad del contenedor (`GrowthTab`),
 * per la fila "Family cards" de la tabla de estados del contrato.
 *
 * Usa `Card`/`CardContent` (shadcn genérico) en vez de `shared/StatCard`
 * porque la tarjeta de IMC necesita un disparador de tooltip junto al
 * título — `StatCard.label` está tipado como `string` y no acepta un nodo
 * con el ícono de información.
 */
import { Info } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getBandVocabulary } from "@/lib/growth/bands";
import type { BandReading, LatestBands } from "@/types/growth.types";

export interface FamilyBandCardsProps {
  /** `GrowthSummary.latest` — `null` cuando aún no hay mediciones. */
  latest: LatestBands | null;
}

const NO_REFERENCE_MESSAGE = "Aún no hay datos suficientes para mostrar esta medida.";

interface BandCardProps {
  title: string;
  /** Aclaración del nombre técnico — solo la tarjeta de IMC la usa (D3). */
  tooltip?: string;
  reading: BandReading | null;
  indicator: "height_for_age" | "bmi_for_age";
  testId: string;
}

function BandCard({ title, tooltip, reading, indicator, testId }: BandCardProps) {
  return (
    <Card data-testid={testId}>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center gap-1">
          <p className="text-sm text-mid-gray">{title}</p>
          {tooltip && (
            <Tooltip>
              <TooltipTrigger asChild>
                {/*
                  Área táctil de 48×48 (SC-006 / constitution III) con
                  márgenes negativos para que el glifo siga midiendo ~20 px y
                  la fila del título no crezca: el `-m-3.5` deja una huella de
                  20 px en el layout, pero el `hit area` real del botón es de
                  48 px en ambos ejes.
                */}
                <button
                  type="button"
                  aria-label={`Más información sobre ${title}`}
                  className="-m-3.5 inline-flex h-12 w-12 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  <Info size={13} aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">{tooltip}</TooltipContent>
            </Tooltip>
          )}
        </div>

        {reading ? (
          <>
            <StatusBadge
              status={getBandVocabulary(indicator, reading.band).tone}
              label={getBandVocabulary(indicator, reading.band).familyLabel}
            />
            <p className="text-sm text-mid-gray">
              {getBandVocabulary(indicator, reading.band).narrative}
            </p>
          </>
        ) : (
          <p className="text-sm text-mid-gray">{NO_REFERENCE_MESSAGE}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function FamilyBandCards({ latest }: FamilyBandCardsProps) {
  return (
    <div data-testid="family-band-cards" className="grid gap-3 sm:grid-cols-2">
      <BandCard
        testId="family-band-card-height"
        title="Estatura para su edad"
        reading={latest?.height ?? null}
        indicator="height_for_age"
      />
      <BandCard
        testId="family-band-card-bmi"
        title="Peso para su estatura"
        tooltip="Índice de masa corporal para la edad, OMS 2007"
        reading={latest?.bmi ?? null}
        indicator="bmi_for_age"
      />
    </div>
  );
}
