/**
 * SiblingViewTabs — fila de pastillas de navegación secundaria compartida.
 *
 * Promueve el patrón existente en `CompetitionDetailPage` (TAB_VALUES /
 * TAB_LABELS / TabTrigger sobre `@radix-ui/react-tabs`) a un componente
 * reutilizable dirigido por rutas reales (cada "sibling view" es su propia
 * ruta, no un `TabsPrimitive.Content` interno).
 *
 * Uso: se renderiza como fila propia de ancho completo directamente debajo
 * del `<h1>` de la página (vía `PageHeader` o equivalente) — **nunca** dentro
 * del slot `actions` de `PageHeader` (alineado a la derecha / con forma de
 * botón, per `specs/028-frontend-design-foundation/contracts/shared-components.md`).
 * Mezclar ambos patrones rompe el reflow bajo ~380px.
 *
 * La pastilla activa se resuelve comparando `location.pathname` contra cada
 * `item.to` (coincidencia exacta o de prefijo de segmento). La navegación
 * real ocurre a través de `NavLink` — Radix Tabs solo aporta la mecánica de
 * teclado (roving tabindex, flechas, Home/End) y el estilo `data-[state=active]`;
 * no controla el contenido.
 *
 * Per `research.md` R4.
 */
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

export interface SiblingViewTabsItem {
  label: string;
  to: string;
}

export interface SiblingViewTabsProps {
  items: SiblingViewTabsItem[];
  /** Etiqueta accesible de la lista de pastillas (default: "Vistas relacionadas"). */
  "aria-label"?: string;
  className?: string;
}

/**
 * Determina qué `item.to` corresponde a la ruta actual.
 *
 * Las vistas hermanas de una misma área comparten un prefijo de ruta común
 * (p. ej. Válidas → `/competitions`, Sin enlazar → `/competitions/unlinked`,
 * Panorama → `/competitions/insights/season/2026`), así que un simple
 * `startsWith` de primer-match confundiría "Válidas" con activa en
 * `/competitions/unlinked`. Se prioriza la coincidencia **exacta** primero;
 * solo si ninguna pastilla coincide exactamente se cae a coincidencia de
 * prefijo (`pathname` empieza por `item.to + "/"`), y entre varios prefijos
 * gana el más largo (más específico) — mismo criterio de longest-prefix que
 * `isAreaActive` en `lib/navigation.ts`.
 */
function resolveActiveTo(
  items: SiblingViewTabsItem[],
  pathname: string,
): string | undefined {
  const exactMatch = items.find((item) => item.to === pathname);
  if (exactMatch) return exactMatch.to;

  const prefixMatches = items.filter((item) =>
    pathname.startsWith(`${item.to}/`),
  );
  if (prefixMatches.length === 0) return undefined;

  return prefixMatches.reduce((longest, item) =>
    item.to.length > longest.to.length ? item : longest,
  ).to;
}

export function SiblingViewTabs({
  items,
  "aria-label": ariaLabel = "Vistas relacionadas",
  className,
}: SiblingViewTabsProps) {
  const location = useLocation();
  const activeTo = resolveActiveTo(items, location.pathname);

  return (
    <TabsPrimitive.Root value={activeTo} className={cn("w-full", className)}>
      <TabsPrimitive.List
        className="flex gap-1 overflow-x-auto rounded-xl bg-light-gray p-1 scrollbar-none"
        aria-label={ariaLabel}
      >
        {items.map((item) => (
          <TabsPrimitive.Trigger key={item.to} value={item.to} asChild>
            <NavLink
              to={item.to}
              end
              className="flex min-h-11 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
            >
              {item.label}
            </NavLink>
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {/*
        Cada vista hermana es una ruta real (su "contenido" vive en otra
        página), no un panel local — por eso estos `Content` van vacíos.
        Sin ellos, el `aria-controls` que Radix genera automáticamente en
        cada Trigger apuntaría a un id inexistente (violación axe
        aria-valid-attr-value); estos paneles vacíos le dan un destino
        válido sin ocupar espacio visual ni duplicar contenido.
      */}
      {items.map((item) => (
        <TabsPrimitive.Content key={item.to} value={item.to} tabIndex={-1} />
      ))}
    </TabsPrimitive.Root>
  );
}
