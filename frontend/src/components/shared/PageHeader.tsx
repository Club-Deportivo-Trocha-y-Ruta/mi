import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

/**
 * Encabezado de página estándar: título (font-display/Cal Sans), subtítulo
 * opcional, back-link de un solo nivel (sin breadcrumbs) y slot de acciones
 * alineado a la derecha. Reemplaza los ~59 <h1> y 16 back-links ad hoc.
 */
interface PageHeaderProps {
  title: string;
  subtitle?: string;
  backTo?: { to: string; label: string };
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, backTo, actions }: PageHeaderProps) {
  return (
    <div className="space-y-3">
      {backTo && (
        <Link
          to={backTo.to}
          className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          {backTo.label}
        </Link>
      )}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display text-2xl font-semibold text-charcoal">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-mid-gray">{subtitle}</p>}
        </div>

        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}
