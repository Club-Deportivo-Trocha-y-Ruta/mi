/**
 * AlertsCard — Card de alertas críticas para padres (Wave 4).
 *
 * Por ahora la única alerta P0 es **consentimiento parental vencido o
 * nunca otorgado** (ConsentStatusPanel ya lo gestiona dentro, y el modal
 * bloqueante en ParentDashboardPage lo fuerza). Este card es un
 * "headline" del problema visible en el feed por si el padre cerró el
 * modal accidentalmente (no debería poder, pero defensa) o por si
 * cargamos la home con el consentimiento revocado (revocados no entran
 * en la cola bloqueante).
 *
 * Si no hay alertas → no renderiza nada. NO renderizamos un placeholder
 * "todo en orden" — sería ruido visual en el feed cuando no aplica.
 *
 * Estructura del consentStatus:
 *   - current_consent === null              → nunca dio consentimiento
 *   - current_consent.withdrawn_at !== null → revocado
 *   - !current_consent.is_current_policy     → política desactualizada
 */
import { AlertTriangle, ShieldOff } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { AthleteConsentStatus } from "@/types/consent";

interface ConsentIssue {
  athleteName: string;
  reason: "missing" | "outdated" | "withdrawn";
}

function classify(item: AthleteConsentStatus): ConsentIssue | null {
  const c = item.current_consent;
  if (c === null) {
    return { athleteName: item.athlete_name, reason: "missing" };
  }
  if (c.withdrawn_at !== null) {
    return { athleteName: item.athlete_name, reason: "withdrawn" };
  }
  if (!c.is_current_policy) {
    return { athleteName: item.athlete_name, reason: "outdated" };
  }
  return null;
}

function reasonLabel(reason: ConsentIssue["reason"]): string {
  switch (reason) {
    case "missing":
      return "Falta autorizar el tratamiento de datos.";
    case "outdated":
      return "La política de privacidad cambió. Revisa y actualiza tu autorización.";
    case "withdrawn":
      return "Tu autorización fue revocada — el club no puede registrar datos hasta que la renueves.";
  }
}

interface AlertsCardProps {
  consentsPerAthlete: AthleteConsentStatus[] | undefined;
  isLoading: boolean;
}

export function AlertsCard({ consentsPerAthlete, isLoading }: AlertsCardProps) {
  // Loading: no mostramos un skeleton específico — la cola bloqueante
  // del modal y el ConsentStatusPanel ya muestran sus propios estados,
  // y no queremos un flash de "alerta" en el feed durante la carga.
  if (isLoading || !consentsPerAthlete) return null;

  const issues = consentsPerAthlete
    .map(classify)
    .filter((i): i is ConsentIssue => i !== null);

  if (issues.length === 0) return null;

  return (
    <Card
      role="region"
      aria-label="Alertas pendientes"
      data-testid="alerts-card"
      className="border-l-4 border-l-amber-500"
    >
      <div className="flex items-start gap-3 px-5 py-4">
        <AlertTriangle
          size={22}
          aria-hidden="true"
          className="mt-0.5 shrink-0 text-amber-600"
        />
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-charcoal">
            Atención: requiere tu autorización
          </p>
          <ul className="mt-2 space-y-2">
            {issues.map((issue, idx) => (
              <li
                key={`${issue.athleteName}-${idx}`}
                className="flex items-start gap-2 text-sm text-charcoal"
              >
                <ShieldOff
                  size={14}
                  aria-hidden="true"
                  className="mt-0.5 shrink-0 text-amber-600"
                />
                <span>
                  <span className="font-medium">{issue.athleteName}: </span>
                  <span className="text-mid-gray">{reasonLabel(issue.reason)}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-text-disclaimer">
            Renueva tu autorización desde el panel de privacidad más abajo.
          </p>
        </div>
      </div>
    </Card>
  );
}
