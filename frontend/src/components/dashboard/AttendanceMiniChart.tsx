/**
 * AttendanceMiniChart — tarjeta "Asistencia" del Inicio del coach
 * (feature 035, fila C del mockup
 * `specs/035-nav-dashboard-redesign/mockups/Main.dc.html`).
 *
 * Cuatro barras, una por sesión ejecutada reciente con asistencia
 * registrada, con el % de asistencia = (presentes + tardes) / total. Una
 * sola serie y una sola tinta (`--color-primary`): no hay identidad que
 * codificar por color, sólo magnitud, así que no lleva leyenda y el texto
 * (valor y fecha) usa siempre tinta de texto, nunca el color de la barra.
 *
 * Datos: `useTrainingSessions` con `executedSessionsFilters()` — los MISMOS
 * filtros que consume `WeekStrip` para los días ya pasados de la semana, así
 * que ambas tarjetas comparten una única entrada de cache de TanStack Query
 * (misma queryKey) en vez de disparar dos requests.
 *
 * Estados (misma disciplina de resiliencia que el resto del Inicio,
 * feature 031):
 *   - cargando o cold start (`isColdStartError`) → esqueletos, nunca tono de
 *     error;
 *   - error real → la tarjeta se renderiza igual, con una línea neutra que
 *     dice que no se pudo cargar; nunca la copy de "no hay datos", que
 *     afirmaría como hecho algo que no se sabe;
 *   - menos de una sesión con asistencia registrada → estado vacío propio.
 *
 * Accesibilidad: el gráfico es decorativo para lectores de pantalla
 * (`aria-hidden`) y el equivalente textual —fecha + porcentaje de cada
 * sesión— viaja en un resumen `sr-only`, para no leer dos listas sueltas de
 * números sin relación entre sí.
 *
 * Privacidad: sólo agregados por sesión — ningún nombre ni dato de menores.
 */
import { useId, type ReactNode } from "react";

import { useTrainingSessions } from "@/api/trainingSessions";
import { clubNoon, executedSessionsFilters } from "@/components/dashboard/WeekStrip";
import { isColdStartError } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDayMonthShort } from "@/lib/datetime";
import type { TrainingSession } from "@/types/trainingSession.types";

/** Sesiones mostradas (las más recientes), per mockup. */
const MAX_BARS = 4;

/** Alto en píxeles de una barra al 100% — el resto escala proporcional. */
const BAR_MAX_PX = 64;

interface AttendanceBar {
  id: number;
  dateLabel: string;
  pct: number;
}

/** % de asistencia de una sesión: presentes + tardes sobre el total convocado. */
function attendancePct(session: TrainingSession): number | null {
  const summary = session.attendance_summary;
  if (!summary || summary.total <= 0) return null;
  return Math.round(((summary.presentes + summary.tardes) / summary.total) * 100);
}

function selectBars(sessions: TrainingSession[] | undefined): AttendanceBar[] {
  if (!sessions || sessions.length === 0) return [];

  return sessions
    .filter((s) => s.status === "executed" && attendancePct(s) !== null)
    .sort((a, b) => {
      const dateCmp = a.scheduled_date.localeCompare(b.scheduled_date);
      if (dateCmp !== 0) return dateCmp;
      return a.scheduled_start_time.localeCompare(b.scheduled_start_time);
    })
    // Las últimas 4, en orden cronológico (la más reciente a la derecha).
    .slice(-MAX_BARS)
    .map((s) => ({
      id: s.id,
      dateLabel: formatDayMonthShort(clubNoon(s.scheduled_date)),
      pct: attendancePct(s) as number,
    }));
}

function CardShell({
  headingId,
  children,
}: {
  headingId: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-2 rounded-xl bg-white px-5 py-4 shadow-card"
    >
      <div className="flex flex-col gap-0.5">
        <h2 id={headingId} className="text-[15px] font-semibold text-charcoal">
          Asistencia
        </h2>
        <p className="text-xs text-mid-gray">Últimas {MAX_BARS} sesiones</p>
      </div>
      {children}
    </section>
  );
}

export function AttendanceMiniChart() {
  const headingId = useId();
  const query = useTrainingSessions(executedSessionsFilters());

  // Cold start (Render Free despertando) muestra el mismo esqueleto que
  // loading, nunca un tono de error (FR-008, feature 031).
  if (query.isLoading || (query.isError && isColdStartError(query.error))) {
    return (
      <CardShell headingId={headingId}>
        <div
          className="flex flex-col gap-2 pt-2"
          role="status"
          aria-busy="true"
          aria-label="Cargando asistencia"
        >
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      </CardShell>
    );
  }

  // Un error real (ya descartado el cold start) NO puede colapsarse en el
  // estado vacío: decirle al coach "aún no hay sesiones con asistencia" es
  // afirmar un hecho falso cuando lo que pasó es que los datos no cargaron.
  // Misma línea neutra que `WeekStrip` para el mismo fallo.
  if (query.isError) {
    return (
      <CardShell headingId={headingId}>
        <p className="text-sm text-mid-gray">No se pudo cargar la asistencia.</p>
      </CardShell>
    );
  }

  const bars = selectBars(query.data);

  if (bars.length === 0) {
    return (
      <CardShell headingId={headingId}>
        <p className="text-sm text-charcoal">Aún no hay sesiones con asistencia registrada</p>
      </CardShell>
    );
  }

  return (
    <CardShell headingId={headingId}>
      <div aria-hidden="true">
        <div className="flex items-end gap-3 px-1" style={{ minHeight: BAR_MAX_PX + 20 }}>
          {bars.map((bar) => (
            <div key={bar.id} className="flex flex-1 flex-col items-center gap-1">
              <span className="text-[11px] text-text-secondary">{bar.pct} %</span>
              <div
                className="w-6 rounded-t-[4px] bg-primary"
                style={{ height: Math.max(3, Math.round((bar.pct / 100) * BAR_MAX_PX)) }}
              />
            </div>
          ))}
        </div>
        <div className="flex gap-3 border-t border-border-gray px-1 pt-1">
          {bars.map((bar) => (
            <span key={bar.id} className="flex-1 text-center text-[11px] text-mid-gray">
              {bar.dateLabel}
            </span>
          ))}
        </div>
      </div>

      {/* Equivalente textual del gráfico (el gráfico va aria-hidden). */}
      <p className="sr-only">
        Asistencia por sesión:{" "}
        {bars.map((bar) => `${bar.dateLabel}, ${bar.pct} %`).join("; ")}.
      </p>
    </CardShell>
  );
}
