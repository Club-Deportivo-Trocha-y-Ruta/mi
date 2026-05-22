/**
 * AthleteSwitcher — Selector compacto del "hijo activo" para el portal de padres.
 *
 * Wave 4: vive en el header del AppShell (solo para rol parent). Su
 * comportamiento depende de cuántos atletas tenga vinculado el padre:
 *
 *   - **0 atletas**: no renderiza nada (defensa — el AppShell verifica).
 *   - **1 atleta**: render estático (avatar + nombre + edad/categoría). No
 *     interactivo: no tiene sentido un dropdown con una sola opción.
 *   - **2+ atletas**: render como `DropdownMenu` shadcn con:
 *       • Item "Ver todos" (id null) — para que la home apile cards por hijo.
 *       • Un item por atleta — selección via setActiveAthlete.
 *
 * Accesibilidad:
 *   - `aria-label="Cambiar atleta activo"` en el trigger del dropdown.
 *   - Cambio anunciado por live region (sr-only) para que SR confirme
 *     "Atleta activo: Santiago López" tras la elección.
 *
 * Avatar: iniciales de nombre/apellido sobre fondo de la marca. No usamos
 * radix-avatar (más peso del que justifica un componente tan simple).
 */
import { useState } from "react";
import { ChevronDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useActiveAthlete } from "@/hooks/parents/useActiveAthlete";
import { cn } from "@/lib/utils";
import type { MyAthleteOut } from "@/types/parent.types";

function getInitials(first: string, last: string): string {
  const f = (first?.trim().charAt(0) ?? "").toUpperCase();
  const l = (last?.trim().charAt(0) ?? "").toUpperCase();
  const combined = `${f}${l}`;
  return combined || "·";
}

function ageSubtitle(athlete: MyAthleteOut): string {
  const parts: string[] = [];
  if (athlete.age_decimal !== null) {
    parts.push(`${athlete.age_decimal.toFixed(1)} años`);
  }
  if (athlete.category) {
    parts.push(athlete.category);
  }
  return parts.join(" · ");
}

function fullName(athlete: MyAthleteOut): string {
  return `${athlete.athlete_first_name} ${athlete.athlete_last_name}`.trim();
}

interface AvatarProps {
  initials: string;
  /** "sm" para uso dentro del item del dropdown. "md" para el trigger. */
  size?: "sm" | "md";
}

function Avatar({ initials, size = "md" }: AvatarProps) {
  const sizeClass = size === "sm" ? "h-7 w-7 text-xs" : "h-9 w-9 text-sm";
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-primary/15 font-semibold text-primary",
        sizeClass,
      )}
    >
      {initials}
    </span>
  );
}

export function AthleteSwitcher() {
  const { athletes, athlete, activeAthleteId, setActiveAthlete, isLoading } =
    useActiveAthlete();
  // Live region para confirmar el cambio. Recuperar el nombre del estado
  // de zustand directamente sería más simple, pero queremos anunciar
  // solo cuando el usuario elige, no en el render inicial.
  const [announcement, setAnnouncement] = useState("");

  if (isLoading || athletes.length === 0) {
    return null;
  }

  // -----------------------------------------------------------------------
  // Caso 1: un solo atleta — label estático, no interactivo
  // -----------------------------------------------------------------------
  if (athletes.length === 1) {
    const only = athletes[0];
    return (
      <div
        className="flex min-w-0 items-center gap-2"
        data-testid="athlete-switcher-single"
      >
        <Avatar
          initials={getInitials(only.athlete_first_name, only.athlete_last_name)}
        />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-charcoal">
            {fullName(only)}
          </p>
          {ageSubtitle(only) && (
            <p className="truncate text-xs text-mid-gray">{ageSubtitle(only)}</p>
          )}
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Caso 2: 2+ atletas — DropdownMenu shadcn
  // -----------------------------------------------------------------------
  const triggerLabel = athlete ? fullName(athlete) : "Todos mis atletas";
  const triggerInitials = athlete
    ? getInitials(athlete.athlete_first_name, athlete.athlete_last_name)
    : "··";

  function handleSelect(id: number | null, displayName: string) {
    setActiveAthlete(id);
    setAnnouncement(`Atleta activo: ${displayName}`);
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Cambiar atleta activo"
          className={cn(
            "flex min-h-11 min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-light-gray",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
          )}
          data-testid="athlete-switcher-trigger"
        >
          <Avatar initials={triggerInitials} />
          <span className="hidden min-w-0 flex-col sm:flex">
            <span className="truncate text-sm font-medium text-charcoal">
              {triggerLabel}
            </span>
            {athlete && ageSubtitle(athlete) && (
              <span className="truncate text-xs text-mid-gray">
                {ageSubtitle(athlete)}
              </span>
            )}
          </span>
          <ChevronDown
            size={14}
            aria-hidden="true"
            className="ml-0.5 shrink-0 text-mid-gray"
          />
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="min-w-[15rem]">
          <DropdownMenuLabel>Atleta activo</DropdownMenuLabel>

          <DropdownMenuItem
            data-testid="athlete-switcher-item-all"
            onSelect={() => handleSelect(null, "Todos mis atletas")}
            className={cn(
              "flex items-center gap-2",
              activeAthleteId === null && "font-semibold",
            )}
            aria-current={activeAthleteId === null ? "true" : undefined}
          >
            <Avatar initials="··" size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">Todos mis atletas</span>
              <span className="block text-xs text-mid-gray">
                Ver feed por cada hijo
              </span>
            </span>
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          {athletes.map((a) => {
            const isActive = a.athlete_id === activeAthleteId;
            const name = fullName(a);
            return (
              <DropdownMenuItem
                key={a.athlete_id}
                data-testid={`athlete-switcher-item-${a.athlete_id}`}
                onSelect={() => handleSelect(a.athlete_id, name)}
                className={cn(
                  "flex items-center gap-2",
                  isActive && "font-semibold",
                )}
                aria-current={isActive ? "true" : undefined}
              >
                <Avatar
                  initials={getInitials(
                    a.athlete_first_name,
                    a.athlete_last_name,
                  )}
                  size="sm"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{name}</span>
                  {ageSubtitle(a) && (
                    <span className="block truncate text-xs text-mid-gray">
                      {ageSubtitle(a)}
                    </span>
                  )}
                </span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>
    </>
  );
}
