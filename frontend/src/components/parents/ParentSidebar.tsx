/**
 * ParentSidebar — Interior del drawer/sidebar del portal de familias
 * (feature 035, mockup `PadresMenu.dc.html`). Combina el selector de
 * atleta activo (hoy solo disponible como dropdown en el header,
 * `AthleteSwitcher.tsx`) con la navegación del portal, las utilidades de
 * cuenta (perfil, cerrar sesión) y un chip de estado de consentimiento.
 *
 * Componente de solo INTERIOR: no monta ningún `Dialog`/`Sheet`/overlay
 * propio — quien lo use decide el contenedor (drawer móvil en <768px,
 * barra fija en desktop, per el mockup "en ≥768px esta misma barra queda
 * fija"). Por eso no toca `AppShell` — una tarea posterior lo conecta.
 *
 * Props:
 *   - `onNavigate` — se dispara en cualquier fila que navega o cambia el
 *     atleta activo, para que el contenedor (drawer) pueda cerrarse.
 *   - `onClose` — gobierna solo el botón X de la cabecera; si no se pasa,
 *     el botón no se renderiza. Cuando sí se pasa, el botón además se oculta
 *     en ≥md (`md:hidden`): el contenedor es UNO SOLO —drawer bajo md, barra
 *     fija arriba— y la presentación la decide el CSS, no un breakpoint en
 *     JS, así que el X debe desaparecer por la misma vía. En la barra fija
 *     no hay overlay que cerrar y el control sería inerte.
 *
 * Resolución de activo de los enlaces de navegación: mismo algoritmo
 * "exact-match primero, luego el prefijo de ruta más largo gana" que
 * `resolveActiveItemId` (`lib/navigation.ts`), reimplementado localmente
 * (mismo racional que `ParentBottomNav.tsx` — ese modelo es coach/admin-only).
 * Mismo lenguaje visual de "pill" activo que `SidebarNav.tsx` (coach): tinte
 * `bg-nav-active-bg` + barra de 3px + ícono en `text-nav-accent` + label
 * semibold — el color nunca es el único canal del estado activo.
 */
import type { LucideIcon } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardList,
  Home,
  LogOut,
  UserRound,
  Users,
  X,
} from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { useActiveAthlete } from "@/hooks/parents/useActiveAthlete";
import { useMyConsentStatus } from "@/hooks/consent";
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";
import type { AthleteConsentStatus } from "@/types/consent";
import type { MyAthleteOut } from "@/types/parent.types";

export interface ParentSidebarProps {
  /** Se dispara en cualquier fila que navega o cambia el atleta activo (para que el drawer se cierre). */
  onNavigate?: () => void;
  /** Gobierna el botón X de la cabecera; sin esta prop, el botón no se renderiza. */
  onClose?: () => void;
}

// ---------------------------------------------------------------------------
// Navegación principal
// ---------------------------------------------------------------------------

interface ParentNavItem {
  id: string;
  label: string;
  to: string;
  icon: LucideIcon;
}

/** Orden de render — igual al mockup (Inicio, Calendario, Entrenamientos, Resumen mensual). */
const NAV_ITEMS: ParentNavItem[] = [
  { id: "home", label: "Inicio", to: "/my-athletes", icon: Home },
  { id: "calendar", label: "Calendario", to: "/parents/calendar", icon: CalendarDays },
  {
    id: "sessions",
    label: "Entrenamientos",
    to: "/parents/training/sessions",
    icon: ClipboardList,
  },
  {
    id: "overview",
    label: "Resumen mensual",
    to: "/parents/training/overview",
    icon: BarChart3,
  },
];

/**
 * Exact-match primero, luego el prefijo de ruta más largo gana — mismo
 * algoritmo que `resolveActiveItemId` (ver nota de módulo). Evita que
 * `/parents/training/overview` también encienda "Entrenamientos", y
 * mantiene "Inicio" activo en subrutas como `/my-athletes/:id`. Recibe la
 * lista de items en vez de leer el módulo `NAV_ITEMS` porque "Bitácora"
 * (feature 038) es un item dinámico — su `to` depende del atleta activo.
 */
function resolveActiveNavId(
  pathname: string,
  items: ParentNavItem[],
): string | undefined {
  const exactMatch = items.find((item) => item.to === pathname);
  if (exactMatch) return exactMatch.id;

  const prefixMatches = items.filter((item) => pathname.startsWith(`${item.to}/`));
  if (prefixMatches.length === 0) return undefined;

  return prefixMatches.reduce((longest, current) =>
    current.to.length > longest.to.length ? current : longest,
  ).id;
}

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50";

const navRowBase = cn(
  "relative flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors",
  focusRing,
);
const navRowActive = "bg-nav-active-bg font-semibold text-charcoal";
const navRowInactive = "font-medium text-mid-gray hover:bg-light-gray hover:text-charcoal";

// ---------------------------------------------------------------------------
// Selector de atleta activo
// ---------------------------------------------------------------------------

function athleteInitial(firstName: string): string {
  return firstName.trim().charAt(0).toUpperCase() || "?";
}

/** "12 años · Infantil" — edad en años completos (privacidad: nunca la fecha exacta). */
function athleteAgeCategory(athlete: MyAthleteOut): string {
  const parts: string[] = [];
  if (athlete.age_decimal !== null) {
    parts.push(`${Math.floor(athlete.age_decimal)} años`);
  }
  if (athlete.category) {
    parts.push(athlete.category);
  }
  return parts.join(" · ");
}

interface AthleteRowProps {
  athlete: MyAthleteOut;
  active: boolean;
  onSelect: () => void;
}

function AthleteRow({ athlete, active, onSelect }: AthleteRowProps) {
  const subtitle = athleteAgeCategory(athlete);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      data-testid={`parent-sidebar-athlete-${athlete.athlete_id}`}
      className={cn(
        "flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-left transition-colors",
        focusRing,
        active ? "bg-nav-active-bg" : "hover:bg-light-gray",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold",
          active
            ? "bg-white text-nav-accent"
            : "bg-light-gray text-text-secondary ring-1 ring-inset ring-border-gray",
        )}
      >
        {athleteInitial(athlete.athlete_first_name)}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block truncate text-sm text-charcoal",
            active ? "font-semibold" : "font-medium",
          )}
        >
          {athlete.athlete_first_name}
        </span>
        {subtitle && (
          <span className="block truncate text-[11px] text-mid-gray">{subtitle}</span>
        )}
      </span>
      {active && (
        <Check
          aria-hidden="true"
          strokeWidth={2.5}
          className="h-4 w-4 shrink-0 text-nav-accent"
        />
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Chip de consentimiento (pie del drawer)
// ---------------------------------------------------------------------------

function isConsentOk(status: AthleteConsentStatus): boolean {
  const consent = status.current_consent;
  return consent !== null && consent.withdrawn_at === null && consent.is_current_policy;
}

function ConsentChip({
  consentsPerAthlete,
}: {
  consentsPerAthlete: AthleteConsentStatus[];
}) {
  const allOk = consentsPerAthlete.every(isConsentOk);
  const Icon = allOk ? CheckCircle2 : AlertTriangle;
  const label = allOk ? "Consentimientos al día" : "Consentimiento por renovar";

  return (
    <span
      data-testid="parent-sidebar-consent-chip"
      className={cn(
        "inline-flex items-center gap-[5px] rounded-full border px-2.5 py-1 text-[11px] font-medium text-charcoal",
        allOk ? "border-success/30 bg-success/10" : "border-warning/30 bg-warning/10",
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn("h-3 w-3 shrink-0", allOk ? "text-success" : "text-warning")}
      />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ParentSidebar({ onNavigate, onClose }: ParentSidebarProps) {
  const { pathname } = useLocation();
  const {
    athlete: activeAthlete,
    athletes,
    activeAthleteId,
    setActiveAthlete,
    isLoading: isAthletesLoading,
  } = useActiveAthlete();
  const { data: consentStatus, isLoading: isConsentLoading } = useMyConsentStatus();
  const logout = useAuthStore((state) => state.logout);

  // "Bitácora" (feature 038) solo aparece cuando hay un atleta activo
  // resuelto (hijo único, o selección explícita en multi-hijo) — su ruta
  // necesita el `athleteId`, a diferencia del resto de items que son
  // globales al portal.
  const navItems: ParentNavItem[] = activeAthlete
    ? [
        ...NAV_ITEMS,
        {
          id: "bitacora",
          label: "Bitácora",
          to: `/my-athletes/${activeAthlete.athlete_id}/bitacora`,
          icon: BookOpen,
        },
      ]
    : NAV_ITEMS;

  const activeNavId = resolveActiveNavId(pathname, navItems);
  const showAthletes = !isAthletesLoading && athletes.length > 0;
  const allAthletesActive = activeAthleteId === null;

  function handleSelectAthlete(id: number | null) {
    setActiveAthlete(id);
    onNavigate?.();
  }

  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      {/* Cabecera — marca + cerrar (drawer móvil) */}
      <div className="flex items-center gap-2.5 p-1">
        <img
          src="/logo-mark.png"
          alt="Trocha y Ruta"
          width={32}
          height={32}
          className="h-8 w-8 shrink-0"
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-display text-[15px] leading-tight font-semibold text-charcoal">
            Trocha y Ruta
          </span>
          <span className="truncate text-[11px] text-mid-gray">Portal de familias</span>
        </div>
        {onClose && (
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={onClose}
            className={cn(
              "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal md:hidden",
              focusRing,
            )}
          >
            <X className="h-[18px] w-[18px]" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Selector de atleta activo */}
      {showAthletes && (
        <>
          <span
            id="parent-sidebar-athletes-heading"
            className="px-3 pt-4 pb-1.5 text-[11px] font-semibold tracking-[0.08em] text-mid-gray uppercase"
          >
            Tus deportistas
          </span>
          <div
            role="group"
            aria-labelledby="parent-sidebar-athletes-heading"
            className="flex flex-col gap-0.5"
          >
            {athletes.map((athlete) => (
              <AthleteRow
                key={athlete.athlete_id}
                athlete={athlete}
                active={athlete.athlete_id === activeAthleteId}
                onSelect={() => handleSelectAthlete(athlete.athlete_id)}
              />
            ))}
            <button
              type="button"
              onClick={() => handleSelectAthlete(null)}
              aria-current={allAthletesActive ? "true" : undefined}
              data-testid="parent-sidebar-athlete-all"
              className={cn(
                "flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-left text-sm font-medium transition-colors",
                focusRing,
                allAthletesActive
                  ? "bg-nav-active-bg text-charcoal"
                  : "text-mid-gray hover:bg-light-gray hover:text-charcoal",
              )}
            >
              <Users className="h-[17px] w-[17px] shrink-0" aria-hidden="true" />
              Todos mis atletas
            </button>
          </div>

          <Separator className="my-3" />
        </>
      )}

      {/* Navegación principal */}
      <nav aria-label="Secciones" className="flex flex-col gap-0.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = item.id === activeNavId;
          return (
            <Link
              key={item.id}
              to={item.to}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(navRowBase, active ? navRowActive : navRowInactive)}
            >
              {active && (
                <span
                  aria-hidden="true"
                  className="absolute top-1/2 left-0 h-[18px] w-[3px] -translate-y-1/2 rounded-xs bg-primary"
                />
              )}
              <Icon
                className={cn("h-[18px] w-[18px] shrink-0", active && "text-nav-accent")}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <Separator className="my-3" />

      {/* Cuenta */}
      <div className="flex flex-col gap-0.5">
        <Link
          to="/perfil"
          onClick={onNavigate}
          aria-current={pathname === "/perfil" ? "page" : undefined}
          className={cn(
            "flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal",
            focusRing,
          )}
        >
          <UserRound className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          Mi perfil
        </Link>
        <button
          type="button"
          onClick={logout}
          className={cn(
            "flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal",
            focusRing,
          )}
        >
          <LogOut className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          Cerrar sesión
        </button>
      </div>

      {/* Pie — estado de consentimiento */}
      <div className="mt-auto flex border-t border-border-gray px-1 pt-3">
        {!isConsentLoading && consentStatus && (
          <ConsentChip consentsPerAthlete={consentStatus.consents_per_athlete} />
        )}
      </div>
    </div>
  );
}
