import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-4">
      <div className="rounded-card bg-surface-raised p-8 text-center shadow-card ring-1 ring-hairline">
        <h1
          className="font-display text-5xl text-charcoal"
        >
          404
        </h1>
        <p className="mt-3 text-sm text-mid-gray">Ruta no encontrada.</p>
        <Link
          to="/dashboard"
          className="mt-6 inline-flex min-h-12 items-center justify-center rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-surface transition-opacity hover:opacity-70 shadow-button-highlight"
        >
          Volver al dashboard
        </Link>
      </div>
    </div>
  );
}
