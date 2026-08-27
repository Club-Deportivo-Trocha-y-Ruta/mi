/**
 * WeekStrip — tarjeta "Semana en curso" del Inicio del coach (feature 035,
 * fila B del mockup `specs/035-nav-dashboard-redesign/mockups/Main.dc.html`).
 *
 * Muestra los 7 días (lunes-domingo) de la semana ISO en curso en
 * `CLUB_TIMEZONE` (America/Bogota, sin horario de verano) con las sesiones
 * de cada día. "Hoy" se distingue por TRES canales a la vez —círculo teal
 * relleno, tinte de celda y la etiqueta "hoy" en semibold— para que el color
 * nunca sea el único indicador (Constitution III).
 *
 * Datos: NO dispara requests nuevos. Consume exactamente los mismos dos
 * conjuntos de filtros que ya usan otras superficies del Inicio, así que
 * TanStack Query resuelve ambos desde el mismo cache (misma queryKey):
 *   - `plannedSessionsFilters()`  → la ventana de 14 días de `NextSessionTile`
 *     y del subtítulo del saludo en `DashboardPage`.
 *   - `executedSessionsFilters()` → la ventana de 60 días de
 *     `AttendanceMiniChart`, que cubre "gratis" los días ya pasados de la
 *     semana en curso (la ventana planificada empieza HOY).
 * Ambos helpers viven aquí —y no en `lib/datetime.ts`— porque este componente
 * es el dueño de la math de "semana en curso"; `DashboardPage` y
 * `AttendanceMiniChart` los importan para no re-derivar las mismas ventanas.
 *
 * Resiliencia (igual que el resto de tiles del Inicio, feature 031):
 *   - cargando / cold start (`isColdStartError`) → esqueletos, nunca tono de
 *     error.
 *   - error real → la tira sigue visible (las fechas siguen siendo útiles)
 *     con una línea neutra; nunca bloquea el resto de la página.
 *
 * Privacidad: sólo foco técnico y hora de la sesión — ningún dato de menores.
 */
import { useId } from "react";
import { Link } from "react-router-dom";
import { Check } from "lucide-react";

import { useTrainingSessions } from "@/api/trainingSessions";
import { isColdStartError } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { CLUB_LOCALE, CLUB_TIMEZONE } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { SessionFilters, TrainingSession } from "@/types/trainingSession.types";

/** Días hacia adelante de la ventana compartida de sesiones planificadas. */
export const PLANNED_WINDOW_DAYS = 14;

/** Días hacia atrás de la ventana compartida de sesiones ejecutadas. */
export const EXECUTED_WINDOW_DAYS = 60;

/** Fecha de "hoy" en la TZ del club, como "YYYY-MM-DD". */
export function clubTodayIso(): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  }).format(new Date());
}

/** "YYYY-MM-DD" de hoy (TZ club) + `days` días de calendario. */
export function clubIsoDateOffset(days: number): string {
  const [y, m, d] = clubTodayIso().split("-").map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d) + days * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

/**
 * Filtros de la ventana de sesiones planificadas — IDÉNTICOS a los de
 * `NextSessionTile` (hoy → +14 días, `status: "planned"`), para compartir
 * el mismo cache de TanStack Query en vez de duplicar el request.
 */
export function plannedSessionsFilters(): SessionFilters {
  return {
    from_date: clubIsoDateOffset(0),
    to_date: clubIsoDateOffset(PLANNED_WINDOW_DAYS),
    status: "planned",
  };
}

/**
 * Filtros de la ventana de sesiones ejecutadas (últimos 60 días), compartida
 * con `AttendanceMiniChart`. `hashKey` de TanStack ordena las claves del
 * objeto, así que basta con que los valores coincidan.
 */
export function executedSessionsFilters(): SessionFilters {
  return {
    from_date: clubIsoDateOffset(-EXECUTED_WINDOW_DAYS),
    to_date: clubIsoDateOffset(0),
    status: "executed",
  };
}

/**
 * Instante de mediodía en la TZ del club para una fecha civil "YYYY-MM-DD".
 * Bogotá no observa horario de verano, así que el offset -05:00 es válido
 * todo el año (misma técnica que `NextSessionTile`). Formatear la fecha
 * cruda con `new Date("YYYY-MM-DD")` la interpretaría como medianoche UTC y
 * mostraría el día anterior en America/Bogota.
 */
export function clubNoon(isoDate: string): Date {
  return new Date(`${isoDate}T12:00:00-05:00`);
}

/** Número de semana ISO 8601 (1-53) de "hoy" en la TZ del club. */
export function currentIsoWeekNumber(): number {
  const [y, m, d] = clubTodayIso().split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  // Jueves de la misma semana ISO: define el año al que pertenece la semana.
  const isoWeekday = date.getUTCDay() === 0 ? 7 : date.getUTCDay();
  date.setUTCDate(date.getUTCDate() + 4 - isoWeekday);
  const yearStart = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.ceil(((date.getTime() - yearStart) / 86_400_000 + 1) / 7);
}

/** Las 7 fechas ("YYYY-MM-DD") lunes→domingo de la semana ISO en curso. */
export function currentIsoWeekDays(): string[] {
  const [y, m, d] = clubTodayIso().split("-").map(Number);
  const todayUtc = Date.UTC(y, m - 1, d);
  const weekday = new Date(todayUtc).getUTCDay();
  const isoWeekday = weekday === 0 ? 7 : weekday; // 1=lunes … 7=domingo
  const monday = todayUtc - (isoWeekday - 1) * 86_400_000;
  return Array.from({ length: 7 }, (_, i) =>
    new Date(monday + i * 86_400_000).toISOString().slice(0, 10),
  );
}

/** "lun" — weekday corto en es-CO para una fecha civil. */
function weekdayLabel(isoDate: string): string {
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    weekday: "short",
    timeZone: CLUB_TIMEZONE,
  }).format(clubNoon(isoDate));
}

/** "4 p. m." / "7:30 a. m." — hora corta, sin minutos cuando son "00". */
function shortTimeLabel(session: TrainingSession): string {
  const raw = session.scheduled_start_time ?? "";
  const hhmmss = raw.length === 5 ? `${raw}:00` : raw;
  const instant = new Date(`${session.scheduled_date}T${hhmmss}-05:00`);
  if (Number.isNaN(instant.getTime())) return "";
  const minutes = Number(hhmmss.slice(3, 5));
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    hour: "numeric",
    ...(minutes === 0 ? {} : { minute: "2-digit" }),
    timeZone: CLUB_TIMEZONE,
  }).format(instant);
}

function SessionPill({ session, isTodayCell }: { session: TrainingSession; isTodayCell: boolean }) {
  const isExecuted = session.status === "executed";
  const time = shortTimeLabel(session);
  const label = [session.technical_focus, time].filter(Boolean).join(" ");

  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        isExecuted
          ? "bg-light-gray text-text-secondary"
          : isTodayCell
            ? "bg-white text-charcoal"
            : "bg-nav-active-bg text-charcoal",
      )}
    >
      {isExecuted && (
        <>
          <Check size={11} strokeWidth={2.5} className="shrink-0 text-success" aria-hidden="true" />
          <span className="sr-only">Ejecutada: </span>
        </>
      )}
      <span className="truncate">{label}</span>
    </span>
  );
}

export function WeekStrip() {
  const headingId = useId();
  const plannedQuery = useTrainingSessions(plannedSessionsFilters());
  // Misma queryKey que `AttendanceMiniChart` → sin request adicional; cubre
  // los días de la semana que ya pasaron (la ventana planificada arranca hoy).
  const executedQuery = useTrainingSessions(executedSessionsFilters());

  const weekDays = currentIsoWeekDays();
  const today = clubTodayIso();

  // Las DOS queries cuentan: la planificada sólo cubre de hoy en adelante,
  // así que lunes→ayer dependen exclusivamente de la ejecutada. Si sólo se
  // mirara la planificada, un fallo (o un vuelo aún en curso) de la ejecutada
  // pintaría "—" en los días pasados y el coach lo leería como "no hubo
  // entrenamientos esta semana".
  const isSessionsPending =
    plannedQuery.isLoading ||
    executedQuery.isLoading ||
    (plannedQuery.isError && isColdStartError(plannedQuery.error)) ||
    (executedQuery.isError && isColdStartError(executedQuery.error));
  // Un error real no bloquea la tira: los días siguen visibles y sólo se
  // avisa, en tono neutro, que las sesiones no se pudieron cargar.
  const hasSessionsError =
    (plannedQuery.isError && !isColdStartError(plannedQuery.error)) ||
    (executedQuery.isError && !isColdStartError(executedQuery.error));

  const sessions: TrainingSession[] = [
    ...(plannedQuery.data ?? []).filter((s) => s.status === "planned"),
    ...(executedQuery.data ?? []).filter((s) => s.status === "executed"),
  ];

  const sessionsByDay = new Map<string, TrainingSession[]>();
  for (const session of sessions) {
    if (!weekDays.includes(session.scheduled_date)) continue;
    const bucket = sessionsByDay.get(session.scheduled_date) ?? [];
    bucket.push(session);
    sessionsByDay.set(session.scheduled_date, bucket);
  }
  for (const bucket of sessionsByDay.values()) {
    bucket.sort((a, b) => a.scheduled_start_time.localeCompare(b.scheduled_start_time));
  }

  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-3 rounded-xl bg-white px-5 py-4 shadow-card"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-[15px] font-semibold text-charcoal">
          Semana en curso
        </h2>
        {/* `text-charcoal` y no `text-primary`: el turquesa de marca sobre la
            tarjeta blanca da 2.42:1 y no pasa AA para 14px; el subrayado
            sigue señalando que es un enlace. */}
        <Link
          to="/calendar"
          className="inline-flex min-h-11 items-center text-sm font-medium text-charcoal underline transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2"
        >
          Abrir calendario
        </Link>
      </div>

      <div
        className="grid grid-cols-7 gap-1 sm:gap-2"
        {...(isSessionsPending
          ? { role: "status", "aria-busy": true, "aria-label": "Cargando la semana en curso" }
          : {})}
      >
        {weekDays.map((day) => {
          const isToday = day === today;
          const dayNumber = Number(day.slice(8, 10));
          const daySessions = sessionsByDay.get(day) ?? [];

          return (
            <div
              key={day}
              className={cn(
                "flex min-w-0 flex-col items-center gap-1.5 rounded-xl px-1 py-2",
                isToday && "bg-nav-active-bg",
              )}
            >
              {/* La etiqueta de hoy se queda en `text-charcoal`: el acento
                  sobre el tinte de la celda da 4.09:1 y no pasa AA. El
                  semibold ya la diferencia, y el color lo aportan el círculo
                  relleno y el tinte de la celda — canales no textuales. */}
              <span
                className={cn(
                  "text-[11px]",
                  isToday ? "font-semibold text-charcoal" : "text-mid-gray",
                )}
              >
                {weekdayLabel(day)}
                {isToday && " · hoy"}
              </span>
              {/* `text-midnight` sobre el relleno turquesa (7.8:1); blanco
                  daba 2.42:1. Midnight no se invierte con el tema y
                  `--color-primary` tampoco, así que sirve en claro y oscuro. */}
              <span
                className={cn(
                  "flex h-[26px] w-[26px] items-center justify-center text-sm font-semibold",
                  isToday ? "rounded-full bg-primary text-midnight" : "text-charcoal",
                )}
              >
                {dayNumber}
              </span>

              {isSessionsPending ? (
                <Skeleton className="h-4 w-full max-w-[64px] rounded-full" />
              ) : daySessions.length === 0 ? (
                <span className="text-[11px] text-mid-gray">—</span>
              ) : (
                daySessions.map((session) => (
                  <SessionPill key={session.id} session={session} isTodayCell={isToday} />
                ))
              )}
            </div>
          );
        })}
      </div>

      {hasSessionsError && (
        <p className="text-xs text-mid-gray">
          No se pudieron cargar las sesiones de esta semana.
        </p>
      )}
    </section>
  );
}
