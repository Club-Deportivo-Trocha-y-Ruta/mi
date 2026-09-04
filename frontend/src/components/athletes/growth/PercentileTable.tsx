/**
 * PercentileTable — vista tabular de las mediciones del atleta para el
 * indicador activo (feature 040, US3, T051): mes-año, edad, valor, Z,
 * percentil y banda, per `contracts/growth-tab-ui.md`. Reemplaza la tabla
 * `sr-only` de `PercentileCurves.tsx` (eliminada en T052) como alternativa
 * visible al `role="img"` de `PercentileChart.tsx` cuando `view === "table"`.
 *
 * Cada fila usa `useGrowthMetrics` (mismo hook que `PercentileInterpretationBlock`
 * y `NutritionalClassification`) para priorizar el Z-score/percentil
 * almacenados en el backend (OMS) sobre el cálculo LMS local. Se delega a un
 * `<PercentileTableRow>` por registro — invocar el hook dentro de un
 * `.map()` del componente padre violaría las Reglas de Hooks; un
 * subcomponente por fila es el patrón correcto (mismo número de hooks en
 * cada instancia, cada una independiente).
 */
import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useGrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";
import { getBandVocabulary } from "@/lib/growth/bands";
import type { GrowthIndicator } from "@/lib/growth/lms";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

export interface PercentileTableProps {
  records: AnthropometricRecord[];
  indicator: GrowthIndicator;
  sex: "M" | "F";
  birthDate: string;
}

const VALUE_FORMATTER: Record<GrowthIndicator, (value: number) => string> = {
  height_for_age: (value) => `${value.toFixed(1)} cm`,
  bmi_for_age: (value) => `${value.toFixed(1)} kg/m²`,
  weight_for_age: (value) => `${value.toFixed(1)} kg`,
};

const MONTH_NAMES_ES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/**
 * Privacidad (Ley 1581): ofusca la fecha completa de evaluación a "mes año"
 * (ej. "ene 2026") en vez de mostrar el día exacto — mismo criterio que
 * `PercentileCurves.tsx::formatMonthYear`, duplicado a propósito aquí para
 * no acoplar esta tabla al componente que se elimina en T052.
 */
function formatMonthYear(isoDate: string): string {
  const [yearStr, monthStr] = isoDate.split("-");
  const monthIdx = Number(monthStr) - 1;
  if (monthIdx < 0 || monthIdx > 11 || Number.isNaN(monthIdx)) return isoDate;
  return `${MONTH_NAMES_ES[monthIdx]} ${yearStr}`;
}

function formatZScore(z: number): string {
  return z >= 0 ? `+${z.toFixed(2)}` : z.toFixed(2);
}

interface PercentileTableRowProps {
  record: AnthropometricRecord;
  indicator: GrowthIndicator;
  sex: "M" | "F";
  birthDate: string;
}

/**
 * Una fila por registro — `null` cuando `useGrowthMetrics` no puede calcular
 * el indicador para este registro (valor inválido o edad fuera del rango de
 * referencia OMS 5–19 años), mismo criterio de omisión que la tabla sr-only
 * que reemplaza.
 */
function PercentileTableRow({ record, indicator, sex, birthDate }: PercentileTableRowProps) {
  const metrics = useGrowthMetrics({ record, sex, birthDate, indicator });
  if (metrics === null) return null;

  const vocab = getBandVocabulary(indicator, metrics.band);

  return (
    <TableRow>
      <TableCell>{formatMonthYear(record.evaluation_date)}</TableCell>
      <TableCell className="tabular-nums">{(metrics.ageMonths / 12).toFixed(1)} años</TableCell>
      <TableCell className="tabular-nums">{VALUE_FORMATTER[indicator](metrics.value)}</TableCell>
      <TableCell className="tabular-nums">{formatZScore(metrics.zScore)}</TableCell>
      <TableCell className="tabular-nums">P{Math.round(metrics.percentile)}</TableCell>
      <TableCell>
        <StatusBadge status={vocab.tone} label={vocab.coachLabel} />
      </TableCell>
    </TableRow>
  );
}

export function PercentileTable({ records, indicator, sex, birthDate }: PercentileTableProps) {
  // Más reciente primero — mismo criterio que `AnthropometryHistory.tsx`.
  const sorted = [...records].sort(
    (a, b) => new Date(b.evaluation_date).getTime() - new Date(a.evaluation_date).getTime(),
  );

  if (sorted.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray" data-testid="growth-curve-table">
        Sin mediciones
      </p>
    );
  }

  return (
    <Table data-testid="growth-curve-table">
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Mes</TableHead>
          <TableHead scope="col">Edad</TableHead>
          <TableHead scope="col">Valor</TableHead>
          <TableHead scope="col">Z</TableHead>
          <TableHead scope="col">Percentil</TableHead>
          <TableHead scope="col">Banda</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((record) => (
          <PercentileTableRow
            key={record.id}
            record={record}
            indicator={indicator}
            sex={sex}
            birthDate={birthDate}
          />
        ))}
      </TableBody>
    </Table>
  );
}
