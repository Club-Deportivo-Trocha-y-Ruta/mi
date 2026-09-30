/**
 * ReadinessPanel — huecos de datos por atleta antes de descargar la
 * planilla IMDERTY (feature 047, US3, T044).
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md`
 * `GET /api/clubs/{club_id}/imderty-sheet/readiness`. `display_name` solo se
 * muestra a admin/coach en pantalla (ya filtrado así por el backend) y
 * nunca se registra en logs — este componente no hace `console.*` con esos
 * valores.
 *
 * La descarga sigue habilitada aunque haya huecos (spec US3, acceptance
 * scenario 4): este panel es informativo, nunca bloquea el botón
 * "Descargar planilla" de `ImdertySheetPage`.
 *
 * Cada hueco enlaza al detalle del atleta (`/athletes/{id}#imderty-profile`,
 * ver `anchors.ts`) para que el
 * coach lo corrija — la sección "Perfil IMDERTY" vive ahí
 * (`components/imderty/ImdertyProfileCard.tsx`, montada en
 * `AthleteInfoCard.tsx` para admin/coach, US2/T034).
 */
import { CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { imdertyProfileHref } from "@/components/imderty/anchors";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableScrollContainer,
} from "@/components/ui/table";
import { useImdertySheetReadiness } from "@/hooks/useImderty";
import { extractErrorDetail } from "@/lib/apiError";
import type { ReadinessGap } from "@/schemas/imderty";

export interface ReadinessPanelProps {
  clubId: number;
  from: string;
  to: string;
}

/** Código de hueco → etiqueta en español (data-model.md, sección "Derived, not stored"). */
const GAP_LABELS: Record<string, string> = {
  missing_document: "Falta documento",
  missing_barrio: "Falta barrio",
  missing_eps: "Falta EPS",
  missing_phone: "Falta teléfono",
  no_guardian: "Sin acudiente vinculado",
  multiple_guardians_no_primary: "Varios acudientes sin contacto principal",
  surname_split_unconfirmed: "Apellidos sin confirmar",
  activity_without_record: "Actividad sin registro de asistencia",
};

function gapLabel(code: string): string {
  return GAP_LABELS[code] ?? code;
}

function gapChipLabel(code: string, activityDates: string[]): string {
  const base = gapLabel(code);
  if (code === "activity_without_record" && activityDates.length > 0) {
    return `${base} (${activityDates.length})`;
  }
  return base;
}

function GapChips({ gap }: { gap: ReadinessGap }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {gap.codes.map((code) => (
        <Badge key={code} variant="warning" title={gapLabel(code)}>
          {gapChipLabel(code, gap.activity_dates)}
        </Badge>
      ))}
    </div>
  );
}

function AthleteLink({ athleteId, children }: { athleteId: number; children: React.ReactNode }) {
  return (
    <Link
      to={imdertyProfileHref(athleteId)}
      className="text-sm font-medium text-link-blue underline-offset-2 hover:underline"
    >
      {children}
    </Link>
  );
}

function ReadinessSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando disponibilidad de datos…" className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-16 w-full" />
    </div>
  );
}

export function ReadinessPanel({ clubId, from, to }: ReadinessPanelProps) {
  const { data, isLoading, isError, error, refetch } = useImdertySheetReadiness(clubId, from, to);

  if (isLoading) {
    return <ReadinessSkeleton />;
  }

  if (isError) {
    return (
      <ErrorState
        message={extractErrorDetail(error, "No se pudo cargar la disponibilidad de datos.")}
        isColdStart={isColdStartError(error)}
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!data) return null;

  if (data.gaps.length === 0) {
    return (
      <Alert variant="success">
        <CheckCircle2 aria-hidden="true" />
        <AlertDescription>
          <strong>Todo listo</strong>. Los {data.athlete_count} atletas de este período no tienen
          datos pendientes para la planilla IMDERTY.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {/*
        Sin `AlertTitle` (h5) a propósito: esta sección ya vive bajo un `<h2>`
        de `ImdertySheetPage` sin un h3/h4 intermedio — usar el heading de
        Alert saltaría niveles (regla axe heading-order). El texto en negrita
        cumple el mismo rol visual sin semántica de encabezado.
      */}
      <Alert variant="warning">
        <AlertDescription>
          <strong>Hay datos pendientes</strong>. {data.gaps.length} de {data.athlete_count}{" "}
          atletas tienen datos faltantes o por confirmar. La planilla se puede descargar igual;
          esas celdas quedarán en blanco.
        </AlertDescription>
      </Alert>

      {/* Vista mobile: una card por atleta (<md) */}
      <ul role="list" className="flex flex-col gap-3 md:hidden">
        {data.gaps.map((gap) => (
          <li key={gap.athlete_id}>
            <div className="rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline">
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium text-charcoal">{gap.display_name}</span>
                <AthleteLink athleteId={gap.athlete_id}>Ver atleta</AthleteLink>
              </div>
              <div className="mt-2">
                <GapChips gap={gap} />
              </div>
            </div>
          </li>
        ))}
      </ul>

      {/* Vista desktop: tabla (md+) */}
      <div className="hidden md:block">
        <TableScrollContainer>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Atleta</TableHead>
                <TableHead>Pendientes</TableHead>
                <TableHead>
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.gaps.map((gap) => (
                <TableRow key={gap.athlete_id}>
                  <TableCell className="font-medium text-charcoal">{gap.display_name}</TableCell>
                  <TableCell>
                    <GapChips gap={gap} />
                  </TableCell>
                  <TableCell>
                    <AthleteLink athleteId={gap.athlete_id}>Ver atleta</AthleteLink>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableScrollContainer>
      </div>
    </div>
  );
}

export default ReadinessPanel;
