import { useState } from "react";

import { PHVBadge } from "@/components/shared/PHVBadge";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

interface AnthropometryHistoryProps {
  records: AnthropometricRecord[];
  isLoading: boolean;
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
          <div key={idx} className="h-9 animate-pulse rounded bg-slate-100" />
        ))}
      </div>
    );
  }

  if (sorted.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-slate-500">
        No hay mediciones registradas aun.
      </p>
    );
  }

  return (
    <>
      <div className="overflow-x-auto" data-testid="anthropometry-history">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Fecha</th>
              <th className="px-3 py-2 font-medium">Mesociclo</th>
              <th className="px-3 py-2 font-medium">Peso</th>
              <th className="px-3 py-2 font-medium">Talla</th>
              <th className="px-3 py-2 font-medium">Talla sentado</th>
              <th className="px-3 py-2 font-medium">Offset</th>
              <th className="px-3 py-2 font-medium">Estado PHV</th>
              <th className="px-3 py-2 font-medium">Edad PHV</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((record) => (
              <tr
                key={record.id}
                className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                onClick={() => setSelectedRecord(record)}
              >
                <td className="px-3 py-2" data-testid="record-date">
                  {formatDate(record.evaluation_date)}
                </td>
                <td className="px-3 py-2">{record.mesocycle ?? "-"}</td>
                <td className="px-3 py-2">{record.weight_kg} kg</td>
                <td className="px-3 py-2">{record.standing_height_cm} cm</td>
                <td className="px-3 py-2">{record.sitting_height_cm} cm</td>
                <td className="px-3 py-2">
                  {formatOffset(record.maturity_offset)}
                </td>
                <td className="px-3 py-2">
                  <PHVBadge status={record.maturation_status} />
                </td>
                <td className="px-3 py-2">{record.age_at_phv} anos</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal de detalle */}
      {selectedRecord && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setSelectedRecord(null)}
        >
          <div
            className="mx-4 w-full max-w-lg rounded-xl bg-white p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">
                Medicion del {formatDate(selectedRecord.evaluation_date)}
              </h3>
              <button
                type="button"
                onClick={() => setSelectedRecord(null)}
                className="text-slate-400 hover:text-slate-700"
              >
                x
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm text-slate-700">
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
              <p>Edad al PHV: {selectedRecord.age_at_phv} anos</p>
              <p>Mesociclo: {selectedRecord.mesocycle ?? "-"}</p>
              <div className="flex items-center gap-2">
                <span>Estado:</span>
                <PHVBadge status={selectedRecord.maturation_status} />
              </div>
            </div>

            {selectedRecord.training_implications && (
              <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="mb-1 font-medium">Implicaciones de entrenamiento:</p>
                <p>{selectedRecord.training_implications}</p>
              </div>
            )}

            {selectedRecord.notes && (
              <div className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-600">
                <p className="mb-1 font-medium">Notas:</p>
                <p>{selectedRecord.notes}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
