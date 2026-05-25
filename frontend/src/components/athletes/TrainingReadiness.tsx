import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { MaturationStatus } from "@/types/enums";

interface TrainingReadinessProps {
  athlete: AthleteDetailOut;
  latestRecord?: AnthropometricRecord;
}

type RuleStatus = "allowed" | "caution" | "forbidden";
type AgeGroup = "10-12" | "13-15";

interface TrainingRule {
  id: string;
  label: string;
  status: RuleStatus;
  detail: string;
}

interface AlertItem {
  level: "warning" | "danger";
  message: string;
}

const STATUS_ICON: Record<RuleStatus, string> = {
  allowed: "✓",
  caution: "⚠",
  forbidden: "✗",
};

const STATUS_COLORS: Record<RuleStatus, { icon: string; bg: string; text: string; border: string }> = {
  allowed: {
    icon: "text-green-600",
    bg: "bg-green-50",
    text: "text-green-800",
    border: "border-green-200",
  },
  caution: {
    icon: "text-yellow-600",
    bg: "bg-yellow-50",
    text: "text-yellow-800",
    border: "border-yellow-200",
  },
  forbidden: {
    icon: "text-red-600",
    bg: "bg-red-50",
    text: "text-red-800",
    border: "border-red-200",
  },
};

function getAgeGroup(ageDecimal: number | null): AgeGroup | null {
  if (ageDecimal === null) return null;
  if (ageDecimal >= 10 && ageDecimal < 13) return "10-12";
  if (ageDecimal >= 13 && ageDecimal <= 15) return "13-15";
  return null;
}

function buildRules(
  ageGroup: AgeGroup,
  isCircaPHV: boolean,
): TrainingRule[] {
  const rules: TrainingRule[] = [
    isCircaPHV
      ? {
          id: "high-intensity",
          label: "Intervalos alta intensidad",
          status: "forbidden",
          detail: "Prohibido en Circa-PHV",
        }
      : ageGroup === "10-12"
      ? {
          id: "high-intensity",
          label: "Intervalos alta intensidad",
          status: "forbidden",
          detail: "Prohibido en 10-12 años — solo juego libre",
        }
      : {
          id: "high-intensity",
          label: "Intervalos alta intensidad",
          status: "caution",
          detail: "Max 2 sesiones/semana",
        },

    isCircaPHV
      ? {
          id: "bodyweight",
          label: "Fuerza peso corporal",
          status: "caution",
          detail: "Volumen reducido — Circa-PHV",
        }
      : {
          id: "bodyweight",
          label: "Fuerza peso corporal",
          status: "allowed",
          detail: "Permitido en todos los grupos",
        },

    isCircaPHV
      ? {
          id: "external-load",
          label: "Fuerza peso externo",
          status: "forbidden",
          detail: "Prohibido en Circa-PHV",
        }
      : ageGroup === "10-12"
      ? {
          id: "external-load",
          label: "Fuerza peso externo",
          status: "forbidden",
          detail: "Prohibido en 10-12 años",
        }
      : {
          id: "external-load",
          label: "Fuerza peso externo",
          status: "caution",
          detail: "Progresión: bandas → mancuernas",
        },

    isCircaPHV
      ? {
          id: "weekly-hours",
          label: "Horas/semana",
          status: "caution",
          detail: "Reducir 20-30% del plan habitual",
        }
      : ageGroup === "10-12"
      ? {
          id: "weekly-hours",
          label: "Horas/semana",
          status: "allowed",
          detail: "3-5 h/semana (edad mínima regla)",
        }
      : {
          id: "weekly-hours",
          label: "Horas/semana",
          status: "allowed",
          detail: "5-10 h/semana",
        },

    {
      id: "cadence",
      label: "Cadencia mínima",
      status: "allowed",
      detail:
        isCircaPHV || ageGroup === "13-15"
          ? "75 rpm — nunca < 60 rpm"
          : "70 rpm — nunca < 60 rpm",
    },

    isCircaPHV
      ? {
          id: "max-hr",
          label: "Test FC máxima",
          status: "forbidden",
          detail: "Prohibido en Circa-PHV — estimada: 197 lpm",
        }
      : ageGroup === "10-12"
      ? {
          id: "max-hr",
          label: "Test FC máxima",
          status: "forbidden",
          detail: "Estimada: 197 lpm — sin test",
        }
      : {
          id: "max-hr",
          label: "Test FC máxima",
          status: "allowed",
          detail: "Permitido con supervisión",
        },

    isCircaPHV
      ? {
          id: "powermeter",
          label: "Potenciómetro",
          status: "forbidden",
          detail: "Prohibido en Circa-PHV",
        }
      : ageGroup === "10-12"
      ? {
          id: "powermeter",
          label: "Potenciómetro",
          status: "forbidden",
          detail: "Prohibido en menores de 13 años",
        }
      : {
          id: "powermeter",
          label: "Potenciómetro",
          status: "allowed",
          detail: "Permitido (solo > 13 años)",
        },

    {
      id: "intensity",
      label: "Distribución Z1-Z2 / Z3-Z5",
      status: "allowed",
      detail:
        isCircaPHV || ageGroup === "10-12" ? "90% / 10%" : "80% / 20%",
    },

    {
      id: "ratio",
      label: "Ratio entreno:competencia",
      status: "allowed",
      detail:
        isCircaPHV || ageGroup === "10-12" ? "70 : 30" : "60 : 40",
    },
  ];

  return rules;
}

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
        message: "Talla muy baja (P<3). Derivar a medico.",
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

const PHV_LABELS: Record<MaturationStatus, string> = {
  [MaturationStatus.PrePHV]: "Pre-PHV",
  [MaturationStatus.CircaPHV]: "Circa-PHV",
  [MaturationStatus.PostPHV]: "Post-PHV",
};

const PHV_BADGE_COLORS: Record<MaturationStatus, string> = {
  [MaturationStatus.PrePHV]: "bg-blue-100 text-blue-800",
  [MaturationStatus.CircaPHV]: "bg-amber-100 text-amber-800",
  [MaturationStatus.PostPHV]: "bg-green-100 text-green-800",
};

interface RuleCardProps {
  rule: TrainingRule;
}

function RuleCard({ rule }: RuleCardProps) {
  const colors = STATUS_COLORS[rule.status];
  return (
    <div className={`rounded-lg border p-3 ${colors.bg} ${colors.border}`}>
      <div className="flex items-start gap-2">
        <span className={`text-base font-bold leading-tight ${colors.icon}`}>
          {STATUS_ICON[rule.status]}
        </span>
        <div className="min-w-0">
          <p className={`text-sm font-medium ${colors.text}`}>{rule.label}</p>
          <p className={`mt-0.5 text-xs opacity-80 ${colors.text}`}>{rule.detail}</p>
        </div>
      </div>
    </div>
  );
}

export function TrainingReadiness({ athlete, latestRecord }: TrainingReadinessProps) {
  const ageGroup = getAgeGroup(athlete.age_decimal);
  const matStatus = latestRecord?.maturation_status ?? null;
  const isCircaPHV = matStatus === MaturationStatus.CircaPHV;

  if (ageGroup === null) {
    return (
      <div
        className="rounded-xl bg-white p-5"
      >
        <h4
          className="mb-2 text-sm text-charcoal font-heading tracking-[0.2px]"
        >
          Recomendaciones de entrenamiento
        </h4>
        <p className="text-sm text-mid-gray">
          Rango de edad fuera del modelo (10-15 años).
        </p>
      </div>
    );
  }

  const rules = buildRules(ageGroup, isCircaPHV);
  const alerts = buildAlerts(latestRecord, isCircaPHV);

  return (
    <div
      className="rounded-xl bg-white p-5 space-y-4"
    >
      {/* Header */}
      <div>
        <h4
          className="text-sm text-charcoal font-heading tracking-[0.2px]"
        >
          Recomendaciones de entrenamiento
        </h4>
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            {athlete.first_name} {athlete.last_name}
          </span>
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            {athlete.age_decimal?.toFixed(1) ?? "—"} años
          </span>
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            {athlete.category ?? "Sin categoría"}
          </span>
          {matStatus && (
            <span className={`rounded-full px-2.5 py-1 font-medium ${PHV_BADGE_COLORS[matStatus]}`}>
              {PHV_LABELS[matStatus]}
            </span>
          )}
          <span className="rounded-full bg-light-gray px-2.5 py-1 text-charcoal">
            Grupo: {ageGroup} años
          </span>
        </div>
      </div>

      {/* Alertas */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((alert, idx) => (
            <div
              key={idx}
              className={`rounded-lg border p-3 text-sm ${
                alert.level === "danger"
                  ? "border-red-200 bg-red-50 text-red-800"
                  : "border-amber-200 bg-amber-50 text-amber-800"
              }`}
            >
              {alert.level === "danger" ? "⬤ " : "⚠ "}
              {alert.message}
            </div>
          ))}
        </div>
      )}

      {/* Grid de reglas */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rules.map((rule) => (
          <RuleCard key={rule.id} rule={rule} />
        ))}
      </div>

      {/* Nota al pie */}
      <p
        className="text-xs text-mid-gray pt-3"
      >
        Decisiones basadas en edad biológica (PHV), no cronológica. Marco LTAD /
        principios no negociables.
      </p>
    </div>
  );
}
