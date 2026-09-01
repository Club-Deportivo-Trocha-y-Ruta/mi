/**
 * HeroLastInsightCard — muestra el último análisis aprobado del atleta
 * en formato hero (sin truncar) dentro del tab Panorama.
 *
 * Privacidad Ley 1581:
 *   - Badge de confidence SOLO en mode="coach".
 *   - Empty state con copy diferenciado por rol.
 *   - No expone metadatos operativos (tokens, costo, prompts).
 */
import { AlertCircle, BookmarkPlus, Info, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  extractSection,
  PROMPT_VERSION_V2,
  validaLabel,
} from "@/lib/insights";
import type { AthleteOut } from "@/types/athlete.types";

interface HeroLastInsightCardProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
  onOpenDetail: (id: number) => void;
  onAddToNewsletter: (id: number) => void;
  /** IDs seleccionados para boletín — cuando se pasa, el botón refleja estado. */
  newsletterSelection?: Set<number>;
  /** Toggle multi-select del boletín (BB4). */
  onToggleSelection?: (id: number) => void;
}

export function HeroLastInsightCard({
  athlete,
  mode,
  onOpenDetail,
  onAddToNewsletter,
  newsletterSelection,
  onToggleSelection,
}: HeroLastInsightCardProps) {
  const insightQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });

  // ---- Loading state -------------------------------------------------------
  if (insightQuery.isLoading) {
    return (
      <div
        className="rounded-xl bg-white p-5 shadow-card"
        data-testid="hero-last-insight-card"
      >
        <Skeleton className="h-4 w-32 mb-3" />
        <Skeleton className="h-[140px] w-full rounded-lg" />
      </div>
    );
  }

  const insight = insightQuery.data?.items[0];

  // ---- Empty state ---------------------------------------------------------
  if (!insight) {
    return (
      <div
        className="rounded-xl bg-white p-5 text-center shadow-card"
        data-testid="hero-last-insight-card"
      >
        <p className="text-sm font-medium text-charcoal">
          {mode === "parent"
            ? "Cuando se aprueben análisis de tu hijo/a, aparecerán aquí."
            : "Aún no hay análisis aprobados. Lanza el primero desde la pestaña 'Analizar con IA'."}
        </p>
      </div>
    );
  }

  // ---- Contenido del insight -----------------------------------------------
  const isV2 = insight.prompt_version === PROMPT_VERSION_V2;
  const displayText = isV2
    ? extractSection(insight.summary_text, "Qué pasó") || insight.summary_text
    : insight.summary_text;
  // Fallback (US4, feature 036): igual que en InsightsTimeline.tsx — una
  // fila persistida por el camino de FALLA de `deterministic_fallback` no
  // es un análisis real y nunca debe ofrecerse para el boletín, ni siquiera
  // desde este card (el guard de verdad es el 422 del backend, pero sin
  // este badge/gate el coach ve el toggle como si hubiera funcionado).
  const isFallback = insight.is_fallback === true;

  return (
    <div
      className="rounded-xl bg-white p-5 shadow-card"
      data-testid="hero-last-insight-card"
    >
      {/* Meta: fecha + badges */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
          {formatDateTimeCompact(insight.generated_at)}
        </span>
        <Badge variant="secondary">
          {validaLabel({ valida_num: insight.valida_num, series_kind: insight.series_kind })}
        </Badge>
        {/* T096c (feature 036, US6): "válida" es jerga del club (una fecha
            de la Copa Valle que cuenta para la tabla de posiciones de la
            temporada) sin explicación en la vista de padres. Se eligió un
            tooltip de primer uso en vez de renombrar la etiqueta a "Carrera
            N" para el rol parent: este mismo histórico ya usa "Carrera A/B/C"
            para el *tier* de dificultad de la carrera (`CarreraTierBadge`,
            `InsightsTimeline.tsx`) — reusar "Carrera" con un segundo
            significado (identidad de la carrera) habría creado una colisión
            de vocabulario nueva. La etiqueta "Válida N" no cambia para
            ningún rol; el helper compartido `validaLabel` (`lib/insights.ts`)
            queda intacto. Un solo punto de explicación basta: Panorama es la
            sub-pestaña por defecto, así que es el primer "Válida N" que ve
            un padre. Patrón calcado de `ParentSessionCard.tsx`'s `InfoIcon`
            (mismo ícono, mismo `TooltipTrigger asChild` + `<button
            aria-label>`); `TooltipProvider` local porque este componente no
            puede asumir que quien lo monte (p. ej. tests con
            `renderWithProviders`) envuelva con el `TooltipProvider` global
            de `App.tsx`. */}
        {mode === "parent" && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="¿Qué es una 'válida'?"
                  data-testid="hero-valida-info-trigger"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                >
                  <Info size={12} aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-64">
                Cada "válida" es una fecha de la Copa Valle. Cuenta para la
                tabla de posiciones de la temporada.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {mode === "coach" && (
          <Badge variant={confidenceVariant(insight.confidence)}>
            {confidenceLabel(insight.confidence)}
          </Badge>
        )}
        {isFallback && (
          <Badge
            variant="outline"
            className="gap-1 border-dashed"
            data-testid="hero-insight-fallback-badge"
          >
            <AlertCircle size={11} aria-hidden="true" />
            Análisis no disponible
          </Badge>
        )}
      </div>

      {/* Contenido completo — sin truncar */}
      <p className="text-sm leading-relaxed text-charcoal whitespace-pre-wrap">
        {displayText}
      </p>

      {/* Acciones */}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="default"
          size="sm"
          className="min-h-12"
          onClick={() => onOpenDetail(insight.id)}
          data-testid="hero-btn-reread"
        >
          Releer último
        </Button>
        {mode === "coach" && !isFallback && (() => {
          // BB4: si hay estado de selección controlado, lo refleja en el botón.
          const isSelectedForNewsletter =
            newsletterSelection !== undefined
              ? newsletterSelection.has(insight.id)
              : false;
          const handleClick = onToggleSelection
            ? () => onToggleSelection(insight.id)
            : () => onAddToNewsletter(insight.id);
          return (
            <Button
              // T097 (feature 036, US6): "Releer último" es la acción
              // primaria de la card (`variant="default"`, turquesa — la
              // marca correcta, no se recolorea: plan.md corrige al audit
              // UX que la marcó como defecto). "Agregar/Quitar del boletín"
              // es la acción secundaria y antes competía con un peso visual
              // similar (outline/secondary son casi tan sólidos como
              // default); "ghost" la demota sin quitarle affordance — el
              // texto ("Agregar"/"Quitar") ya distingue el estado
              // seleccionado sin necesitar un relleno sólido.
              variant="ghost"
              size="sm"
              className="min-h-12"
              onClick={handleClick}
              data-testid="hero-btn-add-newsletter"
            >
              <BookmarkPlus size={14} className="mr-1.5" aria-hidden="true" />
              {isSelectedForNewsletter ? "Quitar del boletín" : "Agregar al boletín"}
            </Button>
          );
        })()}
      </div>

      {/* Link cross-atleta — solo para válidas regulares/CD (no resumen temporada) */}
      {insight.event_id !== null &&
        insight.valida_num !== null &&
        insight.valida_num !== 0 && (
          <Link
            to={`/competitions/${insight.event_id}?tab=insights`}
            // Wave 5 (feature 036, target-size sweep): sin `min-h-12` este
            // link de texto medía 144×16 — la línea de texto sola, sin
            // ningún alto de toque. `min-h-12` en un `inline-flex` con
            // `items-center` crece el hit-area verticalmente sin agrandar
            // el texto ni el ícono (mismo truco que `launch-submit` /
            // `LibraryFilterBar.tsx`'s `<select>`, ver su propio className).
            className="mt-3 inline-flex min-h-12 items-center gap-1 text-xs text-mid-gray underline-offset-2 hover:underline"
            data-testid="hero-link-club-insights"
            onClick={(e) => e.stopPropagation()}
          >
            <Users size={12} aria-hidden="true" />
            Ver club en esta válida
          </Link>
        )}
    </div>
  );
}
