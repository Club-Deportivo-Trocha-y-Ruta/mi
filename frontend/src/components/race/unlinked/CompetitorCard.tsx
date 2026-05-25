/**
 * CompetitorCard — card de un competitor sin enlazar.
 *
 * Encapsula:
 *  - Header con nombre/club/temporadas/results_count.
 *  - Menú overflow "Desvincular" (visible si results_count > 0).
 *  - Grid de sugerencias (SuggestionCard x3).
 *  - Buscador manual con AthleteCombobox.
 *
 * Extraído de UnlinkedCompetitorsTab en B5.
 */
import { useState } from "react";
import {
  Calendar,
  Link2,
  Loader2,
  MoreVertical,
  Search,
  TrophyIcon,
  Unlink,
  X,
} from "lucide-react";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import type { UnlinkedCompetitorItem } from "@/types/raceCompetitors.types";
import { SuggestionCard } from "./SuggestionCard";

export interface CompetitorCardProps {
  competitor: UnlinkedCompetitorItem;
  onLink: (
    competitorId: number,
    athleteId: number,
    competitor: UnlinkedCompetitorItem,
  ) => void;
  onUnlink: (competitor: UnlinkedCompetitorItem) => void;
  isLinkingThis: boolean;
  linkingAthleteId: number | null;
}

export function CompetitorCard({
  competitor,
  onLink,
  onUnlink,
  isLinkingThis,
  linkingAthleteId,
}: CompetitorCardProps) {
  const [showManual, setShowManual] = useState(false);
  const [manualAthleteId, setManualAthleteId] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // Si results_count > 0 y el listado lo devolvió en `unlinked=true`, el
  // competitor está pendiente. Mantenemos el botón "Desvincular" disponible
  // sólo si existe (en este flow R1 no debería estar enlazado, pero por
  // robustez ante refetch lo dejamos en menú overflow).
  const showUnlinkMenu = competitor.results_count > 0;

  return (
    <article
      data-testid={`competitor-card-${competitor.id}`}
      className="space-y-3 rounded-xl bg-white p-4 shadow-ring"
    >
      {/* Header */}
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h3
            className="truncate text-sm text-charcoal font-heading"
            title={competitor.display_name}
          >
            {competitor.display_name}
          </h3>
          <div className="flex flex-wrap items-center gap-1.5">
            {competitor.club_text && (
              <span
                className="inline-flex max-w-[180px] items-center rounded-full bg-light-gray/70 px-2 py-0.5 text-[10px] font-medium text-charcoal"
                title={competitor.club_text}
              >
                <span className="truncate">{competitor.club_text}</span>
              </span>
            )}
            {competitor.sex && (
              <span className="inline-flex items-center rounded-full bg-light-gray/70 px-2 py-0.5 text-[10px] font-semibold text-mid-gray">
                {competitor.sex}
              </span>
            )}
            {competitor.seasons.map((season) => (
              <span
                key={season}
                className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700"
              >
                <Calendar size={10} aria-hidden="true" />
                {season}
              </span>
            ))}
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              <TrophyIcon size={10} aria-hidden="true" />
              {competitor.results_count} resultado
              {competitor.results_count === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {showUnlinkMenu && (
          <div className="relative shrink-0">
            <button
              type="button"
              aria-label="Más acciones"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              data-testid={`competitor-${competitor.id}-overflow`}
              onClick={() => setMenuOpen((v) => !v)}
              onBlur={() => setTimeout(() => setMenuOpen(false), 120)}
              className="rounded-md p-1 text-mid-gray transition-colors hover:bg-light-gray focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
            >
              <MoreVertical size={14} aria-hidden="true" />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full z-30 mt-1 min-w-[180px] rounded-lg bg-white py-1 shadow-lg ring-1 ring-light-gray"
                data-testid={`competitor-${competitor.id}-menu`}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    onUnlink(competitor);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-red-700 transition-colors hover:bg-red-50"
                >
                  <Unlink size={12} aria-hidden="true" />
                  Desvincular
                </button>
              </div>
            )}
          </div>
        )}
      </header>

      {/* Sugerencias */}
      {competitor.suggestions.length > 0 ? (
        <section
          aria-label="Sugerencias de atletas"
          className="grid gap-2 sm:grid-cols-3"
        >
          {competitor.suggestions.map((s, idx) => (
            <SuggestionCard
              key={s.athlete_id}
              suggestion={s}
              testId={`competitor-${competitor.id}-suggestion-${idx}`}
              isLinking={isLinkingThis && linkingAthleteId === s.athlete_id}
              onLink={(athleteId) => onLink(competitor.id, athleteId, competitor)}
            />
          ))}
        </section>
      ) : (
        <p className="rounded-lg bg-light-gray/40 px-3 py-2 text-xs text-mid-gray">
          Sin sugerencias automáticas. Usa el buscador manual.
        </p>
      )}

      {/* Buscador manual */}
      <div className="space-y-2 border-t border-[rgba(34,42,53,0.06)] pt-3">
        {!showManual ? (
          <button
            type="button"
            data-testid={`competitor-${competitor.id}-manual-btn`}
            onClick={() => setShowManual(true)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-700 transition-colors hover:text-blue-800"
          >
            <Search size={12} aria-hidden="true" />
            Buscar otro atleta
          </button>
        ) : (
          <div className="space-y-2">
            <AthleteCombobox
              value={manualAthleteId}
              onChange={setManualAthleteId}
              placeholder="Selecciona un atleta del club"
              data-testid={`competitor-${competitor.id}-manual-combobox`}
              label="Atleta manual"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={manualAthleteId == null || isLinkingThis}
                data-testid={`competitor-${competitor.id}-manual-confirm`}
                onClick={() => {
                  if (manualAthleteId != null) {
                    onLink(competitor.id, manualAthleteId, competitor);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLinkingThis ? (
                  <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Link2 size={12} aria-hidden="true" />
                )}
                Enlazar
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowManual(false);
                  setManualAthleteId(null);
                }}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-mid-gray transition-colors hover:bg-light-gray"
              >
                <X size={12} aria-hidden="true" />
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
