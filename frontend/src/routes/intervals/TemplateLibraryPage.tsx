/**
 * TemplateLibraryPage — página de la biblioteca de templates de intervalos
 * (feature 026 / US4). Ruta lazy `/intervals/templates`.
 *
 * Compone únicamente `TemplatePicker` en modo solo-navegación (sin
 * `trainingSessionId`): explorar y filtrar la biblioteca del club por las tres
 * etiquetas (categoría de edad / fase de mesociclo / proximidad a competencia).
 * El adjunto de un template a una sesión vive en la vista de detalle de sesión,
 * no en la biblioteca (allí no hay una sesión de contexto).
 *
 * Coach/admin only — el gating vive en `App.tsx` vía `ProtectedRoute`; el
 * backend responde 403 a padres/atletas en todo `/api/intervals` (FR-018).
 * Espeja la topología de `routes/strength/CatalogPage.tsx`.
 */
import { TemplatePicker } from "@/components/intervals/TemplatePicker";

export function TemplateLibraryPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-slate-900">
          Biblioteca de intervalos
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Explorá y filtrá los templates de estructuras de intervalos del club
          por categoría de edad, fase de mesociclo y proximidad a competencia.
          Para adjuntar un template a una sesión, abrí el detalle de la sesión.
        </p>
      </div>

      <TemplatePicker />
    </div>
  );
}

export default TemplateLibraryPage;
