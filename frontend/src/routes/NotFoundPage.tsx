import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">404</h1>
        <p className="mt-2 text-sm text-slate-600">Ruta no encontrada.</p>
        <Link
          to="/dashboard"
          className="mt-4 inline-block rounded-md bg-slate-900 px-4 py-2 text-sm text-white"
        >
          Volver al dashboard
        </Link>
      </div>
    </div>
  );
}
