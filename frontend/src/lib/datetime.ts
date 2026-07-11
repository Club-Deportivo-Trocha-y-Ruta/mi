export const CLUB_TIMEZONE = "America/Bogota";
export const CLUB_LOCALE = "es-CO";

type DateInput = string | Date | null | undefined;

/**
 * Detecta strings ISO 8601 con fecha+hora pero sin marcador de zona
 * (sin "Z" ni offset ±HH:MM). El backend usa columnas MySQL DateTime
 * sin tz que viajan en UTC pero Pydantic las serializa naive; JS
 * interpretaría esos strings como local del browser y desfasaría las
 * horas. Convención: tratar naive como UTC.
 */
const ISO_DATETIME_NAIVE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;

function toDate(value: DateInput): Date | null {
  if (value == null || value === "") return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  const normalized = ISO_DATETIME_NAIVE_RE.test(value) ? `${value}Z` : value;
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}

/** "25 de mayo de 2026, 02:13 p. m." */
export function formatDateTime(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "25 de mayo de 2026" */
export function formatDate(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "02:13 p. m." */
export function formatTime(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "25/05/2026" */
export function formatDateShort(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "25 de mayo" (sin año) */
export function formatDayMonth(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "numeric",
    month: "long",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "25 may 2026" — formato corto: día + mes abreviado + año */
export function formatDateMedium(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/** "25 may" — día + mes abreviado, sin año */
export function formatDayMonthShort(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "2-digit",
    month: "short",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/**
 * "lunes, 25 de mayo de 2026" — nombre del día de semana largo, fecha completa.
 * Usado en drawers de eventos de calendario.
 */
export function formatFullDate(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/**
 * "lun., 25 may" — weekday corto + día + mes abreviado, sin año.
 * Usado en cards de sesiones para padres.
 */
export function formatWeekdayShortDate(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(CLUB_LOCALE, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
}

/**
 * "25 may 2026 · 14:13" — fecha corta con hora en 24h separada por ·.
 * Usada en InsightsTimeline y AthleteAIAnalysisTab donde se necesita
 * presentar fecha + hora en formato compacto para entidades operativas (análisis IA).
 */
export function formatDateTimeCompact(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";
  const datePart = new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(d);
  const timePart = new Intl.DateTimeFormat(CLUB_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: CLUB_TIMEZONE,
  }).format(d);
  return `${datePart} · ${timePart}`;
}

/**
 * "Hoy" / "Ayer" / "Mañana" / fallback a formatDate.
 * La referencia "hoy" es la fecha actual en CLUB_TIMEZONE.
 */
export function formatRelativeDay(value: DateInput): string {
  const d = toDate(value);
  if (!d) return "";

  // Extraer la fecha del valor en la TZ del club.
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  })
    .format(d)
    .split("-")
    .map(Number);
  const targetDay = new Date(parts[0], parts[1] - 1, parts[2]);

  // Fecha "hoy" también en TZ del club.
  const nowParts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  })
    .format(new Date())
    .split("-")
    .map(Number);
  const todayDay = new Date(nowParts[0], nowParts[1] - 1, nowParts[2]);

  const diffMs = targetDay.getTime() - todayDay.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Hoy";
  if (diffDays === -1) return "Ayer";
  if (diffDays === 1) return "Mañana";
  return formatDate(d);
}

/**
 * Año actual (season) en CLUB_TIMEZONE — no el año local del navegador/runtime.
 * Misma técnica de extracción que formatRelativeDay: formatea "hoy" con
 * Intl.DateTimeFormat("en-CA", { timeZone: CLUB_TIMEZONE }) y toma el año.
 * Evita el sesgo de `new Date().getFullYear()` cerca de la medianoche cuando
 * la TZ del cliente/servidor difiere de America/Bogota (UTC-5).
 */
export function currentSeason(): number {
  const [year] = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  })
    .format(new Date())
    .split("-")
    .map(Number);
  return year;
}

/**
 * Formatea una duración en minutos como "hh:mm:ss".
 * Acepta minutos fraccionarios (ej. un promedio en horas convertido a minutos);
 * los segundos salen de la fracción. Retorna "—" si el valor es null/undefined.
 * Ej: 720 → "12:00:00", 126 → "02:06:00".
 */
export function formatMinutesAsHms(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  const totalSeconds = Math.round(minutes * 60);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}
