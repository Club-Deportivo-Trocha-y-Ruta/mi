/**
 * HeroLastInsightCard — muestra el último análisis aprobado del atleta
 * en formato hero (sin truncar) dentro del tab Panorama.
 *
 * Privacidad Ley 1581:
 *   - Badge de confidence SOLO en mode="coach".
 *   - Empty state con copy diferenciado por rol.
 *   - No expone metadatos operativos (tokens, costo, prompts).
 */
import { BookmarkPlus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

interface HeroLastInsightCardProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
  onOpenDetail: (id: number) => void;
  onAddToNewsletter: (id: number) => void;
}

export function HeroLastInsightCard({
  athlete,
  mode,
  onOpenDetail,
  onAddToNewsletter,
}: HeroLastInsightCardProps) {
  const insightQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });

  // ---- Loading state -------------------------------------------------------
  if (insightQuery.isLoading) {
    return (
      <div
        className="rounded-xl bg-white p-5"
        style={{ boxShadow: cardShadow }}
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
        className="rounded-xl bg-white p-5 text-center"
        style={{ boxShadow: cardShadow }}
        data-testid="hero-last-insight-card"
      >
        <p className="text-sm font-medium text-charcoal">
          {mode === "parent"
            ? "Cuando se aprueben análisis de tu hijo, aparecerán aquí."
            : "Aún no hay análisis aprobados. Lanza el primero desde la pestaña 'Lanzar'."}
        </p>
      </div>
    );
  }

  // ---- Contenido del insight -----------------------------------------------
  const isV2 = insight.prompt_version === PROMPT_VERSION_V2;
  const displayText = isV2
    ? extractSection(insight.summary_text, "Qué pasó") || insight.summary_text
    : insight.summary_text;

  return (
    <div
      className="rounded-xl bg-white p-5"
      style={{ boxShadow: cardShadow }}
      data-testid="hero-last-insight-card"
    >
      {/* Meta: fecha + badges */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
          {formatDateTimeCompact(insight.generated_at)}
        </span>
        <Badge variant="secondary">{validaLabel(insight.valida_num)}</Badge>
        {mode === "coach" && (
          <Badge variant={confidenceVariant(insight.confidence)}>
            {confidenceLabel(insight.confidence)}
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
          onClick={() => onOpenDetail(insight.id)}
          data-testid="hero-btn-reread"
        >
          Releer último
        </Button>
        {mode === "coach" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onAddToNewsletter(insight.id)}
            data-testid="hero-btn-add-newsletter"
          >
            <BookmarkPlus size={14} className="mr-1.5" aria-hidden="true" />
            Agregar al boletín
          </Button>
        )}
      </div>
    </div>
  );
}
