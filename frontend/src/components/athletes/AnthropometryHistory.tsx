import { useState } from "react";

import { AnthropometricRecordExplanationCard } from "@/components/ai/AnthropometricRecordExplanationCard";
import { PHVBadge } from "@/components/shared/PHVBadge";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

interface AnthropometryHistoryProps {
  records: AnthropometricRecord[];
  isLoading: boolean;
  /** ID del atleta — necesario para invocar la IA particular por medición.
   *  Cuando se omite, la sección de análisis IA no se renderiza. */
  athleteId?: number;
  /** Modo de usuario: 'coach' permite generar/regenerar, 'parent' solo lee. */
  mode?: "coach" | "parent";
}

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

function formatOffset(offset: number | string): string {
  const n = typeof offset === "string" ? parseFloat(offset) : offset;
  return n > 0 ? `+${n.toFixed(2)}` : n.toFixed(2);
}

export function AnthropometryHistory({
  records,
  isLoading,
  athleteId,
  mode = "coach",
}: AnthropometryHistoryProps) {
  const [selectedRecord, setSelectedRecord] =
    useState<AnthropometricRecord | null>(null);

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
              className="w-full cursor-pointer rounded-xl bg-white p-4 text-left transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue/50"
              style={{
                boxShadow:
                  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
              }}
              onClick={() => setSelectedRecord(record)}
              aria-label={`Ver detalle de medición del ${formatDate(record.evaluation_date)}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-charcoal" data-testid="record-date">
                  {formatDate(record.evaluation_date)}
                </span>
                <PHVBadge status={record.maturation_status} />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <span className="text-mid-gray">Peso: <span className="text-charcoal">{record.weight_kg} kg</span></span>
                <span className="text-mid-gray">Talla: <span className="text-charcoal">{record.standing_height_cm} cm</span></span>
                <span className="text-mid-gray">Sentado: <span className="text-charcoal">{record.sitting_height_cm} cm</span></span>
                <span className="text-mid-gray">Offset: <span className="font-medium text-charcoal">{formatOffset(record.maturity_offset)}</span></span>
                {record.arm_span_cm != null && (
                  <span className="text-mid-gray">Enverg.: <span className="text-charcoal">{record.arm_span_cm} cm</span></span>
                )}
              </div>
            </button>
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
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Offset</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Estado PHV</th>
              <th className="px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-mid-gray">Edad PHV</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((record) => (
              <tr
                key={record.id}
                className="cursor-pointer transition-colors hover:bg-light-gray"
                style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                onClick={() => setSelectedRecord(record)}
              >
                <td className="px-3 py-2.5 text-charcoal" data-testid="record-date">
                  {formatDate(record.evaluation_date)}
                </td>
                <td className="px-3 py-2.5 text-mid-gray">
                  {record.arm_span_cm != null ? `${record.arm_span_cm} cm` : "-"}
                </td>
                <td className="px-3 py-2.5 text-charcoal">{record.weight_kg} kg</td>
                <td className="px-3 py-2.5 text-charcoal">{record.standing_height_cm} cm</td>
                <td className="px-3 py-2.5 text-charcoal">{record.sitting_height_cm} cm</td>
                <td className="px-3 py-2.5 font-medium text-charcoal">
                  {formatOffset(record.maturity_offset)}
                </td>
                <td className="px-3 py-2.5">
                  <PHVBadge status={record.maturation_status} />
                </td>
                <td className="px-3 py-2.5 text-mid-gray">{record.age_at_phv} años</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal de detalle */}
      {selectedRecord && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-midnight/40"
          onClick={() => setSelectedRecord(null)}
        >
          <div
            className="mx-4 w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6"
            style={{
              maxHeight: "85dvh",
              boxShadow:
                "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="mb-4 flex items-center justify-between pb-3"
              style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
            >
              <h3
                className="text-base text-charcoal"
                style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
              >
                Medición del {formatDate(selectedRecord.evaluation_date)}
              </h3>
              <button
                type="button"
                onClick={() => setSelectedRecord(null)}
                className="text-mid-gray transition-colors hover:text-charcoal"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm text-charcoal">
              <p>Peso: {selectedRecord.weight_kg} kg</p>
              <p>Talla: {selectedRecord.standing_height_cm} cm</p>
              <p>Talla sentado: {selectedRecord.sitting_height_cm} cm</p>
              <p>
                Envergadura: {selectedRecord.arm_span_cm ?? "No registrada"}{" "}
                {selectedRecord.arm_span_cm ? "cm" : ""}
              </p>
              <p>Long. pierna: {selectedRecord.leg_length_cm} cm</p>
              <p>Ratio pierna/sentado: {selectedRecord.leg_sitting_ratio}</p>
              <p>Maturity Offset: {formatOffset(selectedRecord.maturity_offset)}</p>
              <p>Edad al PHV: {selectedRecord.age_at_phv} años</p>
              <div className="flex items-center gap-2">
                <span>Estado:</span>
                <PHVBadge status={selectedRecord.maturation_status} />
              </div>
            </div>

            {selectedRecord.training_implications && (
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
          </div>
        </div>
      )}
    </>
  );
}
