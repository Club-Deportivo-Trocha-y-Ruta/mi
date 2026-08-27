/**
 * MeasurementAlerts — tarjeta "Alertas de medición" del Inicio del coach
 * (fila C del mockup `specs/035-nav-dashboard-redesign/mockups/Main.dc.html`).
 *
 * Feature 035 reencuadra la sección como tarjeta (título + enlace a la lista
 * de atletas en el encabezado, círculo con inicial por fila, insignia de
 * estado a la derecha) SIN tocar la query, el orden ni los estados: siguen
 * siendo los mismos `useAlerts()`, el mismo criterio de "accionables", el
 * mismo tope de 8 filas y el mismo enlace "Ver todas (N)".
 *
 * Privacidad: sólo nombre y estado de medición del atleta; la inicial del
 * avatar se deriva del nombre que ya se muestra — nunca fecha de nacimiento
 * ni datos médicos.
 */
import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { AthleteLink } from "@/components/shared/AthleteLink";
import { ErrorState } from "@/components/shared/ErrorState";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useAlerts } from "@/hooks/athletes/useAlerts";
import { useAuthStore } from "@/store/auth.store";
import type { AthleteAlert, MeasurementStatus } from "@/types/alerts.types";
import { UserRole } from "@/types/enums";

/**
 * `/athletes` (la lista) está restringida a `UserRole.coach` (ver
 * `src/App.tsx`), igual que `/athletes/:id` en `AthleteLink.tsx` — admin NO
 * tiene acceso y `ProtectedRoute` lo rebota en silencio al dashboard.
 * Mantener sincronizado con el `allowedRoles` de esa ruta.
 */
const ATHLETES_LIST_ALLOWED_ROLES: readonly UserRole[] = [UserRole.coach];

/**
 * Tono + copy por estado de medición. El tono alimenta a `StatusBadge`, que
 * siempre acompaña el color con ícono y texto (Constitution III) — antes
 * esta tabla pintaba puntos y fondos con colores crudos de Tailwind, fuera
 * del vocabulario de estado del design system.
 */
const STATUS_META: Record<
  MeasurementStatus,
  { tone: Status; rowLabel: string; summaryLabel: string }
> = {
  overdue: { tone: "danger", rowLabel: "Vencida", summaryLabel: "vencidas" },
  due_soon: { tone: "warning", rowLabel: "Próxima", summaryLabel: "próximas" },
  ok: { tone: "success", rowLabel: "Al día", summaryLabel: "al día" },
  never: { tone: "neutral", rowLabel: "Sin medir", summaryLabel: "sin medir" },
};

function formatDaysText(alert: AthleteAlert): string {
  if (alert.measurement_status === "never") return "Sin medición";
  if (alert.days_overdue === null) return "";
  if (alert.days_overdue > 0) {
    return `${alert.days_overdue}d de atraso`;
  }
  return `Vence en ${Math.abs(alert.days_overdue)}d`;
}

/** Inicial para el círculo de avatar — nunca reemplaza al nombre visible. */
function initialOf(name: string): string {
  const trimmed = name.trim();
  return trimmed.length > 0 ? trimmed[0].toUpperCase() : "?";
}

/** Contenedor común de los tres estados (cargando, error, resuelto). */
function AlertsCard({
  headingId,
  action,
  children,
}: {
  headingId: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-3 rounded-xl bg-white px-5 py-4 shadow-card"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-[15px] font-semibold text-charcoal">
          Alertas de medición
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function MeasurementAlerts() {
  const headingId = useId();
  const { data, isPending, isError, refetch } = useAlerts();
  const role = useAuthStore((state) => state.user?.role);
  const canViewAthletesList =
    role !== undefined && ATHLETES_LIST_ALLOWED_ROLES.includes(role);

  const headerAction = canViewAthletesList ? (
    // `text-charcoal` y no `text-primary`: el turquesa de marca sobre la
    // tarjeta blanca da 2.42:1 y no pasa AA para 14px. El subrayado sigue
    // siendo el canal que dice "esto es un enlace".
    <Link
      to="/athletes"
      className="inline-flex min-h-11 shrink-0 items-center text-sm font-medium text-charcoal underline transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2"
    >
      Ver todos los atletas
    </Link>
  ) : undefined;

  if (isPending) {
    return (
      <AlertsCard headingId={headingId} action={headerAction}>
        <p className="text-sm text-mid-gray">Cargando alertas...</p>
      </AlertsCard>
    );
  }

  if (isError) {
    return (
      <AlertsCard headingId={headingId} action={headerAction}>
        <ErrorState
          message="No se pudieron cargar las alertas de medición."
          onRetry={() => void refetch()}
        />
      </AlertsCard>
    );
  }

  if (!data || data.athletes.length === 0) return null;

  const STATUS_ORDER: Record<MeasurementStatus, number> = {
    overdue: 0,
    due_soon: 1,
    never: 2,
    ok: 3,
  };

  const actionable = data.athletes
    .filter((a) => a.measurement_status !== "ok")
    .sort((a, b) => {
      const statusDiff = STATUS_ORDER[a.measurement_status] - STATUS_ORDER[b.measurement_status];
      if (statusDiff !== 0) return statusDiff;
      if (a.measurement_status === "overdue") {
        return (b.days_overdue ?? 0) - (a.days_overdue ?? 0);
      }
      if (a.measurement_status === "due_soon") {
        const aDays = a.days_overdue === null ? Infinity : Math.abs(a.days_overdue);
        const bDays = b.days_overdue === null ? Infinity : Math.abs(b.days_overdue);
        return aDays - bDays;
      }
      return 0;
    });

  const MAX_VISIBLE = 8;
  const visibleActionable = actionable.slice(0, MAX_VISIBLE);
  const remainingCount = actionable.length;

  const rapidGrowth = data.athletes.filter(
    (a) => a.growth_alerts.includes("rapid_growth")
  );

  return (
    <AlertsCard headingId={headingId} action={headerAction}>
      {/* Barra de resumen */}
      <div className="flex flex-wrap gap-2">
        {data.overdue > 0 && (
          <StatusBadge
            status={STATUS_META.overdue.tone}
            label={`${data.overdue} ${STATUS_META.overdue.summaryLabel}`}
          />
        )}
        {data.due_soon > 0 && (
          <StatusBadge
            status={STATUS_META.due_soon.tone}
            label={`${data.due_soon} ${STATUS_META.due_soon.summaryLabel}`}
          />
        )}
        <StatusBadge
          status={STATUS_META.ok.tone}
          label={`${data.ok} ${STATUS_META.ok.summaryLabel}`}
        />
        {data.never_measured > 0 && (
          <StatusBadge
            status={STATUS_META.never.tone}
            label={`${data.never_measured} ${STATUS_META.never.summaryLabel}`}
          />
        )}
      </div>

      {/* Alertas de crecimiento acelerado */}
      {rapidGrowth.length > 0 && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-4">
          <p className="mb-2 text-sm font-medium text-charcoal">
            Crecimiento acelerado detectado
          </p>
          {rapidGrowth.map((a) => (
            <p key={a.athlete_id} className="text-sm text-charcoal">
              <AthleteLink athleteId={a.athlete_id} className="font-medium underline">
                {a.athlete_name}
              </AthleteLink>
              {" — "}{a.growth_velocity_cm_month} cm/mes. {a.training_implications ?? "Revisar carga de entrenamiento."}
            </p>
          ))}
        </div>
      )}

      {/* Lista de atletas que requieren accion */}
      {actionable.length > 0 && (
        <ul>
          {visibleActionable.map((a, idx) => {
            const meta = STATUS_META[a.measurement_status];
            const detail = [a.current_phv_status, formatDaysText(a)]
              .filter((part): part is string => Boolean(part && part.length > 0))
              .join(" · ");
            return (
              <li
                key={a.athlete_id}
                className="relative flex min-h-11 items-center gap-3 py-3"
                style={idx > 0 ? { borderTop: "1px solid rgba(34, 42, 53, 0.06)" } : undefined}
              >
                <span
                  aria-hidden="true"
                  className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full bg-light-gray text-xs font-semibold text-text-secondary"
                >
                  {initialOf(a.athlete_name)}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  {/* El área táctil real es TODA la fila (el `<li>` es el
                      `relative` de referencia), no sólo el ancho del nombre:
                      el ::after se estira sobre avatar, detalle e insignia
                      —ninguno interactivo— así que la fila se comporta como
                      lo que aparenta. El `truncate` baja al span interior
                      porque su `overflow:hidden` recortaría el ::after.
                      El nombre accesible del enlace sigue siendo sólo el
                      nombre del atleta. */}
                  <AthleteLink
                    athleteId={a.athlete_id}
                    className="block text-[13px] font-semibold text-charcoal transition-opacity after:absolute after:inset-0 after:content-[''] hover:opacity-70"
                  >
                    <span className="block truncate">{a.athlete_name}</span>
                  </AthleteLink>
                  {detail && <span className="truncate text-xs text-mid-gray">{detail}</span>}
                </div>
                <span className="shrink-0">
                  <StatusBadge status={meta.tone} label={meta.rowLabel} />
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {/* Única vía para ver las alertas más allá del tope de 8 filas: alto
          táctil real (min-h-11) y misma tinta legible que el enlace del
          encabezado. */}
      {remainingCount > MAX_VISIBLE && (
        canViewAthletesList ? (
          <Link
            to="/athletes"
            className="inline-flex min-h-11 items-center self-start text-sm font-medium text-charcoal underline transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2"
          >
            Ver todas ({remainingCount})
          </Link>
        ) : (
          <span className="inline-flex items-center self-start text-sm font-medium text-charcoal">
            Ver todas ({remainingCount})
          </span>
        )
      )}
    </AlertsCard>
  );
}
