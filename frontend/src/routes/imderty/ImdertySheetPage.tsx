/**
 * ImdertySheetPage — planilla mensual de asistencia IMDERTY (feature 047).
 * Flujo: elegir un mes, ajustar el encabezado solo para esta descarga
 * (`HeaderOverridesForm`, US3/T044), revisar la disponibilidad de datos
 * (`ReadinessPanel`, US3/T044) y descargar el workbook oficial (FO-GDD-057),
 * con estados de carga/error/cold-start.
 *
 * Toggle «Un mes / Varios meses» (US4/T050): en modo rango, `from`/`to`
 * vienen de dos selectores de mes independientes, con el límite de 12
 * meses (contrato §Sheet — 422 más allá de eso) verificado también acá,
 * de forma optimista, para deshabilitar el botón con un mensaje en línea
 * en vez de esperar la respuesta del backend.
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md` §Sheet.
 */
import { useMemo, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { HeaderOverridesForm } from "@/components/imderty/HeaderOverridesForm";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { ReadinessPanel } from "@/components/imderty/ReadinessPanel";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useDownloadImdertySheet } from "@/hooks/useImderty";
import { extractErrorDetail } from "@/lib/apiError";
import { triggerBlobDownload } from "@/lib/download";
import { CLUB_TIMEZONE } from "@/lib/datetime";
import type { ImdertySheetHeaderValues } from "@/schemas/imderty";
import { useAuthStore } from "@/store/auth.store";

const MAX_RANGE_MONTHS = 12;

type PeriodMode = "single" | "range";

/**
 * Cantidad de meses calendario entre `from` y `to`, ambos inclusive
 * ("2026-08" a "2026-08" → 1; "2026-11" a "2027-02" → 4). Negativo cuando
 * `to` es anterior a `from`.
 */
function monthsInRange(from: string, to: string): number {
  const [fromYear, fromMonth] = from.split("-").map(Number);
  const [toYear, toMonth] = to.split("-").map(Number);
  return (toYear - fromYear) * 12 + (toMonth - fromMonth) + 1;
}

/** "YYYY-MM" del día de hoy en la zona horaria del club (no la del browser). */
function currentMonthInClubTz(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CLUB_TIMEZONE,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((p) => p.type === "year")?.value ?? "1970";
  const month = parts.find((p) => p.type === "month")?.value ?? "01";
  return `${year}-${month}`;
}

/** El mes calendario inmediatamente anterior a `month` ("YYYY-MM"). */
function previousMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, monthNumber - 1, 1));
  date.setUTCMonth(date.getUTCMonth() - 1);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/**
 * `downloadImdertySheet` pide `responseType: "blob"` (necesario para el
 * archivo bueno), así que axios NUNCA parsea el cuerpo de un error como
 * JSON: un 422 llega como `error.response.data` siendo un `Blob` con el
 * `detail` en español adentro, no un objeto. `extractErrorDetail` (que sí
 * sabe leer `.detail`) no puede verlo sin este paso previo. Los errores de
 * red/cold-start (sin `response`) pasan intactos.
 */
async function normalizeBlobError(err: unknown): Promise<unknown> {
  const candidate = err as { response?: { data?: unknown } } | null;
  const data = candidate?.response?.data;
  if (!(data instanceof Blob)) return err;
  try {
    const text = await data.text();
    const parsed = JSON.parse(text) as unknown;
    return { ...(err as object), response: { ...candidate!.response, data: parsed } };
  } catch {
    return err;
  }
}

export function ImdertySheetPage() {
  const clubId = useAuthStore((s) => s.user?.club_ids?.[0] ?? 1);
  const currentMonth = useMemo(() => currentMonthInClubTz(), []);
  const [month, setMonth] = useState(() => previousMonth(currentMonthInClubTz()));

  // Toggle «Un mes / Varios meses» (US4/T050). En modo "single" se sigue
  // usando `month` (from === to, comportamiento US1 sin cambios); en modo
  // "range" se usan `rangeFrom`/`rangeTo`, sembrados con el mismo mes por
  // defecto para que activar el toggle no deje el formulario vacío.
  const [periodMode, setPeriodMode] = useState<PeriodMode>("single");
  const [rangeFrom, setRangeFrom] = useState(() => previousMonth(currentMonthInClubTz()));
  const [rangeTo, setRangeTo] = useState(() => previousMonth(currentMonthInClubTz()));

  const from = periodMode === "range" ? rangeFrom : month;
  const to = periodMode === "range" ? rangeTo : month;
  const rangeLength = periodMode === "range" ? monthsInRange(from, to) : 1;
  const rangeTooLong = periodMode === "range" && rangeLength > MAX_RANGE_MONTHS;
  const rangeInverted = periodMode === "range" && rangeLength < 1;

  // Encabezado editable solo para esta descarga (US3/T044) — no hay
  // "guardar" propio: `save_header_as_default` viaja en el mismo POST y el
  // backend decide si persiste estos valores como configuración del club.
  // `null` hasta que `HeaderOverridesForm` termine de cargar la
  // configuración guardada del club: el contrato hace que un `header`
  // ausente (`null`) caiga de vuelta a esa configuración (§Sheet), así que
  // descargar en esa ventana breve debe seguir heredándola en vez de
  // mandar un objeto en blanco que la pisaría.
  const [headerOverride, setHeaderOverride] = useState<ImdertySheetHeaderValues | null>(null);
  const [saveHeaderAsDefault, setSaveHeaderAsDefault] = useState(false);

  const downloadSheet = useDownloadImdertySheet(clubId);
  const [downloadError, setDownloadError] = useState<unknown>(null);

  const isMonthInProgress = to === currentMonth;

  async function handleDownload() {
    setDownloadError(null);
    try {
      const { blob, filename } = await downloadSheet.mutateAsync({
        from,
        to,
        header: headerOverride,
        save_header_as_default: saveHeaderAsDefault,
      });
      triggerBlobDownload(blob, filename);
    } catch (err) {
      setDownloadError(await normalizeBlobError(err));
    }
  }

  const errorMessage = downloadError
    ? extractErrorDetail(downloadError, "No se pudo generar la planilla.")
    : null;
  const errorIsColdStart = Boolean(downloadError) && isColdStartError(downloadError);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Planilla IMDERTY"
        subtitle="Genera la planilla mensual de asistencia en el formato oficial FO-GDD-057."
      />

      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="space-y-1.5">
            <Label id="imderty-period-mode-label">Periodo</Label>
            <ToggleGroup
              type="single"
              variant="outline"
              value={periodMode}
              onValueChange={(value) => {
                if (value) setPeriodMode(value as PeriodMode);
              }}
              aria-labelledby="imderty-period-mode-label"
              className="w-fit"
            >
              <ToggleGroupItem value="single" className="min-h-12 px-4">
                Un mes
              </ToggleGroupItem>
              <ToggleGroupItem value="range" className="min-h-12 px-4">
                Varios meses
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {periodMode === "single" ? (
            <div className="space-y-1.5">
              <Label htmlFor="imderty-sheet-month">Mes</Label>
              <Input
                id="imderty-sheet-month"
                type="month"
                inputMode="numeric"
                value={month}
                max={currentMonth}
                onChange={(e) => setMonth(e.target.value)}
                className="max-w-xs"
              />
            </div>
          ) : (
            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="space-y-1.5">
                <Label htmlFor="imderty-sheet-range-from">Desde</Label>
                <Input
                  id="imderty-sheet-range-from"
                  type="month"
                  inputMode="numeric"
                  value={rangeFrom}
                  max={currentMonth}
                  onChange={(e) => setRangeFrom(e.target.value)}
                  className="max-w-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="imderty-sheet-range-to">Hasta</Label>
                <Input
                  id="imderty-sheet-range-to"
                  type="month"
                  inputMode="numeric"
                  value={rangeTo}
                  max={currentMonth}
                  onChange={(e) => setRangeTo(e.target.value)}
                  className="max-w-xs"
                />
              </div>
            </div>
          )}

          {rangeInverted && (
            <Alert variant="destructive">
              <AlertDescription>
                El mes «Hasta» no puede ser anterior al mes «Desde».
              </AlertDescription>
            </Alert>
          )}

          {rangeTooLong && (
            <Alert variant="destructive">
              <AlertDescription>
                El rango no puede superar los {MAX_RANGE_MONTHS} meses (elegiste {rangeLength}).
              </AlertDescription>
            </Alert>
          )}

          {isMonthInProgress && !rangeTooLong && !rangeInverted && (
            <Alert variant="warning">
              <AlertDescription>El mes aún no termina.</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          {/*
            `<h2>` nativo, no `CardTitle` (que renderiza `<h3>`): esta página
            no tiene un `<h2>` propio antes de esta sección, así que un `h3`
            saltaría un nivel bajo el `<h1>` de `PageHeader` (regla axe
            heading-order) — mismo patrón que `routes/training/ProjectProfilePage.tsx`.
          */}
          <h2 className="text-base font-semibold text-charcoal">Disponibilidad de datos</h2>
        </CardHeader>
        <CardContent>
          {rangeTooLong || rangeInverted ? (
            <p className="text-sm text-charcoal">
              Corrige el rango de meses para ver la disponibilidad de datos.
            </p>
          ) : (
            <ReadinessPanel clubId={clubId} from={from} to={to} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-base font-semibold text-charcoal">Encabezado de la planilla</h2>
        </CardHeader>
        <CardContent>
          <HeaderOverridesForm
            clubId={clubId}
            saveAsDefault={saveHeaderAsDefault}
            onSaveAsDefaultChange={setSaveHeaderAsDefault}
            onChange={setHeaderOverride}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 pt-5">
          <Button
            type="button"
            size="lg"
            className="w-full sm:w-auto"
            onClick={() => void handleDownload()}
            disabled={downloadSheet.isPending || !from || !to || rangeTooLong || rangeInverted}
          >
            {downloadSheet.isPending ? (
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <Download size={16} aria-hidden="true" />
            )}
            Descargar planilla
          </Button>

          {errorMessage && (
            <ErrorState
              message={errorMessage}
              isColdStart={errorIsColdStart}
              onRetry={handleDownload}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ImdertySheetPage;
