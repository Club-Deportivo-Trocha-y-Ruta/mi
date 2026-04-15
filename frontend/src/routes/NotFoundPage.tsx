import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="rounded-xl bg-white p-8 text-center"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
      >
        <h1
          className="text-5xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          404
        </h1>
        <p className="mt-3 text-sm text-mid-gray">Ruta no encontrada.</p>
        <Link
          to="/dashboard"
          className="mt-6 inline-block rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
        >
          Volver al dashboard
        </Link>
      </div>
    </div>
  );
}
