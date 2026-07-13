/**
 * WeeklyLoadMeter — Row 1, Tile 3 ("Carga semanal") del Inicio rediseñado
 * del coach (feature 031, US3, `contracts/home-tiles.md` Tile 3 + R6).
 *
 * Consume `useCoachSummary().weekly_load` — dos medidores independientes
 * ("small multiples"), uno por `age_band` presente en la respuesta, cada
 * uno normalizado a 0-100% de SU PROPIO tope (`cap_minutes`), nunca un
 * único bar chart de eje compartido (research.md R6: los topes de 10-12 y
 * 13-15 son distintos — 600 vs 780 min — así que compartir eje haría
 * ilegible "qué tan cerca del tope" está cada banda).
 *
 * Estados por medidor (contracts/home-tiles.md, "Meter state table"):
 *   - comfortable (<=80% del tope) → relleno `--color-primary`.
 *   - near-cap (>80%, <=100%)      → relleno `--color-warning` + copy
 *     "Cerca del tope — revisa antes de agregar más sesiones."
 *   - over-cap (>100%)             → relleno `--color-danger`, la barra
 *     renderiza a ancho completo (NUNCA recortada/desbordada) y el texto
 *     lleva la sobrecarga en minutos/horas, tono asesor y nunca de alarma
 *     (jamás "¡Exceso!").
 *
 * El track de cada estado es un tinte pálido del MISMO hue del relleno
 * (`color-mix(in oklch, var(--color-X) 18%, white)`, research.md R6) — no
 * un gris neutro fijo.
 *
 * Headline en horas decimales ("4 h planificadas" / "10.5 h planificadas")
 * — figura proporcional, sin `tabular-nums` (dataviz "figures" rule; el
 * valor es un titular independiente, no una columna de tabla).
 *
 * Absent (`weekly_load: null`, agregado no disponible) vs. empty
 * (`weekly_load: []`, club sin atletas 10-15) son estados DISTINTOS
 * (contracts/home-tiles.md, Tile 3):
 *   - Absent → la tile se omite por completo (`return null`), nunca un
 *     tono de error — consistente con FR-005 acceptance #3 ("nunca
 *     bloquea el resto del Inicio") y US3 acceptance #3.
 *   - Empty → la tile SÍ se renderiza (mismo contenedor que el resto de
 *     estados), pero en vez de medidores muestra una única línea neutra:
 *     "Sin atletas en edad de seguimiento (10-15 años)."
 *
 * El link "Ver sesiones de esta semana" pre-aplica el `from_date`/`to_date`
 * de la semana ISO actual (lunes-domingo, TZ del club, mismo criterio que
 * `compute_weekly_load` en el backend) al store compartido
 * `useTrainingFiltersStore` (el mismo que `SessionFiltersBar`/
 * `SessionsListPage` ya leen) antes de navegar a `/training/sessions` — no
 * filtra por banda de edad (esa pantalla no tiene ese filtro hoy, fuera de
 * alcance per contracts/home-tiles.md).
 */
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";

import { isColdStartError } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";
import { CLUB_TIMEZONE } from "@/lib/datetime";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import type { WeeklyLoadAgeBand, WeeklyLoadBand } from "@/types/dashboard.types";

type MeterState = "comfortable" | "near_cap" | "over_cap";

const BAND_LABEL: Record<WeeklyLoadAgeBand, string> = {
  "10-12": "10-12 años",
  "13-15": "13-15 años",
};

const STATE_COLOR_VAR: Record<MeterState, string> = {
  comfortable: "--color-primary",
  near_cap: "--color-warning",
  over_cap: "--color-danger",
};

function resolveState(plannedMinutes: number, capMinutes: number): MeterState {
  if (capMinutes <= 0) return "comfortable";
  const pct = (plannedMinutes / capMinutes) * 100;
  if (pct > 100) return "over_cap";
  if (pct > 80) return "near_cap";
  return "comfortable";
}

/** "4 h" / "10.5 h" — horas decimales, sin ceros de más (figura proporcional). */
function formatHours(minutes: number): string {
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours}`;
}

/** "30 min" / "1 h" / "1 h 30 min" — usado para la sobrecarga en over-cap. */
function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/**
 * Lunes-domingo (semana ISO) que contiene "hoy" en `CLUB_TIMEZONE`, como
 * `{from_date, to_date}` en formato "YYYY-MM-DD" — mismo criterio de
 * semana que `backend/app/services/dashboard_summary.py::compute_weekly_load`
 * (`today.weekday()`, lunes=0).
 */
function currentWeekRange(): { from_date: string; to_date: string } {
  const [year, month, day] = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  })
    .format(new Date())
    .split("-")
    .map(Number);
  const today = new Date(year, month - 1, day);
  const isoWeekday = today.getDay() === 0 ? 7 : today.getDay(); // 1=lunes .. 7=domingo
  const monday = new Date(today);
  monday.setDate(today.getDate() - (isoWeekday - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const toIso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  return { from_date: toIso(monday), to_date: toIso(sunday) };
}

function fillColorStyle(colorVar: string): CSSProperties {
  return { backgroundColor: `var(${colorVar})` };
}

function trackTintStyle(colorVar: string): CSSProperties {
  return { backgroundColor: `color-mix(in oklch, var(${colorVar}) 18%, white)` };
}

function MeterBlock({ band }: { band: WeeklyLoadBand }) {
  const state = resolveState(band.planned_minutes, band.cap_minutes);
  const colorVar = STATE_COLOR_VAR[state];
  const fillPct = Math.min((band.planned_minutes / Math.max(band.cap_minutes, 1)) * 100, 100);
  const bandLabel = BAND_LABEL[band.age_band];

  const stateCopy =
    state === "near_cap"
      ? "Cerca del tope — revisa antes de agregar más sesiones."
      : state === "over_cap"
        ? `${formatDuration(band.planned_minutes - band.cap_minutes)} sobre el tope de ${bandLabel}. Revisa el plan de la semana.`
        : null;

  return (
    <div className="space-y-1.5">
      <p className="font-display text-2xl font-semibold text-charcoal">
        {formatHours(band.planned_minutes)} h planificadas
      </p>
      <p className="text-xs text-mid-gray">
        {bandLabel} · tope {formatHours(band.cap_minutes)} h/semana
      </p>
      <div
        className="h-2 w-full overflow-hidden rounded-full"
        style={trackTintStyle(colorVar)}
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${fillPct}%`, ...fillColorStyle(colorVar) }}
        />
      </div>
      {stateCopy && <p className="text-xs text-charcoal">{stateCopy}</p>}
    </div>
  );
}

export function WeeklyLoadMeter() {
  const query = useCoachSummary();
  const setFromDate = useTrainingFiltersStore((s) => s.setFromDate);
  const setToDate = useTrainingFiltersStore((s) => s.setToDate);

  if (query.isLoading) {
    return (
      <div className="space-y-3 rounded-xl bg-white p-4 shadow-card" role="status" aria-busy="true" aria-label="Cargando carga semanal">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-2 w-full" />
      </div>
    );
  }

  if (query.isError) {
    // Cold start (Render Free despertando) muestra el mismo esqueleto que
    // loading, nunca un tono de error (FR-008). Un error real degrada
    // igual que el agregado ausente: la tile se omite por completo, nunca
    // bloquea el resto del Inicio (FR-005 acceptance #3).
    if (isColdStartError(query.error)) {
      return (
        <div className="space-y-3 rounded-xl bg-white p-4 shadow-card" role="status" aria-busy="true" aria-label="Cargando carga semanal">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-2 w-full" />
        </div>
      );
    }
    return null;
  }

  const bands = query.data?.weekly_load;

  // Absent (agregado no disponible): la tile se omite por completo, nunca
  // un tono de error (FR-005 acceptance #3, US3 acceptance #3).
  if (bands === null || bands === undefined) return null;

  // Empty (club sin atletas 10-15): la tile SÍ se renderiza, con una única
  // línea neutra en vez de medidores (contracts/home-tiles.md Tile 3).
  if (bands.length === 0) {
    return (
      <div className="space-y-2 rounded-xl bg-white p-4 shadow-card">
        <p className="text-sm text-mid-gray">Carga semanal</p>
        <p className="text-sm text-charcoal">Sin atletas en edad de seguimiento (10-15 años)</p>
      </div>
    );
  }

  function handleGoToCurrentWeek() {
    const { from_date, to_date } = currentWeekRange();
    setFromDate(from_date);
    setToDate(to_date);
  }

  return (
    <div className="space-y-4 rounded-xl bg-white p-4 shadow-card">
      <p className="text-sm text-mid-gray">Carga semanal</p>

      {bands.map((band, idx) => (
        <div
          key={band.age_band}
          style={idx > 0 ? { borderTop: "1px solid rgba(34, 42, 53, 0.06)", paddingTop: "1rem" } : undefined}
        >
          <MeterBlock band={band} />
        </div>
      ))}

      <Link
        to="/training/sessions"
        onClick={handleGoToCurrentWeek}
        className="inline-block min-h-12 text-sm font-medium text-primary underline transition-opacity hover:opacity-70"
      >
        Ver sesiones de esta semana
      </Link>
    </div>
  );
}
