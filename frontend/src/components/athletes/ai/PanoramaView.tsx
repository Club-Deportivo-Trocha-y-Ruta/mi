/**
 * PanoramaView — contenido del sub-tab "Panorama" en AthleteAIAnalysisTab.
 *
 * Sprint 1: solo renderiza HeroLastInsightCard.
 * Sprint 2 añadirá: sparkline de evolución + KPI cards.
 *
 * Privacidad: este componente no filtra por modo — la responsabilidad
 * de privacidad recae en HeroLastInsightCard y en el tab-gating del padre.
 */
import { HeroLastInsightCard } from "./HeroLastInsightCard";
import type { AthleteOut } from "@/types/athlete.types";

interface PanoramaViewProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
  onOpenDetail: (id: number) => void;
  onAddToNewsletter: (id: number) => void;
}

export function PanoramaView({
  athlete,
  mode,
  onOpenDetail,
  onAddToNewsletter,
}: PanoramaViewProps) {
  return (
    <div className="space-y-4" data-testid="panorama-view">
      <HeroLastInsightCard
        athlete={athlete}
        mode={mode}
        onOpenDetail={onOpenDetail}
        onAddToNewsletter={onAddToNewsletter}
      />
    </div>
  );
}
