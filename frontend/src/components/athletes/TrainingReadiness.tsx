import { AlertCircle, AlertTriangle, ChevronDown } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { PHVBadge } from "@/components/athletes/PHVBadge";
import {
  differsFromDefault,
  rulesFor,
  type AgeGroup,
  type RuleStatus,
  type Stage,
  type TrainingRule,
} from "@/lib/growth/rules";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { MaturationStatus } from "@/types/enums";
import type { GrowthSummary } from "@/types/growth.types";

interface TrainingReadinessProps {
  athlete: AthleteDetailOut;
  latestRecord?: AnthropometricRecord;
  /**
   * Alertas del resumen de crecimiento (`useGrowthSummary`). Cuando se
   * provee, sustituye por completo el cálculo local `buildAlerts` — cuando
   * es `undefined` (uso independiente, p. ej. en las pruebas del
   * componente) se conserva ese cálculo local para que el componente siga
   * funcionando de forma autónoma.
   */
  alerts?: GrowthSummary["alerts"];
}

interface AlertItem {
  level: "warning" | "danger";
  message: string;
}

/** Mapeo de `RuleStatus` (lib/growth/rules.ts) a `StatusBadge` (icono + etiqueta, nunca solo color). */
const STATUS_BADGE: Record<RuleStatus, { status: Status; label: string }> = {
  allowed: { status: "success", label: "Permitido" },
  caution: { status: "warning", label: "Con cuidado" },
  forbidden: { status: "danger", label: "No permitido" },
};

function getAgeGroup(ageDecimal: number | null): AgeGroup | null {
  if (ageDecimal === null) return null;
  if (ageDecimal >= 10 && ageDecimal < 13) return "10-12";
  if (ageDecimal >= 13 && ageDecimal <= 15) return "13-15";
  return null;
}

/**
 * Alertas calculadas a partir del `GrowthSummary.alerts` del backend
 * (mismo vocabulario que `contracts/growth-summary-api.md`). Solo se
 * traducen a mensaje los tres códigos con implicación directa sobre las
 * reglas de entrenamiento; `rapid_growth` / `approaching_circa` /
 * `phase_changed` se muestran en `GrowthAlerts` (fuera de este bloque).
 */
function buildAlertsFromSummary(
  summaryAlerts: GrowthSummary["alerts"],
): AlertItem[] {
  const alerts: AlertItem[] = [];

  if (summaryAlerts.includes("circa_phv")) {
    alerts.push({
      level: "warning",
      message:
        "Fase de máxima vulnerabilidad ósea. Vigilar Osgood-Schlatter. Priorizar técnica sobre condición.",
    });
  }
  if (summaryAlerts.includes("height_p3")) {
    alerts.push({
      level: "danger",
      message: "Talla muy baja (P<3). Derivar a médico.",
    });
  }
  if (summaryAlerts.includes("bmi_p3")) {
    alerts.push({
      level: "danger",
      message: "Delgadez severa (P<3). Derivar a nutricionista.",
    });
  }

  return alerts;
}

/** Cálculo local de respaldo — usado cuando el componente se renderiza sin `alerts` (uso independiente). */
function buildAlerts(
  latestRecord: AnthropometricRecord | undefined,
  isCircaPHV: boolean,
): AlertItem[] {
  const alerts: AlertItem[] = [];

  if (isCircaPHV) {
    alerts.push({
      level: "warning",
      message:
        "Fase de máxima vulnerabilidad ósea. Vigilar Osgood-Schlatter. Priorizar técnica sobre condición.",
    });
  }

  if (latestRecord) {
    const hp = latestRecord.height_percentile != null ? Number(latestRecord.height_percentile) : null;
    if (hp !== null && hp < 3) {
      alerts.push({
        level: "danger",
        message: "Talla muy baja (P<3). Derivar a médico.",
      });
    }
    const bp = latestRecord.bmi_percentile != null ? Number(latestRecord.bmi_percentile) : null;
    if (bp !== null && bp < 3) {
      alerts.push({
        level: "danger",
        message: "Delgadez severa (P<3). Derivar a nutricionista.",
      });
    }
  }

  return alerts;
}

interface RuleRowProps {
  rule: TrainingRule;
}

function RuleRow({ rule }: RuleRowProps) {
  const badge = STATUS_BADGE[rule.status];
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border-gray bg-white p-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-charcoal">{rule.topic}</p>
        <p className="mt-0.5 text-xs text-mid-gray">{rule.text}</p>
      </div>
      <StatusBadge status={badge.status} label={badge.label} />
    </div>
  );
}

export function TrainingReadiness({ athlete, latestRecord, alerts }: TrainingReadinessProps) {
  const ageGroup = getAgeGroup(athlete.age_decimal);
  const matStatus = latestRecord?.maturation_status ?? null;
  const isCircaPHV = matStatus === MaturationStatus.CircaPHV;

  if (ageGroup === null) {
    return (
      <div className="rounded-xl bg-white p-5 shadow-card" data-testid="growth-rules">
        <h4
          className="font-display mb-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          Qué cambia en el entrenamiento
        </h4>
        <p className="text-sm text-mid-gray">
          Rango de edad fuera del modelo (10-15 años).
        </p>
      </div>
    );
  }

  const stage: Stage = matStatus ?? "any";
  const rules = rulesFor(ageGroup, stage);
  const changedRules = rules.filter(differsFromDefault);
  const alertItems = alerts !== undefined ? buildAlertsFromSummary(alerts) : buildAlerts(latestRecord, isCircaPHV);

  return (
    <div className="rounded-xl bg-white p-5 space-y-4 shadow-card" data-testid="growth-rules">
      {/* Header */}
      <div>
        <h4
          className="font-display text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          Qué cambia en el entrenamiento
        </h4>
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            {athlete.age_decimal?.toFixed(1) ?? "—"} años
          </span>
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            {athlete.category ?? "Sin categoría"}
          </span>
          {matStatus && <PHVBadge status={matStatus} />}
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            Grupo: {ageGroup} años
          </span>
        </div>
      </div>

      {/* Alertas */}
      {alertItems.length > 0 && (
        <div className="space-y-2">
          {alertItems.map((alert, idx) => (
            <Alert key={idx} variant={alert.level === "danger" ? "destructive" : "warning"}>
              {alert.level === "danger" ? (
                <AlertCircle aria-hidden="true" />
              ) : (
                <AlertTriangle aria-hidden="true" />
              )}
              <AlertDescription>{alert.message}</AlertDescription>
            </Alert>
          ))}
        </div>
      )}

      {/* Reglas que difieren del plan base del grupo de edad */}
      {changedRules.length > 0 ? (
        <div className="space-y-2">
          {changedRules.map((rule) => (
            <RuleRow key={rule.id} rule={rule} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-mid-gray">
          Sin cambios respecto al plan base para este grupo de edad.
        </p>
      )}

      {/* Detalle completo de las nueve reglas */}
      <Collapsible>
        <CollapsibleTrigger className="flex min-h-12 w-full items-center justify-between gap-2 rounded-lg border border-border-gray px-3 text-sm font-medium text-charcoal transition-colors hover:bg-light-gray [&[data-state=open]_svg]:rotate-180">
          Ver todas las reglas
          <ChevronDown size={16} aria-hidden="true" className="shrink-0 transition-transform" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="grid gap-2 pt-2 sm:grid-cols-2 lg:grid-cols-3">
            {rules.map((rule) => (
              <RuleRow key={rule.id} rule={rule} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Nota al pie */}
      <p
        className="text-xs text-mid-gray pt-3"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.08)" }}
      >
        Decisiones basadas en edad biológica (PHV), no cronológica. Marco LTAD /
        principios no negociables.
      </p>
    </div>
  );
}
