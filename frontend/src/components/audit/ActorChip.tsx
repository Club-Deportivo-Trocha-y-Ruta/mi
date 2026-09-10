/**
 * ActorChip — nombre de un actor (adulto o proceso automático) para las
 * superficies de auditoría/atribución (feature 041 — gobernanza
 * multi-coach, FR-013). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §7.2.
 *
 * El id numérico crudo **nunca** se renderiza — ese es el problema que
 * resuelve esta feature (§7.3: "Creado por usuario ID" era la única
 * excepción en todo el frontend, ver `components/competitions/tabs/InfoTab.tsx`).
 *
 * Orden de resolución (§7.2):
 *   1. `displayName` ya resuelto (p. ej. filas de auditoría, filas del
 *      informe de actividad por entrenador) → se usa tal cual.
 *   2. `actorKind` distinto de `"user"`, o `userId === null` → "Proceso
 *      automático" (un caller que sí conoce la etiqueta específica —p. ej.
 *      "Sistema"/"Tarea programada" de `audit_log`— debe pasarla como
 *      `displayName`; este componente no reinventa esas etiquetas).
 *   3. `userId` numérico sin `displayName` → se resuelve contra el
 *      directorio de personal (`useStaff`, coach+admin, activos e
 *      inactivos) — mientras carga: `Skeleton`; si no aparece: "Usuario no
 *      disponible".
 *
 * La insignia "Inactivo" es neutra (ícono + texto, nunca solo color,
 * constitution III) y se muestra siempre que se conozca `is_active === false`,
 * ya sea porque el caller lo pasó directamente (`isActive`, caso de
 * `coaches[].coach.is_active` del informe) o porque se resolvió desde el
 * directorio.
 *
 * Privacidad (Ley 1581): este componente SOLO resuelve personal adulto
 * (`useStaff` → `role in {coach, admin}`) — nunca debe recibir un id de
 * deportista.
 */
import { useStaff } from "@/hooks/admin/useStaff";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { cn } from "@/lib/utils";

export interface ActorChipProps {
  userId: number | null;
  /** Nombre ya resuelto (las filas de auditoría lo traen; InfoTab no). */
  displayName?: string | null;
  /** Cuando el autor no fue una persona — viene de la fila de auditoría. */
  actorKind?: "user" | "system" | "webhook" | "cron";
  isActive?: boolean;
  className?: string;
}

const AUTOMATED_LABEL = "Proceso automático";
const UNAVAILABLE_LABEL = "Usuario no disponible";

function InactiveBadge() {
  return (
    <span data-testid="actor-chip-inactive-badge">
      <StatusBadge status="neutral" label="Inactivo" />
    </span>
  );
}

export function ActorChip({
  userId,
  displayName,
  actorKind,
  isActive,
  className,
}: ActorChipProps) {
  // Caso 1: nombre ya resuelto por el caller.
  if (displayName) {
    return (
      <span
        className={cn("inline-flex items-center gap-1.5", className)}
        data-testid="actor-chip"
      >
        <span className="text-charcoal">{displayName}</span>
        {isActive === false && <InactiveBadge />}
      </span>
    );
  }

  // Caso 2: actor no humano, o sin id — sin nombre que resolver.
  if (userId === null || (actorKind !== undefined && actorKind !== "user")) {
    return (
      <span
        className={cn("text-mid-gray", className)}
        data-testid="actor-chip"
      >
        {AUTOMATED_LABEL}
      </span>
    );
  }

  // Caso 3: solo tenemos el id — se resuelve contra el directorio de personal.
  return (
    <ActorChipFromDirectory
      userId={userId}
      isActive={isActive}
      className={className}
    />
  );
}

function ActorChipFromDirectory({
  userId,
  isActive,
  className,
}: {
  userId: number;
  isActive?: boolean;
  className?: string;
}) {
  const staffQuery = useStaff();

  if (staffQuery.isLoading) {
    return (
      <Skeleton
        className={cn("h-4 w-24", className)}
        data-testid="actor-chip-skeleton"
      />
    );
  }

  const staffMember = staffQuery.data?.items.find((u) => u.id === userId);

  if (!staffMember) {
    return (
      <span
        className={cn("text-mid-gray", className)}
        data-testid="actor-chip"
      >
        {UNAVAILABLE_LABEL}
      </span>
    );
  }

  const resolvedIsActive = isActive ?? staffMember.is_active;

  return (
    <span
      className={cn("inline-flex items-center gap-1.5", className)}
      data-testid="actor-chip"
    >
      <span className="text-charcoal">
        {staffMember.first_name} {staffMember.last_name}
      </span>
      {resolvedIsActive === false && <InactiveBadge />}
    </span>
  );
}
