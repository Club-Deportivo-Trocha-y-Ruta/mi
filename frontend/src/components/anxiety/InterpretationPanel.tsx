import type { AnxietySource, Interpretation } from "@/types/anxiety.types";

interface InterpretationPanelProps {
  interpretation: Interpretation;
  source: AnxietySource | null;
}

/** Renderiza la interpretación cacheada (US4). Clima de maestría, sin diagnóstico. */
export function InterpretationPanel({
  interpretation,
  source,
}: InterpretationPanelProps) {
  return (
    <article className="rounded-xl border border-border-gray bg-white p-5">
      <header className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-charcoal">
          Interpretación
        </h3>
        {source && (
          <span
            className="rounded-full bg-light-gray px-2 py-0.5 text-xs text-mid-gray"
            title={
              source === "llm"
                ? "Generada por IA del club"
                : "Generada por reglas (respaldo)"
            }
          >
            {source === "llm" ? "IA" : "Reglas"}
          </span>
        )}
      </header>

      <p className="mb-4 text-sm text-charcoal">{interpretation.resumen}</p>

      <dl className="mb-4 space-y-2 text-sm">
        <div>
          <dt className="font-medium text-charcoal">Cognitiva</dt>
          <dd className="text-mid-gray">
            {interpretation.por_dimension.cognitiva}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-charcoal">Somática</dt>
          <dd className="text-mid-gray">
            {interpretation.por_dimension.somatica}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-charcoal">Autoconfianza</dt>
          <dd className="text-mid-gray">
            {interpretation.por_dimension.autoconfianza}
          </dd>
        </div>
      </dl>

      {interpretation.estrategias.length > 0 && (
        <div className="mb-4">
          <h4 className="mb-1 text-sm font-medium text-charcoal">
            Estrategias
          </h4>
          <ul className="list-disc space-y-1 pl-5 text-sm text-mid-gray">
            {interpretation.estrategias.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="mb-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
        {interpretation.mensaje_para_el_atleta}
      </p>

      {interpretation.banderas.length > 0 && (
        <div
          className="rounded-lg border border-amber-300 bg-amber-50 p-3"
          role="alert"
        >
          <h4 className="mb-1 text-sm font-medium text-amber-900">Atención</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">
            {interpretation.banderas.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

export default InterpretationPanel;
