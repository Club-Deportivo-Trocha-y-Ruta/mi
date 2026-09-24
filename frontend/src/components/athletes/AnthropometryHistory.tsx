import { useRef, useState } from "react";

import { AnthropometricRecordExplanationCard } from "@/components/ai/AnthropometricRecordExplanationCard";
import { PHVBadge } from "@/components/athletes/PHVBadge";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMeasurementExplanationCached } from "@/hooks/ai/useMeasurementExplanation";
import type { AnthropometricRecordExplanationResponse } from "@/types/ai.types";
import { ageAtEvaluation, SKINFOLD_MIN_AGE_YEARS } from "@/lib/bodyComposition/eligibility";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

interface AnthropometryHistoryProps {
  records: AnthropometricRecord[];
  isLoading: boolean;
  /** ID del atleta — necesario para invocar la IA particular por medición.
   *  Cuando se omite, la sección de análisis IA no se renderiza. */
  athleteId?: number;
  /** Modo de usuario: 'coach' permite generar/regenerar, 'parent' solo lee. */
  mode?: "coach" | "parent";
  /**
   * Feature 046 (T031): acción de fila "Agregar pliegues" / "Editar
   * pliegues" (sólo coach). El llamador navega al asistente de captura.
   * Si se omite, la columna de acción no se renderiza.
   */
  onSkinfoldsAction?: (record: AnthropometricRecord) => void;
}

/** La evaluación ya tiene un set de pliegues (el backend lo manda `null` a padres). */
function hasSkinfolds(record: AnthropometricRecord): boolean {
  return record.skinfolds != null;
}

/**
 * La acción de fila se ofrece para editar un set existente, o para agregar
 * uno cuando el deportista tenía ≥ 9 años en esa fecha. El intervalo mínimo
 * entre sets lo valida el backend (409 explicado en el asistente).
 */
function canOfferSkinfoldsAction(record: AnthropometricRecord): boolean {
  if (hasSkinfolds(record)) return true;
  const age = ageAtEvaluation(record);
  return age !== null && age >= SKINFOLD_MIN_AGE_YEARS;
}

function SkinfoldsMarker() {
  return (
    <span
      data-testid="history-skinfolds-marker"
      className="inline-flex items-center whitespace-nowrap rounded-full bg-light-gray px-2 py-0.5 text-[11px] font-medium text-charcoal"
    >
      Pliegues
    </span>
  );
}

function SkinfoldsActionButton({
  record,
  onAction,
}: {
  record: AnthropometricRecord;
  onAction: (record: AnthropometricRecord) => void;
}) {
  const label = hasSkinfolds(record) ? "Editar pliegues" : "Agregar pliegues";
  return (
    <button
      type="button"
      onClick={(event) => {
        // La fila de escritorio abre el detalle al hacer clic: no propagar.
        event.stopPropagation();
        onAction(record);
      }}
      aria-label={`${label} de la medición del ${formatDate(record.evaluation_date)}`}
      className="inline-flex min-h-[48px] items-center whitespace-nowrap rounded-lg px-3 text-xs font-medium text-link-blue ring-1 ring-hairline transition-colors hover:bg-light-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue/50"
    >
      {label}
    </button>
  );
}

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatOffset(offset: number | string): string {
  const n = typeof offset === "string" ? parseFloat(offset) : offset;
  return n > 0 ? `+${n.toFixed(2)}` : n.toFixed(2);
}

/** `true` cuando el análisis IA cacheado de la medición trae al menos una
 *  señal de aviso (feature 042, FR-028/SC-005). Una fila `"v1"` (sin
 *  `structured`) nunca activa la marca. */
function hasWarningSigns(
  data: AnthropometricRecordExplanationResponse | null | undefined,
): boolean {
  if (!data || data.schema_version !== "v2") return false;
  return data.structured.warning_signs.length > 0;
}

/**
 * Marca "Con señal para revisar" para UNA fila del histórico (FR-028), sin
 * abrir el modal — lee el mismo slot de caché (`audience="family"`, igual
 * criterio que `AnthropometricRecordExplanationCard`) sin disparar
 * generación nueva.
 *
 * La compuerta familiar (FR-016) ya vive en el backend: para un padre, una
 * fila `flagged`/`fallback`/`skipped` llega como `204` — indistinguible de
 * "sin análisis todavía" (`_family_gate_blocks` en `routers/ai.py`) — así
 * que esta marca nunca delata a una familia que existe un análisis
 * retenido para revisión. Para el coach, el mismo `204` solo significa que
 * aún no se generó nada; cualquier fila generada (incluida una marcada
 * "Con observaciones") sí expone sus señales de aviso, si las tiene.
 */
function HistoryRowWarningMarker({
  athleteId,
  recordId,
}: {
  athleteId: number;
  recordId: number;
}) {
  const cachedQuery = useMeasurementExplanationCached(athleteId, recordId, true);
  if (!hasWarningSigns(cachedQuery.data)) return null;
  return (
    <span
      data-testid="history-warning-marker"
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800"
    >
      <span aria-hidden="true">⚠</span>
      Con señal para revisar
    </span>
  );
}

export function AnthropometryHistory({
  records,
  isLoading,
  athleteId,
  mode = "coach",
  onSkinfoldsAction,
}: AnthropometryHistoryProps) {
  const [selectedRecord, setSelectedRecord] =
    useState<AnthropometricRecord | null>(null);
  // FR-031: el foco debe volver al control que abrió el diálogo. Radix lo
  // hace solo cuando el disparador es un `DialogTrigger`; aquí el diálogo es
  // controlado y hay N filas, así que Radix no puede saber CUÁL de ellas lo
  // abrió y el foco terminaba en `document.body`. Guardamos el elemento y lo
  // restauramos nosotros en `onCloseAutoFocus`.
  const triggerRef = useRef<HTMLElement | null>(null);

  const openRecord = (
    record: AnthropometricRecord,
    event: React.MouseEvent<HTMLElement>
  ) => {
    triggerRef.current = event.currentTarget;
    setSelectedRecord(record);
  };
  // FR-016 (feature 040, US4): la familia nunca ve el offset de madurez, la
  // etiqueta clínica de etapa ni la edad estimada del PHV — esos campos son
  // exclusivos del coach. En modo padre el historial se limita a las medidas.
  const showClinical = mode === "coach";
  // Feature 046: marcador "Pliegues" y acción de fila — sólo coach.
  const skinfoldsAction = showClinical ? onSkinfoldsAction : undefined;
  const showSkinfoldsColumn =
    showClinical && (!!skinfoldsAction || records.some(hasSkinfolds));

  const sorted = [...records].sort(
    (a, b) =>
      new Date(b.evaluation_date).getTime() -
      new Date(a.evaluation_date).getTime(),
  );

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, idx) => (
          <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
        ))}
      </div>
    );
  }

  if (sorted.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray">
        No hay mediciones registradas aún.
      </p>
    );
  }

  return (
    <>
      {/* Vista mobile: lista de cards (<md) */}
      <ul role="list" className="flex flex-col gap-2 md:hidden" data-testid="anthropometry-history">
        {sorted.map((record) => (
          <li key={record.id}>
            <button
              type="button"
              className="w-full cursor-pointer rounded-card bg-surface-raised p-4 text-left shadow-card ring-1 ring-hairline transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue/50"
              onClick={(event) => openRecord(record, event)}
              aria-label={`Ver detalle de medición del ${formatDate(record.evaluation_date)}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <span className="text-sm font-medium text-charcoal" data-testid="record-date">
                    {formatDate(record.evaluation_date)}
                  </span>
                  {athleteId !== undefined && athleteId > 0 && (
                    <HistoryRowWarningMarker athleteId={athleteId} recordId={record.id} />
                  )}
                </span>
                {showClinical && <PHVBadge status={record.maturation_status} />}
              </div>
              {showClinical && hasSkinfolds(record) && (
                <div className="mt-2">
                  <SkinfoldsMarker />
                </div>
              )}
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <span className="text-mid-gray">Peso: <span className="text-charcoal">{record.weight_kg} kg</span></span>
                <span className="text-mid-gray">Talla: <span className="text-charcoal">{record.standing_height_cm} cm</span></span>
                <span className="text-mid-gray">Sentado: <span className="text-charcoal">{record.sitting_height_cm} cm</span></span>
                {showClinical && (
                  <span className="text-mid-gray">Offset: <span className="font-medium text-charcoal">{formatOffset(record.maturity_offset)}</span></span>
                )}
                {record.arm_span_cm != null && (
                  <span className="text-mid-gray">Enverg.: <span className="text-charcoal">{record.arm_span_cm} cm</span></span>
                )}
              </div>
            </button>
            {skinfoldsAction && canOfferSkinfoldsAction(record) && (
              <div className="mt-1 flex justify-end">
                <SkinfoldsActionButton record={record} onAction={skinfoldsAction} />
              </div>
            )}
          </li>
        ))}
      </ul>

      {/* Vista desktop: tabla (md+) */}
      <div className="hidden overflow-x-auto md:block" data-testid="anthropometry-history-desktop">
        <table className="min-w-full text-sm">
          <thead
            className="text-left"
            style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
          >
            <tr>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Fecha</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Envergadura</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Peso</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Talla</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Talla sentado</th>
              {showClinical && (
                <>
                  <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Offset</th>
                  <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Estado PHV</th>
                  <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Edad PHV</th>
                </>
              )}
              {showSkinfoldsColumn && (
                <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Pliegues</th>
              )}
            </tr>
          </thead>
          <tbody>
            {sorted.map((record) => (
              <tr
                key={record.id}
                className="cursor-pointer transition-colors hover:bg-light-gray"
                style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                onClick={(event) => openRecord(record, event)}
              >
                <td className="px-3 py-2.5 text-charcoal">
                  <span className="flex items-center gap-2">
                    <span data-testid="record-date">{formatDate(record.evaluation_date)}</span>
                    {athleteId !== undefined && athleteId > 0 && (
                      <HistoryRowWarningMarker athleteId={athleteId} recordId={record.id} />
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-mid-gray">
                  {record.arm_span_cm != null ? `${record.arm_span_cm} cm` : "-"}
                </td>
                <td className="px-3 py-2.5 text-charcoal">{record.weight_kg} kg</td>
                <td className="px-3 py-2.5 text-charcoal">{record.standing_height_cm} cm</td>
                <td className="px-3 py-2.5 text-charcoal">{record.sitting_height_cm} cm</td>
                {showClinical && (
                  <>
                    <td className="px-3 py-2.5 font-medium text-charcoal">
                      {formatOffset(record.maturity_offset)}
                    </td>
                    <td className="px-3 py-2.5">
                      <PHVBadge status={record.maturation_status} />
                    </td>
                    <td className="px-3 py-2.5 text-mid-gray">{record.age_at_phv} años</td>
                  </>
                )}
                {showSkinfoldsColumn && (
                  <td className="px-3 py-2.5">
                    <span className="flex items-center gap-2">
                      {hasSkinfolds(record) && <SkinfoldsMarker />}
                      {skinfoldsAction && canOfferSkinfoldsAction(record) && (
                        <SkinfoldsActionButton record={record} onAction={skinfoldsAction} />
                      )}
                    </span>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal de detalle — primitiva compartida (feature 042, T075): foco
          trapado, cierre con Escape y foco devuelto al disparador vienen
          gratis de Radix (`ui/dialog.tsx`), en vez de reimplementarlos a
          mano como antes (FR-028/FR-031). */}
      <Dialog
        open={selectedRecord !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedRecord(null);
        }}
      >
        <DialogContent
          hideClose
          className="max-w-3xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            triggerRef.current?.focus();
          }}
        >
          {selectedRecord && (
            <>
              {/* Control de cierre ≥48 px de alto (FR-031) — el de
                  `DialogContent` por defecto es más pequeño, así que se
                  reemplaza con `hideClose` + este botón propio. */}
              <DialogClose
                aria-label="Cerrar"
                className="absolute right-3 top-3 inline-flex min-h-[48px] min-w-[48px] items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal focus:outline-none focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
              >
                <span aria-hidden="true" className="text-lg leading-none">
                  ✕
                </span>
              </DialogClose>

              <DialogHeader>
                <DialogTitle>
                  Medición del {formatDate(selectedRecord.evaluation_date)}
                </DialogTitle>
                <DialogDescription>
                  Detalle de la medición registrada
                  {showClinical
                    ? ", incluidas las notas clínicas del coach y el análisis de IA si está disponible."
                    : " y el análisis de IA si está disponible."}
                </DialogDescription>
              </DialogHeader>

              <DialogBody
                className="overflow-y-auto"
                style={{ maxHeight: "70dvh" }}
              >
                <div className="grid grid-cols-2 gap-3 text-sm text-charcoal sm:grid-cols-3">
                  <p>Peso: {selectedRecord.weight_kg} kg</p>
                  <p>Talla: {selectedRecord.standing_height_cm} cm</p>
                  <p>Talla sentado: {selectedRecord.sitting_height_cm} cm</p>
                  <p>
                    Envergadura: {selectedRecord.arm_span_cm ?? "No registrada"}{" "}
                    {selectedRecord.arm_span_cm ? "cm" : ""}
                  </p>
                  <p>Long. pierna: {selectedRecord.leg_length_cm} cm</p>
                  <p>Ratio pierna/sentado: {selectedRecord.leg_sitting_ratio}</p>
                  {showClinical && (
                    <>
                      <p>Maturity Offset: {formatOffset(selectedRecord.maturity_offset)}</p>
                      <p>Edad al PHV: {selectedRecord.age_at_phv} años</p>
                      <div className="flex items-center gap-2">
                        <span>Estado:</span>
                        <PHVBadge status={selectedRecord.maturation_status} />
                      </div>
                    </>
                  )}
                </div>

                {showClinical && selectedRecord.training_implications && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                    <p className="mb-1 font-medium">Implicaciones de entrenamiento:</p>
                    <p>{selectedRecord.training_implications}</p>
                  </div>
                )}

                {selectedRecord.notes && (
                  <div className="mt-3 rounded-lg bg-light-gray p-3 text-sm text-mid-gray">
                    <p className="mb-1 font-medium text-charcoal">Notas:</p>
                    <p>{selectedRecord.notes}</p>
                  </div>
                )}

                {athleteId !== undefined && athleteId > 0 && (
                  <div
                    className="mt-5 pt-4"
                    style={{ borderTop: "1px solid rgba(34, 42, 53, 0.08)" }}
                    data-testid="anthropometry-record-explanation-section"
                  >
                    <AnthropometricRecordExplanationCard
                      athleteId={athleteId}
                      recordId={selectedRecord.id}
                      readOnly={mode === "parent"}
                    />
                  </div>
                )}
              </DialogBody>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
