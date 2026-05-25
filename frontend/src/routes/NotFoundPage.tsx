import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="rounded-xl bg-white p-8 text-center"
      >
        <h1
          className="text-5xl text-charcoal font-heading"
        >
          404
        </h1>
        <p className="mt-3 text-sm text-mid-gray">Ruta no encontrada.</p>
        <Link
          to="/dashboard"
          className="mt-6 inline-block rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70"
        >
          Volver al dashboard
        </Link>
      </div>
    </div>
  );
}
