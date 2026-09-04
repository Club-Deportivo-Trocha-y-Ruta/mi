/**
 * FamilyStageCard — tarjeta "Etapa de desarrollo" en lenguaje familiar
 * (feature 040, US4, T058), per `contracts/growth-tab-ui.md` (mockup §5.2 de
 * `docs/18-growth-module-redesign/proposal.md`): una frase de etapa sin
 * jerga clínica ("Tu hijo/a está…") más la fecha de la última evaluación
 * ofuscada a "mes año".
 *
 * La frase reutiliza el texto exacto de `phvParentMessage`
 * (`routes/parents/MyAthleteDetailPage.tsx`) — deliberadamente duplicado en
 * vez de importado: esa página sigue gobernando su propio bloque "Estado
 * PHV" hasta que un wave posterior (T062) la reemplace por `GrowthTab` en
 * modo padre, y esta tarea no toca ese archivo (fuera de la lista de
 * ownership). Si el texto de `phvParentMessage` cambia, actualizar también
 * esta copia hasta que T062 retire el bloque duplicado de la página.
 *
 * D2 ("la etapa PHV NUNCA lleva color propio", ya aplicado en
 * `GrowthStatusRow::EtapaTile` del lado coach): esta tarjeta tampoco tiñe el
 * fondo por etapa (el antiguo bloque de `MyAthleteDetailPage.tsx` resaltaba
 * Circa-PHV en ámbar con clases Tailwind crudas) — mismo texto en un único
 * estilo neutro, sin banda de color que "never sea el único canal" tenga que
 * respetar (no hay banda aquí, solo una frase).
 *
 * Privacidad (Ley 1581): la fecha de evaluación se ofusca a "mes año" (ej.
 * "ago 2026"), nunca el día exacto — mismo criterio que
 * `PercentileChart.tsx::formatMonthYear` / `PercentileTable.tsx::formatMonthYear`,
 * duplicado aquí a propósito por el mismo motivo que esos dos archivos
 * documentan (no acoplar este componente a los suyos).
 */
import { Card, CardContent } from "@/components/ui/card";
import { MaturationStatus, Sex } from "@/types/enums";

export interface FamilyStageCardProps {
  /** `GrowthSummary.stage` — `null` cuando aún no hay mediciones. */
  stage: MaturationStatus | null;
  /** `GrowthSummary.latest_evaluation_date` (ISO `YYYY-MM-DD`) o `null`. */
  latestEvaluationDate: string | null;
  sex: Sex;
}

const MONTH_NAMES_ES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/** Privacidad: ofusca la fecha completa de evaluación a "mes año" (ej. "ene 2026"). */
function formatMonthYear(isoDate: string | null): string | null {
  if (!isoDate) return null;
  const [yearStr, monthStr] = isoDate.split("-");
  const monthIdx = Number(monthStr) - 1;
  if (monthIdx < 0 || monthIdx > 11 || Number.isNaN(monthIdx)) return isoDate;
  return `${MONTH_NAMES_ES[monthIdx]} ${yearStr}`;
}

/**
 * Frase de etapa en lenguaje familiar — copia exacta de `phvParentMessage`
 * (`routes/parents/MyAthleteDetailPage.tsx:98`). `null` cuando la etapa aún
 * no se conoce (sin mediciones) — el llamador (`GrowthTab`) no debería
 * montar esta tarjeta en ese caso, pero se maneja de forma defensiva.
 */
function stageMessage(stage: MaturationStatus | null, sex: Sex): string | null {
  const pronoun = sex === Sex.F ? "hija" : "hijo";
  if (stage === MaturationStatus.PrePHV) {
    return `Tu ${pronoun} está en etapa de desarrollo temprano`;
  }
  if (stage === MaturationStatus.CircaPHV) {
    return `Tu ${pronoun} está en su pico de crecimiento — etapa clave`;
  }
  if (stage === MaturationStatus.PostPHV) {
    return `El crecimiento de tu ${pronoun} se está estabilizando`;
  }
  return null;
}

export function FamilyStageCard({ stage, latestEvaluationDate, sex }: FamilyStageCardProps) {
  const message = stageMessage(stage, sex);
  if (!message) return null;

  const evaluated = formatMonthYear(latestEvaluationDate);

  return (
    <Card data-testid="family-stage-card">
      <CardContent className="flex flex-col gap-1.5">
        <p className="text-sm text-mid-gray">Etapa de desarrollo</p>
        <p className="text-base font-medium text-charcoal">{message}</p>
        {evaluated && <p className="text-xs text-mid-gray">Evaluado en {evaluated}</p>}
      </CardContent>
    </Card>
  );
}
