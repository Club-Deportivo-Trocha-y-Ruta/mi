/**
 * AthleteHomeBlock — Bloque agrupado de cards del home feed para un único
 * atleta (Wave 4).
 *
 * Centraliza la composición de UpcomingSessionCard + LastSessionCard +
 * WeeklySummaryCard para un athleteId concreto. Lo usa
 * `ParentDashboardPage` tanto en el modo "un solo atleta seleccionado"
 * como en el modo "multi-atleta apilado" (en cuyo caso renderiza N
 * bloques, uno por hijo, cada uno con su encabezado).
 *
 * Beneficio: las queries (`useNextSession`, `useLastSession`,
 * `useParentMonthlySummary`) viven aquí — cada bloque tiene su slice
 * propio del cache identificado por athleteId, y si el padre alterna en
 * el switcher, solo el slice del hijo "abandonado" se purga.
 */
import { useMemo } from "react";

import { LastSessionCard } from "@/components/parents/home/LastSessionCard";
import { UpcomingSessionCard } from "@/components/parents/home/UpcomingSessionCard";
import { WeeklySummaryCard } from "@/components/parents/home/WeeklySummaryCard";
import { useLastSession } from "@/hooks/parents/useLastSession";
import { useNextSession } from "@/hooks/parents/useNextSession";
import { useParentMonthlySummary } from "@/api/trainingSessions";
import type { MyAthleteOut } from "@/types/parent.types";

interface AthleteHomeBlockProps {
  athlete: MyAthleteOut;
  /** Si true, antepone un encabezado con el nombre del atleta (modo multi-atleta apilado). */
  showHeader?: boolean;
}

export function AthleteHomeBlock({ athlete, showHeader = false }: AthleteHomeBlockProps) {
  const athleteId = athlete.athlete_id;
  const athleteName = `${athlete.athlete_first_name} ${athlete.athlete_last_name}`.trim();

  const next = useNextSession(athleteId);
  const last = useLastSession(athleteId);

  const monthMeta = useMemo(() => {
    const now = new Date();
    return {
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    };
  }, []);

  const monthLabel = useMemo(
    () =>
      new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" }).format(
        new Date(monthMeta.year, monthMeta.month - 1, 1),
      ),
    [monthMeta],
  );

  const summaryQuery = useParentMonthlySummary(monthMeta.year, monthMeta.month, athleteId);
  const summaryForAthlete = summaryQuery.data?.find((s) => s.athlete_id === athleteId);

  return (
    <section
      className="space-y-3"
      aria-label={showHeader ? `Resumen de ${athleteName}` : undefined}
      data-testid={`athlete-home-block-${athleteId}`}
    >
      {showHeader && (
        <h2
          className="text-base text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          {athleteName}
        </h2>
      )}

      <UpcomingSessionCard
        session={next.data ?? null}
        isLoading={next.isLoading}
        isError={next.isError}
        athleteName={athleteName}
      />

      <LastSessionCard
        session={last.data ?? null}
        isLoading={last.isLoading}
        isError={last.isError}
        athleteId={athleteId}
        athleteName={athlete.athlete_first_name}
      />

      <WeeklySummaryCard
        summary={summaryForAthlete}
        isLoading={summaryQuery.isLoading}
        isError={summaryQuery.isError}
        monthLabel={monthLabel}
        athleteName={athlete.athlete_first_name}
      />
    </section>
  );
}
