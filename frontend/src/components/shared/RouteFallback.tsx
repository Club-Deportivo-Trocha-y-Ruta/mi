interface RouteFallbackProps {
  /** Mensaje de carga a mostrar, p. ej. "Cargando sesiones...". */
  label: string;
}

/**
 * RouteFallback — fallback de `<Suspense>` para las rutas cargadas de forma
 * perezosa en App.tsx. Unifica los ~21 `<div>` idénticos duplicados ahí,
 * y añade role="status"/aria-live="polite" (ausente en el original) para que
 * los lectores de pantalla anuncien la carga de la ruta.
 */
export function RouteFallback({ label }: RouteFallbackProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[40vh] items-center justify-center text-sm text-mid-gray"
    >
      {label}
    </div>
  );
}
