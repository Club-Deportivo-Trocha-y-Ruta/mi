import { useState } from "react";

import { mapAnxietyError } from "@/api/anxiety";
import { useAnxietyImport } from "@/hooks/anxiety/useAnxietyDashboards";
import type { ImportResult } from "@/types/anxiety.types";

/** Import histórico CSV (US6): preview del archivo + reporte de errores por fila. */
export function ImportDialog() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mutation = useAnxietyImport();

  function run() {
    if (!file) return;
    setError(null);
    setResult(null);
    mutation.mutate(file, {
      onSuccess: (data) => setResult(data),
      onError: (err) => setError(mapAnxietyError(err).message),
    });
  }

  return (
    <section
      className="rounded-xl border border-border-gray bg-white p-5"
      aria-label="Importar evaluaciones históricas"
    >
      <h3 className="mb-1 text-base font-semibold text-charcoal">
        Importar histórico (CSV)
      </h3>
      <p className="mb-4 text-xs text-mid-gray">
        Columnas: <code>athlete_ref, instrument, date, event_ref?, i1..iN</code>.
        Cada fila se puntúa con la misma clave que el flujo en vivo.
      </p>

      <label className="mb-3 block text-sm">
        <span className="mb-1 block font-medium text-charcoal">Archivo</span>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setResult(null);
            setError(null);
          }}
          className="block w-full text-sm text-mid-gray file:mr-3 file:rounded-md file:border-0 file:bg-light-gray file:px-3 file:py-2"
        />
      </label>

      {file && (
        <p className="mb-3 text-xs text-mid-gray">
          Seleccionado: <strong>{file.name}</strong> ({Math.ceil(file.size / 1024)} KB)
        </p>
      )}

      <button
        type="button"
        onClick={run}
        disabled={!file || mutation.isPending}
        className="min-h-10 rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? "Importando…" : "Importar"}
      </button>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 text-sm">
          <p className="text-charcoal">
            Importadas: <strong>{result.imported}</strong> · Omitidas:{" "}
            <strong>{result.skipped}</strong>
          </p>
          {result.errors.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-800">
              {result.errors.map((e) => (
                <li key={e.row}>
                  Fila {e.row}: {e.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export default ImportDialog;
