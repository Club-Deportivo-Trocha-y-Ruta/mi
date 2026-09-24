import { getSkinfoldSiteDiagram, type SkinfoldSite } from "@/lib/bodyComposition/siteDiagrams";
import { SITE_ILLUSTRATION_SIZE, getSiteIllustration } from "@/lib/bodyComposition/siteIllustrations";
import { cn } from "@/lib/utils";

/**
 * SkinfoldSiteDiagram — ilustración de un sitio de pliegue cutáneo
 * (feature 046, T024).
 *
 * Renderiza siempre el `.webp` del sitio (`lib/bodyComposition/siteIllustrations.ts`)
 * con el `alt` de `siteDiagrams.ts`; no hay respaldo vectorial — un `.webp`
 * faltante rompe el build (imports estáticos en `siteIllustrations.ts`).
 *
 * `lib/bodyComposition/siteDiagrams.ts` es la única fuente de verdad del texto
 * (ver ese archivo). Los mismos textos alimentan el instructivo en PDF
 * (`backend/app/data/skinfold_sites.json`, T056) — cualquier ajuste debe
 * hacerse en `siteDiagrams.ts`, nunca aquí.
 *
 * El contenedor es cuadrado y ocupa el ancho que le dé el padre (`className`),
 * y el `<img>` lleva `width`/`height` intrínsecos, así el navegador reserva el
 * espacio antes de decodificar y no hay salto de layout. La imagen tiene fondo
 * blanco: el contenedor también, para que en tema oscuro no se vea recortada.
 * La insignia "D" (lado derecho, convención del protocolo) se superpone como
 * HTML sobre la imagen; su texto accesible es "Lado derecho".
 */
export interface SkinfoldSiteDiagramProps {
  site: SkinfoldSite;
  className?: string;
}

const FRAME_CLASS = "relative aspect-square w-full overflow-hidden rounded-card shadow-card ring-1 ring-hairline";

export function SkinfoldSiteDiagram({ site, className }: SkinfoldSiteDiagramProps) {
  const spec = getSkinfoldSiteDiagram(site);
  const illustration = getSiteIllustration(site);

  return (
    <div className={cn(FRAME_CLASS, "bg-white", className)}>
      <img
        src={illustration}
        alt={spec.alt}
        width={SITE_ILLUSTRATION_SIZE}
        height={SITE_ILLUSTRATION_SIZE}
        loading="eager"
        decoding="async"
        className="size-full object-contain"
      />
      <span
        role="img"
        aria-label="Lado derecho"
        className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-full bg-surface-dark text-sm font-bold text-white"
      >
        <span aria-hidden="true">{spec.sideTag}</span>
      </span>
    </div>
  );
}
