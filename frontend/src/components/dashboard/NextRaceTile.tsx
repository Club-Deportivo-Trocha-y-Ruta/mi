/**
 * NextRaceTile — hero tile "Próxima carrera Copa Valle" del Inicio del
 * coach (feature 031, US1, Tile 2 de `contracts/home-tiles.md`).
 *
 * Consume `useRaceEventsList({ season: currentSeason() })` (mismo fetch que
 * `PendingInbox`'s "Resultados por importar" — sin requests duplicados,
 * research.md R2) y selecciona el primer evento con `event_date >= hoy`
 * (zona horaria del club). El estado de urgencia (neutral/upcoming/
 * in_window) sale de `getCarreraTier` + `TAPER_GUIDANCE` (`lib/insights.ts`,
 * T024) comparando `daysUntil` contra los umbrales exactos por tier
 * (`warningAt`/`dangerAt`) — ya alineados con
 * `contracts/home-tiles.md`: A/CD → warning ≤10d, danger ≤7d;
 * B → warning ≤6d, danger ≤4d; C → siempre neutral.
 *
 * Estado vacío de fin de temporada: se muestra en texto plano vía
 * `EmptyState` sin acción (no hay "crear carrera" — el calendario Copa
 * Valle es fijo), distinto del loading (`undefined`).
 *
 * Privacidad: solo nombre/fecha/lugar de la carrera — sin resultados ni
 * nombres de atletas (contracts/home-tiles.md).
 *
 * Feature 035 (rediseño del Inicio) suma dos elementos al estado resuelto,
 * ambos derivados de datos que la tile ya tenía en mano — sin queries ni
 * lógica de urgencia nuevas: la insignia "Clase A/B/C" (`getCarreraTier`) y
 * la línea de guía de tapering (`TAPER_GUIDANCE`, que antes viajaba
 * comprimida dentro del hint junto a día y lugar).
 */
import { CalendarClock } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { TAPER_GUIDANCE, getCarreraTier, type TaperGuidance } from "@/lib/insights";
import { currentSeason, diffDaysFromToday, formatRelativeDayCount } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { RaceEventListItem } from "@/types/raceEvents.types";

type Urgency = "neutral" | "upcoming" | "in_window";

type CarreraTier = "A" | "B" | "C";

/**
 * Tinte 10% + borde 30% del token ordinal del tier (`--color-tier-a/-b/-c`,
 * feature 033) — el color acompaña al texto "Clase A/B/C", nunca lo
 * reemplaza. Se usan las utilidades de color del `@theme` (`bg-tier-a/10`) y
 * NO la forma `bg-[--color-tier-a]/10` de `InsightsTimeline.tsx`: Tailwind
 * v4 la compila a `color-mix(in oklab, --color-tier-a …)` —sin `var()`—, una
 * declaración inválida que el navegador descarta.
 */
const TIER_CHIP_CLASSES: Record<CarreraTier, string> = {
  A: "border-tier-a/30 bg-tier-a/10",
  B: "border-tier-b/30 bg-tier-b/10",
  C: "border-tier-c/30 bg-tier-c/10",
};

const TIER_DOT_CLASSES: Record<CarreraTier, string> = {
  A: "bg-tier-a",
  B: "bg-tier-b",
  C: "bg-tier-c",
};

const URGENCY_TONE: Record<Urgency, Status> = {
  neutral: "neutral",
  upcoming: "warning",
  in_window: "danger",
};

const URGENCY_LABEL: Record<Exclude<Urgency, "neutral">, string> = {
  upcoming: "Se acerca la ventana de tapering",
  in_window: "En ventana de tapering",
};

function resolveUrgency(daysUntil: number, warningAt: number | null, dangerAt: number | null): Urgency {
  if (warningAt === null || dangerAt === null) return "neutral";
  if (daysUntil <= dangerAt) return "in_window";
  if (daysUntil <= warningAt) return "upcoming";
  return "neutral";
}

/**
 * Línea de guía de tapering del tier, armada con el copy real de
 * `TAPER_GUIDANCE` (`lib/insights.ts`): la etiqueta del tier + su ventana
 * `taperDays`. Un tier sin ventana (`taperDays: null`, la diagnóstica C) lo
 * dice explícitamente en vez de mostrar un rango vacío.
 */
function taperHint(guidance: TaperGuidance): string {
  if (!guidance.taperDays) {
    return `${guidance.label} · sin ventana de tapering`;
  }
  const [min, max] = guidance.taperDays;
  return `${guidance.label} · ${min}–${max} días`;
}

function TierChip({ tier }: { tier: CarreraTier }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium text-charcoal",
        TIER_CHIP_CLASSES[tier],
      )}
    >
      <span
        className={cn("h-2 w-2 shrink-0 rounded-full", TIER_DOT_CLASSES[tier])}
        aria-hidden="true"
      />
      Clase {tier}
    </span>
  );
}

function selectNextRace(items: RaceEventListItem[]): RaceEventListItem | null {
  const upcoming = items
    .filter((item) => {
      const days = diffDaysFromToday(item.event_date);
      return days !== null && days >= 0;
    })
    .sort((a, b) => (a.event_date < b.event_date ? -1 : a.event_date > b.event_date ? 1 : 0));
  return upcoming[0] ?? null;
}

export function NextRaceTile() {
  const query = useRaceEventsList({ season: currentSeason() });

  if (query.isLoading) {
    return <StatCard label="Próxima carrera Copa Valle" value="" isLoading />;
  }

  if (query.isError) {
    // Cold start (Render Free despertando) muestra el mismo skeleton que
    // loading, nunca un tono de error (FR-008, contracts/home-tiles.md
    // "Cold start"). Solo un error real muestra ErrorState con reintentar.
    if (isColdStartError(query.error)) {
      return <StatCard label="Próxima carrera Copa Valle" value="" isLoading />;
    }
    return (
      <ErrorState
        message="No se pudo cargar la próxima carrera."
        onRetry={() => void query.refetch()}
      />
    );
  }

  const nextRace = selectNextRace(query.data?.items ?? []);

  if (!nextRace) {
    return (
      <EmptyState icon={CalendarClock} title="Temporada finalizada — sin próximas carreras" />
    );
  }

  const daysUntil = diffDaysFromToday(nextRace.event_date) ?? 0;
  const tier = getCarreraTier(nextRace.event_date);
  const taperGuidance = tier ? TAPER_GUIDANCE[tier] : null;
  const urgency = taperGuidance
    ? resolveUrgency(daysUntil, taperGuidance.warningAt, taperGuidance.dangerAt)
    : "neutral";

  // La guía de tapering ya no viaja en el hint: baja a su propia línea, bajo
  // la insignia de clase (mockup `Main.dc.html`, fila A).
  const hintParts = [formatRelativeDayCount(nextRace.event_date), nextRace.location].filter(
    (part): part is string => Boolean(part && part.length > 0),
  );

  const hasTierBlock = tier !== null && taperGuidance !== null;
  const hasBadgeBlock = hasTierBlock || urgency !== "neutral";

  return (
    <StatCard
      label="Próxima carrera Copa Valle"
      value={nextRace.name}
      hint={hintParts.join(" · ")}
      href={`/competitions/${nextRace.id}`}
      tone={URGENCY_TONE[urgency]}
      badge={
        hasBadgeBlock ? (
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
              {tier && <TierChip tier={tier} />}
              {urgency !== "neutral" && (
                <StatusBadge status={URGENCY_TONE[urgency]} label={URGENCY_LABEL[urgency]} />
              )}
            </div>
            {taperGuidance && (
              <span className="text-xs text-mid-gray">{taperHint(taperGuidance)}</span>
            )}
          </div>
        ) : undefined
      }
    />
  );
}
