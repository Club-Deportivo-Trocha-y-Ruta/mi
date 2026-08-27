import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, ChevronsLeft, ChevronsRight } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useNavBadges, type NavBadgeCounts } from "@/hooks/layout/useNavBadges";
import { cn } from "@/lib/utils";
import {
  getGroupedAreas,
  isAreaActive,
  resolveActiveItemId,
  resolveAreaDefaultTo,
  type NavArea,
  type NavRole,
} from "@/lib/navigation";

export interface SidebarNavProps {
  /** Only "coach"/"admin" consume this — parent nav is out of scope (spec.md Assumptions). */
  role: NavRole;
  /**
   * `true` → riel de 72px; `false` → barra expandida de 256px.
   *
   * Contractualmente `AppShell` SIEMPRE pasa este par (`collapsed` +
   * `onToggleCollapsed`, ambos de `useSidebarCollapsed`). Se declaran
   * opcionales sólo para que el `AppShell` previo a la integración de la
   * feature 035 siga compilando; el default (`false` / no-op) equivale a la
   * barra expandida de siempre.
   */
  collapsed?: boolean;
  /** Alterna riel ↔ expandida. Ver nota en `collapsed`. */
  onToggleCollapsed?: () => void;
  /** Optional callback fired on any link click (e.g. closing a mobile drawer). */
  onNavigate?: () => void;
  /** Pie de la barra — hoy la tarjeta de usuario (`UserMenu`), la monta `AppShell`. */
  footer?: ReactNode;
}

/**
 * Anillo de foco — mismo tratamiento que `QuickCreate`/`UserMenu`, los otros
 * controles del shell.
 */
const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50";

/**
 * Estado activo (feature 035, `NavEntrenador.dc.html` §"Estado activo"):
 * tinte + barra de 3px + ícono en el acento + label semibold. El color nunca
 * es el único canal — el peso tipográfico y la barra sobreviven en escala de
 * grises y en modo de alto contraste.
 */
const areaRowBase =
  "relative flex min-h-11 flex-1 items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors";
const areaRowActive = "bg-nav-active-bg font-semibold text-charcoal";
const areaRowInactive =
  "font-medium text-mid-gray hover:bg-light-gray hover:text-charcoal";

// `min-h-11` (44px) y no los 36px del mockup: los sub-items son 12 destinos
// de navegación reales y el piso táctil del proyecto manda sobre el ritmo
// vertical dibujado (mismo criterio que las filas de `PendingInbox`).
const subItemBase =
  "flex min-h-11 items-center rounded-lg px-2.5 py-2 text-[13px] transition-colors";
const subItemActive = "bg-nav-active-bg font-semibold text-charcoal";
const subItemInactive =
  "font-medium text-mid-gray hover:bg-light-gray hover:text-charcoal";

const railTileBase =
  "relative flex h-11 w-11 items-center justify-center rounded-lg transition-colors";
const railTileActive = "bg-nav-active-bg text-nav-accent";
const railTileInactive = "text-mid-gray hover:bg-light-gray hover:text-charcoal";

/** Barra indicadora de 3×18px del estado activo. */
function ActiveBar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "absolute top-1/2 h-[18px] w-[3px] -translate-y-1/2 rounded-xs bg-primary",
        className,
      )}
    />
  );
}

/** Conteo de pendientes del área, si su fuente resolvió con algo que mostrar. */
function badgeForArea(
  areaId: string,
  badges: NavBadgeCounts,
): number | undefined {
  if (areaId === "competitions") return badges.competitions;
  if (areaId === "families") return badges.families;
  return undefined;
}

/**
 * Nombre accesible del área cuando lleva insignia: «Competencias · 2
 * pendientes». La píldora/punto es decorativa (`aria-hidden`), así que el
 * conteo se anuncia por aquí — misma copy en el riel (tooltip + aria-label)
 * que en la barra expandida.
 */
function areaLabelWithBadge(area: NavArea, badge: number | undefined): string {
  return badge === undefined
    ? area.label
    : `${area.label} · ${badge} pendientes`;
}

/**
 * Interior completo de la barra lateral de entrenador/admin (feature 035;
 * mockups `Main.dc.html` columna izquierda + `NavEntrenador.dc.html`).
 *
 * Dos modos:
 *  - Expandida (256px): marca + overlines de grupo («Operación» / «Club») +
 *    filas de área con disclosure, sub-items sobre riel de 2px e insignias de
 *    pendientes.
 *  - Riel (72px): sólo tiles de 44×44 con tooltip; la insignia se vuelve un
 *    punto ámbar y el conteo pasa al tooltip.
 *
 * Se conservan intactos los contratos de la feature 030: cada área de varios
 * items expone DOS controles independientes de ≥44px — la etiqueta navega a
 * `resolveAreaDefaultTo`, y un chevron aparte que sólo pliega/despliega
 * ("Expandir X"/"Contraer X") — el área activa se auto-expande desde el
 * pathname (`isAreaActive`) y el estado manual es transitorio (nunca se
 * persiste). En el riel no hay disclosure: los tiles son enlaces de área a
 * secas, y la navegación a sub-items pasa por la ruta por defecto del área.
 */
export function SidebarNav({
  role,
  collapsed = false,
  onToggleCollapsed,
  onNavigate,
  footer,
}: SidebarNavProps) {
  const { pathname } = useLocation();
  const groups = getGroupedAreas(role);
  const badges = useNavBadges(role);
  // Transient — never persisted (data-model.md §4). Auto-expand always wins
  // for the active area; this only tracks manual opens of inactive ones.
  const [manuallyOpened, setManuallyOpened] = useState<Record<string, boolean>>(
    {},
  );

  if (collapsed) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center px-2">
        <img
          src="/logo-mark.png"
          alt=""
          aria-hidden="true"
          width={32}
          height={32}
          className="h-8 w-8 shrink-0"
        />

        {/* El provider envuelve TODOS los controles de sólo ícono del riel
            —tiles de área y el botón de expandir— para que ninguno quede sin
            pista visible al pasar el puntero. */}
        <TooltipProvider delayDuration={200}>
          <nav
            aria-label="Secciones"
            className="mt-5 flex flex-col items-center gap-1"
          >
            {groups.flatMap((group) => group.areas).map((area) => {
              const Icon = area.icon;
              const active = isAreaActive(area, pathname);
              const badge = badgeForArea(area.id, badges);
              const label = areaLabelWithBadge(area, badge);
              return (
                <Tooltip key={area.id}>
                  <TooltipTrigger asChild>
                    <Link
                      to={resolveAreaDefaultTo(area, role)}
                      onClick={onNavigate}
                      aria-label={label}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        railTileBase,
                        focusRing,
                        active ? railTileActive : railTileInactive,
                      )}
                    >
                      {active && <ActiveBar className="-left-2" />}
                      <Icon size={20} aria-hidden="true" />
                      {badge !== undefined && (
                        <span
                          aria-hidden="true"
                          className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-warning"
                        />
                      )}
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="right">{label}</TooltipContent>
                </Tooltip>
              );
            })}
          </nav>

          <div className="mt-auto flex flex-col items-center gap-3 self-stretch border-t border-border-gray pt-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Expandir navegación"
                  onClick={onToggleCollapsed}
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal",
                    focusRing,
                  )}
                >
                  <ChevronsRight size={16} aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">Expandir navegación</TooltipContent>
            </Tooltip>
            {footer}
          </div>
        </TooltipProvider>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ── Marca + control de colapso ── */}
      <div className="flex items-center gap-2.5 px-1">
        <img
          src="/logo-mark.png"
          alt=""
          aria-hidden="true"
          width={36}
          height={36}
          className="h-9 w-9 shrink-0"
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-display text-[15px] leading-tight font-semibold text-charcoal">
            Trocha y Ruta
          </span>
          <span className="truncate text-[11px] text-mid-gray">
            Club Ciclismo XCO
          </span>
        </div>
        {/* 28px visibles (mockup) pero área táctil real de 44×44 vía
            ::after — el control no puede quedar por debajo del mínimo
            táctil aunque el ícono sea pequeño. */}
        <button
          type="button"
          aria-label="Contraer navegación"
          onClick={onToggleCollapsed}
          className={cn(
            "relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal",
            "after:absolute after:-inset-2 after:content-['']",
            focusRing,
          )}
        >
          <ChevronsLeft size={14} aria-hidden="true" />
        </button>
      </div>

      {/* ── Áreas agrupadas ── */}
      <nav aria-label="Secciones" className="mt-5 flex flex-col">
        {groups.map((group, groupIndex) => (
          <div
            key={group.id}
            role="group"
            aria-labelledby={`nav-group-${group.id}`}
            className={cn("flex flex-col gap-0.5", groupIndex > 0 && "mt-2")}
          >
            <span
              id={`nav-group-${group.id}`}
              className="px-3 pt-1.5 pb-1 text-[11px] font-semibold tracking-[0.08em] text-mid-gray uppercase"
            >
              {group.label}
            </span>

            {group.areas.map((area) => {
              const visibleItems = area.items.filter((item) =>
                item.roles.includes(role),
              );
              const Icon = area.icon;
              const defaultTo = resolveAreaDefaultTo(area, role);
              const active = isAreaActive(area, pathname);
              const badge = badgeForArea(area.id, badges);

              const rowContent = (
                <>
                  {active && <ActiveBar className="left-0" />}
                  <Icon
                    size={18}
                    className={cn("shrink-0", active && "text-nav-accent")}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1 truncate">{area.label}</span>
                  {badge !== undefined && (
                    <span
                      aria-hidden="true"
                      className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-light-gray px-1.5 text-[11px] font-semibold text-text-secondary"
                    >
                      {badge}
                    </span>
                  )}
                </>
              );
              // El conteo va al nombre accesible (la píldora es decorativa);
              // sin insignia, el nombre lo aporta el propio texto de la fila.
              const rowAriaLabel =
                badge === undefined ? undefined : areaLabelWithBadge(area, badge);

              // Inicio (y cualquier área de un solo item): link plano, sin
              // disclosure — igual que en la feature 030.
              if (visibleItems.length <= 1) {
                return (
                  <Link
                    key={area.id}
                    to={defaultTo}
                    onClick={onNavigate}
                    aria-label={rowAriaLabel}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      areaRowBase,
                      focusRing,
                      active ? areaRowActive : areaRowInactive,
                    )}
                  >
                    {rowContent}
                  </Link>
                );
              }

              const open = active || !!manuallyOpened[area.id];

              return (
                <Collapsible
                  key={area.id}
                  open={open}
                  onOpenChange={(next) =>
                    setManuallyOpened((prev) => ({ ...prev, [area.id]: next }))
                  }
                >
                  <div className="flex items-center gap-1">
                    {/* Control 1 — navega a la ruta por defecto del área.
                        `Link` (no `NavLink`) porque el activo es a nivel de
                        área (`isAreaActive`), no de esta única ruta — mismo
                        pareo que `BottomNav`. */}
                    <Link
                      to={defaultTo}
                      onClick={onNavigate}
                      aria-label={rowAriaLabel}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        areaRowBase,
                        focusRing,
                        active ? areaRowActive : areaRowInactive,
                      )}
                    >
                      {rowContent}
                    </Link>

                    {/* Control 2 — sólo alterna el disclosure; nunca navega. */}
                    <CollapsibleTrigger
                      aria-label={
                        open ? `Contraer ${area.label}` : `Expandir ${area.label}`
                      }
                      className={cn(
                        "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal",
                        focusRing,
                      )}
                    >
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 transition-transform",
                          open && "rotate-180",
                        )}
                        aria-hidden="true"
                      />
                    </CollapsibleTrigger>
                  </div>

                  <CollapsibleContent>
                    <div className="my-0.5 ml-5 flex flex-col gap-0.5 border-l-2 border-border-gray pl-3.5">
                      {(() => {
                        // Plain `Link` + manually-computed active item — not
                        // `NavLink`'s own (non-`end`) prefix match, which would
                        // mark e.g. "Válidas" (`/competitions`) simultaneously
                        // active alongside "Sin enlazar"
                        // (`/competitions/unlinked`) or "Panorama de temporada"
                        // (`/competitions/insights/season/:year`).
                        const activeItemId = resolveActiveItemId(
                          visibleItems,
                          pathname,
                        );
                        return visibleItems.map((item) => {
                          const to =
                            typeof item.to === "function" ? item.to() : item.to;
                          const itemActive = item.id === activeItemId;
                          return (
                            <Link
                              key={item.id}
                              to={to}
                              onClick={onNavigate}
                              aria-current={itemActive ? "page" : undefined}
                              className={cn(
                                subItemBase,
                                focusRing,
                                itemActive ? subItemActive : subItemInactive,
                              )}
                            >
                              {item.label}
                            </Link>
                          );
                        });
                      })()}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              );
            })}
          </div>
        ))}
      </nav>

      {footer && (
        <div className="mt-auto border-t border-border-gray pt-3">{footer}</div>
      )}
    </div>
  );
}
