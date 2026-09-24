import { Maximize2 } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  computeSiteValue,
  isPlausible,
  needsThirdReading,
} from "@/lib/bodyComposition/readings";
import { getSkinfoldSiteDiagram } from "@/lib/bodyComposition/siteDiagrams";
import type { SkinfoldWizardFormValues } from "@/schemas/bodyComposition.schema";
import type { SkinfoldSite } from "@/types/bodyComposition.types";

import { SkinfoldSiteDiagram } from "./SkinfoldSiteDiagram";

/** Valor de un sitio dentro del formulario del wizard (T014). */
export type SkinfoldSiteStepValue = SkinfoldWizardFormValues["sites"][SkinfoldSite];

const SITE_LABEL_ES: Record<SkinfoldSite, string> = {
  triceps: "Tríceps",
  biceps: "Bíceps",
  subscapular: "Subescapular",
  medial_calf: "Pantorrilla medial",
  iliac_crest: "Cresta ilíaca",
  supraspinale: "Supraespinal",
};

/**
 * SkinfoldSiteStep — paso de captura de un sitio de pliegue cutáneo dentro
 * del asistente (feature 046, T026).
 *
 * Puramente controlado: `SkinfoldWizard` (T028) es dueño del estado RHF y
 * decide cuándo avanzar — este componente sólo refleja `value` y notifica
 * cambios vía `onChange`/`onSkip`. Reglas de negocio (regla de tercera
 * lectura, mediana, rango plausible) viven en `lib/bodyComposition/readings.ts`
 * y son las mismas que usa `SkinfoldReviewStep` (T027) y el backend
 * (`app/services/body_composition.py`) — nunca se reimplementan aquí.
 */
export interface SkinfoldSiteStepProps {
  site: SkinfoldSite;
  /** Edad del deportista en años, para el rango plausible por sitio. */
  ageYears: number;
  /** Valor actual de este sitio en el formulario del wizard. */
  value: SkinfoldSiteStepValue;
  /** Se dispara con el valor actualizado en cada cambio de lectura. */
  onChange: (value: SkinfoldSiteStepValue) => void;
  /**
   * "Omitir este sitio": marca `{declined: true}` y avanza. El componente
   * no decide el avance — sólo notifica; `SkinfoldWizard` arma el valor
   * declinado y mueve el paso.
   */
  onSkip: () => void;
  /** Texto de posición, p. ej. "Sitio 2 de 6" — puramente informativo. */
  stepLabel?: string;
}

function readingsOf(value: SkinfoldSiteStepValue): number[] {
  return value.declined ? [] : value.readings;
}

export function SkinfoldSiteStep({
  site,
  ageYears,
  value,
  onChange,
  onSkip,
  stepLabel,
}: SkinfoldSiteStepProps) {
  const headingId = useId();
  const spec = getSkinfoldSiteDiagram(site);
  const readings = readingsOf(value);

  // Campos de texto controlados: se guardan como string para permitir un
  // input vacío o parcial ("8." mientras el atleta escribe) sin forzar un
  // número inválido en el estado del formulario.
  const [reading1Text, setReading1Text] = useState(
    readings[0] !== undefined ? String(readings[0]) : "",
  );
  const [reading2Text, setReading2Text] = useState(
    readings[1] !== undefined ? String(readings[1]) : "",
  );
  const [reading3Text, setReading3Text] = useState(
    readings[2] !== undefined ? String(readings[2]) : "",
  );

  const reading1 = reading1Text === "" ? null : Number(reading1Text);
  const reading2 = reading2Text === "" ? null : Number(reading2Text);
  const reading3 = reading3Text === "" ? null : Number(reading3Text);

  const showThirdReading =
    reading1 !== null &&
    reading2 !== null &&
    !Number.isNaN(reading1) &&
    !Number.isNaN(reading2) &&
    needsThirdReading(reading1, reading2);

  function isValid(v: number | null): v is number {
    return v !== null && !Number.isNaN(v);
  }

  /**
   * Notifica siempre las lecturas válidas actuales, aunque sean menos de dos:
   * así el formulario nunca conserva un par anterior que ya no está en
   * pantalla (el wizard valida `min(2)` con `trigger()` antes de avanzar).
   * La tercera lectura sólo viaja cuando la regla de tolerancia la exige
   * para las dos primeras lecturas *actuales*.
   */
  function emit(nextReading1: number | null, nextReading2: number | null, nextReading3: number | null) {
    const thirdApplies =
      isValid(nextReading1) && isValid(nextReading2) && needsThirdReading(nextReading1, nextReading2);
    const readingsList = [nextReading1, nextReading2, thirdApplies ? nextReading3 : null].filter(isValid);
    onChange({ declined: false, readings: readingsList });
  }

  function handleReading1Change(text: string) {
    setReading1Text(text);
    emit(text === "" ? null : Number(text), reading2, reading3);
  }

  function handleReading2Change(text: string) {
    setReading2Text(text);
    emit(reading1, text === "" ? null : Number(text), reading3);
  }

  function handleReading3Change(text: string) {
    setReading3Text(text);
    emit(reading1, reading2, text === "" ? null : Number(text));
  }

  const siteValue = useMemo(() => {
    const validReadings = [reading1, reading2, showThirdReading ? reading3 : null].filter(
      (v): v is number => v !== null && !Number.isNaN(v),
    );
    if (validReadings.length < 2) return null;
    return computeSiteValue(validReadings);
  }, [reading1, reading2, reading3, showThirdReading]);

  const plausible = siteValue === null ? true : isPlausible(site, ageYears, siteValue);

  function handleSkip() {
    setReading1Text("");
    setReading2Text("");
    setReading3Text("");
    onChange({ declined: true });
    onSkip();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          {stepLabel ? <p className="text-xs uppercase tracking-wide text-mid-gray">{stepLabel}</p> : null}
          <h2 id={headingId} className="text-lg font-semibold text-charcoal">
            {SITE_LABEL_ES[site]}
          </h2>
        </div>
        <Button type="button" variant="secondary" size="lg" onClick={handleSkip}>
          Omitir este sitio
        </Button>
      </div>

      <div className="flex flex-col gap-4 md:flex-row md:items-start md:gap-6">
        <Dialog>
          <div className="relative mx-auto w-full max-w-80 md:mx-0 md:size-64 md:max-w-none md:shrink-0">
            <SkinfoldSiteDiagram site={site} />
            {/* Botón transparente sobre la imagen: toda la ilustración es el
                objetivo táctil (≥ 240 px) sin envolver el <img>, así conserva
                su alt como imagen propia. */}
            <DialogTrigger asChild>
              <button
                type="button"
                aria-label={`Ampliar la ilustración de ${SITE_LABEL_ES[site]}`}
                className="absolute inset-0 rounded-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              />
            </DialogTrigger>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute bottom-2 right-2 flex size-8 items-center justify-center rounded-full bg-surface-dark/80 text-white"
            >
              <Maximize2 size={16} />
            </span>
          </div>
          <DialogContent className="max-h-[92dvh] w-[calc(100%-2rem)] max-w-xl overflow-y-auto" hideClose>
            <DialogHeader>
              <DialogTitle>{SITE_LABEL_ES[site]}</DialogTitle>
              <DialogDescription>{spec.donde}</DialogDescription>
            </DialogHeader>
            <DialogBody>
              <SkinfoldSiteDiagram site={site} className="mx-auto max-w-[min(100%,60dvh)]" />
            </DialogBody>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="secondary" size="lg">
                  Cerrar
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <div className="flex flex-1 flex-col gap-3 text-sm">
          <div>
            <p className="font-medium text-charcoal">Dónde</p>
            <p className="text-mid-gray">{spec.donde}</p>
          </div>
          <div>
            <p className="font-medium text-charcoal">Cómo</p>
            <p className="text-mid-gray">{spec.como}</p>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row">
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-sm font-medium text-charcoal">Primera lectura (mm)</span>
          <Input
            type="number"
            inputMode="decimal"
            step="0.5"
            min={2}
            max={60}
            value={reading1Text}
            onChange={(e) => handleReading1Change(e.target.value)}
            aria-label="Primera lectura (mm)"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-sm font-medium text-charcoal">Segunda lectura (mm)</span>
          <Input
            type="number"
            inputMode="decimal"
            step="0.5"
            min={2}
            max={60}
            value={reading2Text}
            onChange={(e) => handleReading2Change(e.target.value)}
            aria-label="Segunda lectura (mm)"
          />
        </label>
      </div>

      {showThirdReading ? (
        <div className="flex flex-col gap-2">
          <p role="status" className="text-sm font-medium text-amber-700">
            Diferencia mayor a lo esperado: toma una tercera lectura
          </p>
          <label className="flex max-w-[50%] flex-col gap-1">
            <span className="text-sm font-medium text-charcoal">Tercera lectura (mm)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="0.5"
              min={2}
              max={60}
              value={reading3Text}
              onChange={(e) => handleReading3Change(e.target.value)}
              aria-label="Tercera lectura (mm)"
            />
          </label>
        </div>
      ) : null}

      <div className="rounded-control bg-light-gray p-4 text-sm">
        <div className="flex justify-between">
          <span className="text-charcoal">Valor del sitio</span>
          <span className="font-semibold text-charcoal">
            {siteValue === null ? "—" : `${siteValue.toFixed(1)} mm`}
          </span>
        </div>
        {siteValue !== null && !plausible ? (
          <p role="status" className="mt-2 text-amber-700">
            ¿Seguro? Ese valor es alto/bajo para este pliegue.
          </p>
        ) : null}
      </div>
    </div>
  );
}
