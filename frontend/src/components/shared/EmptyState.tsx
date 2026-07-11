import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * EmptyState — bloque centrado reutilizable para listas/tablas sin datos.
 * Estructura tomada del empty-state de CompetitionsListPage (ícono +
 * título + descripción + acción, todos opcionales salvo el título).
 */
interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode; // p. ej. un botón de "crear nuevo"
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="rounded-xl bg-white px-6 py-12 text-center shadow-card">
      {Icon && <Icon size={44} className="mx-auto mb-3 text-mid-gray" aria-hidden="true" />}
      <p className="text-sm font-medium text-charcoal">{title}</p>
      {description && <p className="mt-1 text-xs text-mid-gray">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
