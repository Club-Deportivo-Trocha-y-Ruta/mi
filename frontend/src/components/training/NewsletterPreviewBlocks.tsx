/**
 * NewsletterPreviewBlocks — renderiza los bloques email_blocks del boletín.
 *
 * Cada bloque del email_blocks se muestra de forma legible:
 * - attendance: % asistencia, comparativa, racha
 * - technical_load: rúbrica, focos técnicos
 * - races: resultados Copa Valle del mes
 * - calendar: próxima válida / sesiones planificadas
 * - support_at_home: tips de apoyo en casa
 * - photos: miniaturas (links, sin datos binarios)
 * - badges: insignias ganadas
 *
 * Si un bloque falta en email_blocks se omite silenciosamente.
 * NO se renderiza antropometría — esa información va solo en el PDF.
 */

import { Award, Calendar, Camera, Home, TrendingUp, Users } from "lucide-react";

import { cn } from "@/lib/utils";

interface BlockCardProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  testId?: string;
}

function BlockCard({ icon, title, children, testId }: BlockCardProps) {
  return (
    <article
      className="rounded-xl border border-[rgba(34,42,53,0.08)] bg-white px-4 py-4 shadow-sm"
      data-testid={testId}
      aria-label={title}
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-light-gray text-charcoal">
          {icon}
        </span>
        <h3 className="text-sm font-semibold text-charcoal">{title}</h3>
      </div>
      {children}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Bloque Asistencia
// ---------------------------------------------------------------------------

interface AttendanceBlock {
  attendance_pct?: number;
  prev_month_pct?: number;
  streak_sessions?: number;
  count_present?: number;
  count_total?: number;
}

function AttendanceBlockView({ data }: { data: AttendanceBlock }) {
  const pct = data.attendance_pct ?? null;
  const prev = data.prev_month_pct ?? null;
  const streak = data.streak_sessions ?? null;

  return (
    <BlockCard
      icon={<Users className="h-4 w-4" aria-hidden="true" />}
      title="Asistencia y compromiso"
      testId="block-attendance"
    >
      <div className="space-y-2 text-sm text-charcoal">
        {pct !== null && (
          <div className="flex items-center gap-2">
            <span className="font-semibold text-lg leading-none">{pct.toFixed(0)}%</span>
            <span className="text-mid-gray">asistencia este mes</span>
            {prev !== null && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-xs font-medium",
                  pct >= prev
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700",
                )}
              >
                {pct >= prev ? "+" : ""}
                {(pct - prev).toFixed(0)}% vs mes anterior
              </span>
            )}
          </div>
        )}
        {data.count_present !== undefined && data.count_total !== undefined && (
          <p className="text-xs text-mid-gray">
            {data.count_present} de {data.count_total} sesiones
          </p>
        )}
        {streak !== null && streak > 0 && (
          <p className="text-xs text-mid-gray">
            Racha activa: <span className="font-medium text-charcoal">{streak} sesiones consecutivas</span>
          </p>
        )}
      </div>
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Carga técnica
// ---------------------------------------------------------------------------

interface TechnicalLoadBlock {
  focos_tecnicos?: string[];
  avg_rpe?: number;
  avg_rubric_effort?: number;
  avg_rubric_attitude?: number;
  avg_rubric_technique?: number;
  hours_per_week?: number;
}

function TechnicalLoadBlockView({ data }: { data: TechnicalLoadBlock }) {
  const metrics = [
    { label: "Esfuerzo", value: data.avg_rubric_effort },
    { label: "Actitud", value: data.avg_rubric_attitude },
    { label: "Técnica", value: data.avg_rubric_technique },
  ].filter((m) => m.value !== undefined && m.value !== null);

  return (
    <BlockCard
      icon={<TrendingUp className="h-4 w-4" aria-hidden="true" />}
      title="Carga y desarrollo técnico"
      testId="block-technical-load"
    >
      <div className="space-y-3 text-sm">
        {data.focos_tecnicos && data.focos_tecnicos.length > 0 && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-1.5">
              Focos del mes
            </p>
            <div className="flex flex-wrap gap-1.5">
              {data.focos_tecnicos.map((foco) => (
                <span
                  key={foco}
                  className="rounded-full bg-light-gray px-2.5 py-0.5 text-xs font-medium text-charcoal"
                >
                  {foco}
                </span>
              ))}
            </div>
          </div>
        )}
        {data.avg_rpe !== undefined && data.avg_rpe !== null && (
          <p className="text-xs text-mid-gray">
            RPE promedio: <span className="font-semibold text-charcoal">{data.avg_rpe.toFixed(1)}</span>
            <span className="ml-1 text-[10px]">(escala 1-10)</span>
          </p>
        )}
        {metrics.length > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {metrics.map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-light-gray px-2 py-2 text-center">
                <p className="text-base font-semibold text-charcoal">
                  {(value as number).toFixed(1)}
                </p>
                <p className="text-[10px] text-mid-gray mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        )}
        {data.hours_per_week !== undefined && data.hours_per_week !== null && (
          <p className="text-xs text-mid-gray">
            Carga semanal: <span className="font-medium text-charcoal">{data.hours_per_week.toFixed(1)} h/semana</span>
          </p>
        )}
      </div>
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Resultados Copa Valle
// ---------------------------------------------------------------------------

interface RaceEntry {
  event_name?: string;
  event_date?: string;
  position?: number;
  category?: string;
  gap_p1_ms?: number;
  gap_p3_ms?: number;
}

interface RacesBlock {
  races?: RaceEntry[];
  ranking_club?: number;
  projection?: string;
}

function formatGap(ms: number): string {
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function RacesBlockView({ data }: { data: RacesBlock }) {
  return (
    <BlockCard
      icon={<Award className="h-4 w-4" aria-hidden="true" />}
      title="Resultados Copa Valle"
      testId="block-races"
    >
      {data.races && data.races.length > 0 ? (
        <div className="space-y-3">
          {data.races.map((race, idx) => (
            <div
              key={idx}
              className="rounded-lg border border-[rgba(34,42,53,0.06)] p-3 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-medium text-charcoal">{race.event_name ?? "Válida"}</p>
                {race.position !== undefined && (
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-bold",
                      race.position <= 3
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-light-gray text-charcoal",
                    )}
                  >
                    P{race.position}
                  </span>
                )}
              </div>
              {race.event_date && (
                <p className="text-xs text-mid-gray mt-0.5">{race.event_date}</p>
              )}
              {race.category && (
                <p className="text-xs text-mid-gray">{race.category}</p>
              )}
              {race.gap_p1_ms !== undefined && race.gap_p1_ms > 0 && (
                <p className="text-xs text-mid-gray mt-1">
                  Gap P1: <span className="font-medium text-charcoal">+{formatGap(race.gap_p1_ms)}</span>
                </p>
              )}
              {race.gap_p3_ms !== undefined && race.gap_p3_ms > 0 && (
                <p className="text-xs text-mid-gray">
                  Gap P3: <span className="font-medium text-charcoal">+{formatGap(race.gap_p3_ms)}</span>
                </p>
              )}
            </div>
          ))}
          {data.ranking_club !== undefined && (
            <p className="text-xs text-mid-gray">
              Posición en ranking del club: <span className="font-medium text-charcoal">{data.ranking_club}</span>
            </p>
          )}
          {data.projection && (
            <p className="text-xs text-mid-gray italic">
              Proyección: {data.projection}
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-mid-gray">Sin carreras este mes.</p>
      )}
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Calendario
// ---------------------------------------------------------------------------

interface CalendarBlock {
  next_race_name?: string;
  next_race_date?: string;
  next_race_location?: string;
  macro_phase?: string;
  planned_sessions_next_month?: number;
}

function CalendarBlockView({ data }: { data: CalendarBlock }) {
  return (
    <BlockCard
      icon={<Calendar className="h-4 w-4" aria-hidden="true" />}
      title="Calendario"
      testId="block-calendar"
    >
      <div className="space-y-2 text-sm text-charcoal">
        {data.next_race_name && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-0.5">
              Próxima válida
            </p>
            <p className="font-medium">{data.next_race_name}</p>
            {data.next_race_date && (
              <p className="text-xs text-mid-gray">{data.next_race_date}</p>
            )}
            {data.next_race_location && (
              <p className="text-xs text-mid-gray">{data.next_race_location}</p>
            )}
          </div>
        )}
        {data.macro_phase && (
          <p className="text-xs text-mid-gray">
            Fase macrociclo: <span className="font-medium text-charcoal">{data.macro_phase}</span>
          </p>
        )}
        {data.planned_sessions_next_month !== undefined && (
          <p className="text-xs text-mid-gray">
            Sesiones planificadas el próximo mes:{" "}
            <span className="font-medium text-charcoal">{data.planned_sessions_next_month}</span>
          </p>
        )}
        {!data.next_race_name && !data.macro_phase && !data.planned_sessions_next_month && (
          <p className="text-sm text-mid-gray">Sin información de calendario disponible.</p>
        )}
      </div>
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Apoyo en casa
// ---------------------------------------------------------------------------

interface SupportTip {
  text: string;
  title?: string;
  category?: string;
}

interface SupportBlock {
  tips?: Array<string | SupportTip>;
  hydration_reminder?: string;
  sleep_reminder?: string;
}

function SupportBlockView({ data }: { data: SupportBlock }) {
  const normalizedTips: string[] = (data.tips ?? []).map((tip) =>
    typeof tip === 'string' ? tip : tip.text
  );
  const allTips = [
    ...normalizedTips,
    ...(data.hydration_reminder ? [data.hydration_reminder] : []),
    ...(data.sleep_reminder ? [data.sleep_reminder] : []),
  ];

  return (
    <BlockCard
      icon={<Home className="h-4 w-4" aria-hidden="true" />}
      title="Como apoyar desde casa"
      testId="block-support"
    >
      {allTips.length > 0 ? (
        <ul className="space-y-1.5 text-sm text-charcoal" role="list">
          {allTips.map((tip, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-charcoal/40" aria-hidden="true" />
              {tip}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-mid-gray">Sin recomendaciones para este mes.</p>
      )}
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Fotos
// ---------------------------------------------------------------------------

interface PhotoEntry {
  thumbnail_url?: string;
  caption?: string;
  media_id?: number;
}

interface PhotosBlock {
  photos?: PhotoEntry[];
  total?: number;
}

function PhotosBlockView({ data }: { data: PhotosBlock }) {
  const photos = data.photos ?? [];

  return (
    <BlockCard
      icon={<Camera className="h-4 w-4" aria-hidden="true" />}
      title="Fotos del mes"
      testId="block-photos"
    >
      {photos.length > 0 ? (
        <div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {photos.slice(0, 8).map((photo, idx) => (
              <div
                key={photo.media_id ?? idx}
                className="aspect-square overflow-hidden rounded-lg bg-light-gray"
              >
                {photo.thumbnail_url ? (
                  <img
                    src={photo.thumbnail_url}
                    alt={photo.caption ?? `Foto ${idx + 1}`}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div
                    className="flex h-full w-full items-center justify-center"
                    aria-label={photo.caption ?? `Foto ${idx + 1}`}
                  >
                    <Camera className="h-5 w-5 text-mid-gray" aria-hidden="true" />
                  </div>
                )}
              </div>
            ))}
          </div>
          {data.total !== undefined && data.total > 8 && (
            <p className="mt-2 text-xs text-mid-gray">
              +{data.total - 8} fotos adicionales en el PDF.
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-mid-gray">Sin fotos etiquetadas este mes.</p>
      )}
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Bloque Insignias (Badges)
// ---------------------------------------------------------------------------

interface BadgeEntry {
  badge_type?: string;
  label?: string;
  description?: string;
}

interface BadgesBlock {
  badges?: BadgeEntry[];
}

const BADGE_ICONS: Record<string, string> = {
  attendance_100: "100%",
  attendance_90: "90%",
  attendance_75: "75%",
  first_podium: "P",
  mtp: "MT",
  top10: "T10",
};

function BadgesBlockView({ data }: { data: BadgesBlock }) {
  const badges = data.badges ?? [];

  // Sin insignias este mes: ocultar el bloque entero. Es más sutil para
  // el padre que mostrar "0 insignias", evitando reforzar comparaciones.
  if (badges.length === 0) {
    return null;
  }

  return (
    <BlockCard
      icon={<Award className="h-4 w-4" aria-hidden="true" />}
      title="Insignias del mes"
      testId="block-badges"
    >
      {badges.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {badges.map((badge, idx) => (
            <div
              key={idx}
              className="flex flex-col items-center gap-1 rounded-xl border border-yellow-200 bg-yellow-50 px-3 py-2"
              role="img"
              aria-label={badge.label ?? badge.badge_type ?? "Insignia"}
            >
              <span className="text-lg font-bold text-yellow-700">
                {BADGE_ICONS[badge.badge_type ?? ""] ?? "★"}
              </span>
              <span className="text-xs font-medium text-charcoal">
                {badge.label ?? badge.badge_type}
              </span>
              {badge.description && (
                <span className="text-[10px] text-mid-gray text-center leading-tight">
                  {badge.description}
                </span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-mid-gray">Sin insignias este mes.</p>
      )}
    </BlockCard>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

interface NewsletterPreviewBlocksProps {
  emailBlocks: Record<string, unknown> | null;
  badges: Array<Record<string, unknown>> | null;
}

export function NewsletterPreviewBlocks({
  emailBlocks,
  badges,
}: NewsletterPreviewBlocksProps) {
  if (!emailBlocks && (!badges || badges.length === 0)) {
    return (
      <div
        className="rounded-xl border border-dashed border-[rgba(34,42,53,0.12)] bg-white p-8 text-center"
        data-testid="preview-empty"
      >
        <p className="text-sm text-mid-gray">
          Sin contenido de preview disponible. Genera el boletín para ver los bloques.
        </p>
      </div>
    );
  }

  const blocks = (emailBlocks ?? {}) as Record<string, unknown>;
  const attendance = blocks.attendance as AttendanceBlock | undefined;
  const technical = blocks.technical_load as TechnicalLoadBlock | undefined;
  const races = blocks.races as RacesBlock | undefined;
  const calendar = blocks.calendar as CalendarBlock | undefined;
  const support = blocks.support_at_home as SupportBlock | undefined;
  const photos = blocks.photos as PhotosBlock | undefined;

  return (
    <div className="space-y-3" data-testid="newsletter-preview-blocks" aria-label="Preview del boletín">
      {attendance && <AttendanceBlockView data={attendance} />}
      {technical && <TechnicalLoadBlockView data={technical} />}
      {races && <RacesBlockView data={races} />}
      {calendar && <CalendarBlockView data={calendar} />}
      {support && <SupportBlockView data={support} />}
      {photos && <PhotosBlockView data={photos} />}

      {/* Insignias — puede venir de email_blocks.badges o del campo badges_earned raíz */}
      {(blocks.badges || (badges && badges.length > 0)) && (
        <BadgesBlockView
          data={{
            badges:
              (blocks.badges as BadgesBlock)?.badges ??
              (badges as BadgeEntry[]) ??
              [],
          }}
        />
      )}
    </div>
  );
}
