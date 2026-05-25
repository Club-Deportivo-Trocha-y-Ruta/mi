import { useState } from "react";

interface ReferenceItem {
  title: string;
  url: string;
  desc: string;
}

const REFERENCES: ReferenceItem[] = [
  {
    title: "OMS — Growth Reference Data 5-19 years",
    url: "https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators",
    desc: "Referencia oficial de crecimiento OMS",
  },
  {
    title: "CDC — Growth Charts Data Files",
    url: "https://www.cdc.gov/growthcharts/cdc-data-files.htm",
    desc: "Datos LMS con percentiles calculados (2-20 años)",
  },
  {
    title: "Resolución 2465 de 2016 — MinSalud Colombia",
    url: "https://www.icbf.gov.co/sites/default/files/resolucion_no._2465_del_14_de_junio_de_2016.pdf",
    desc: "Normativa colombiana de clasificación nutricional",
  },
  {
    title: "Duran et al. 2016 — Curvas colombianas",
    url: "https://onlinelibrary.wiley.com/doi/10.1111/apa.13269",
    desc: "Acta Paediatrica — n=27.209 niños colombianos",
  },
  {
    title: "IMC vs grasa corporal en atletas adolescentes",
    url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC3445161/",
    desc: "Evidencia de falsos positivos de IMC en deportistas",
  },
  {
    title: "Talla en Colombia — Revisión 60 años",
    url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC8392461/",
    desc: "Datos históricos incluyendo Valle del Cauca",
  },
  {
    title: "WHO AnthroPlus — Paquete R oficial",
    url: "https://github.com/WorldHealthOrganization/anthroplus",
    desc: "Datos LMS originales de la OMS",
  },
];

export function ResearchReferences() {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="rounded-xl bg-white"
    >
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <span>Fuentes bibliográficas ({REFERENCES.length})</span>
        <span className="text-xs text-mid-gray">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <ul
          className="px-5 pb-5"
        >
          {REFERENCES.map((ref) => (
            <li
              key={ref.url}
              className="py-3"
            >
              <a
                href={ref.url}
                target="_blank"
                rel="noreferrer"
                className="group flex items-start gap-2"
              >
                <span className="mt-0.5 shrink-0 text-mid-gray transition-colors group-hover:text-link-blue">
                  ↗
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-charcoal transition-opacity group-hover:opacity-70">
                    {ref.title}
                  </p>
                  <p className="mt-0.5 text-xs text-mid-gray">{ref.desc}</p>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
