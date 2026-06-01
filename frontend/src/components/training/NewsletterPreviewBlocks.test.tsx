/**
 * Tests para NewsletterPreviewBlocks.
 *
 * Cubre: render de cada bloque, skip si data faltante, empty state.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { NewsletterPreviewBlocks } from "./NewsletterPreviewBlocks";

describe("NewsletterPreviewBlocks — empty state", () => {
  it("muestra empty state cuando no hay bloques ni badges", () => {
    render(<NewsletterPreviewBlocks emailBlocks={null} badges={null} />);
    expect(screen.getByTestId("preview-empty")).toBeInTheDocument();
    expect(
      screen.getByText(/Sin contenido de preview disponible/i),
    ).toBeInTheDocument();
  });

  it("muestra empty state cuando email_blocks es null y badges es array vacío", () => {
    render(<NewsletterPreviewBlocks emailBlocks={null} badges={[]} />);
    expect(screen.getByTestId("preview-empty")).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque asistencia", () => {
  it("renderiza bloque de asistencia con porcentaje", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: {
            attendance_pct: 85.4,
            count_present: 6,
            count_total: 7,
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-attendance")).toBeInTheDocument();
    expect(screen.getByText(/85%/i)).toBeInTheDocument();
    expect(screen.getByText(/6 de 7 sesiones/i)).toBeInTheDocument();
  });

  it("muestra racha activa cuando streak > 0", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 90, streak_sessions: 4 },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/4 sesiones consecutivas/i)).toBeInTheDocument();
  });

  it("muestra diferencia vs mes anterior", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 90, prev_month_pct: 80 },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/\+10%/i)).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque carga técnica", () => {
  it("renderiza focos técnicos", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          technical_load: {
            focos_tecnicos: ["Frenada", "Curvas"],
            avg_rpe: 6.5,
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-technical-load")).toBeInTheDocument();
    expect(screen.getByText("Frenada")).toBeInTheDocument();
    expect(screen.getByText("Curvas")).toBeInTheDocument();
    expect(screen.getByText(/6.5/i)).toBeInTheDocument();
  });

  it("renderiza métricas de rúbrica", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          technical_load: {
            avg_rubric_effort: 3.8,
            avg_rubric_attitude: 4.1,
            avg_rubric_technique: 3.5,
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText("Esfuerzo")).toBeInTheDocument();
    expect(screen.getByText("Actitud")).toBeInTheDocument();
    expect(screen.getByText("Técnica")).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque carreras", () => {
  it("renderiza resultado de carrera con posición", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          races: {
            races: [
              {
                event_name: "Válida IV — Cali",
                event_date: "2026-05-17",
                position: 3,
                category: "JUV-M",
              },
            ],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-races")).toBeInTheDocument();
    expect(screen.getByText(/Válida IV — Cali/i)).toBeInTheDocument();
    expect(screen.getByText(/P3/i)).toBeInTheDocument();
  });

  it("muestra 'Sin carreras' cuando no hay races", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{ races: { races: [] } }}
        badges={null}
      />,
    );
    expect(screen.getByText(/Sin carreras este mes/i)).toBeInTheDocument();
  });

  it("muestra gap P1 formateado", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          races: {
            races: [
              {
                event_name: "Válida",
                position: 5,
                gap_p1_ms: 90000,
              },
            ],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/1m 30s/i)).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque calendario", () => {
  it("renderiza próxima válida", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          calendar: {
            next_race_name: "Válida V — Palmira",
            next_race_date: "2026-08-01",
            macro_phase: "Competitiva A",
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-calendar")).toBeInTheDocument();
    expect(screen.getByText(/Válida V — Palmira/i)).toBeInTheDocument();
    expect(screen.getByText(/Competitiva A/i)).toBeInTheDocument();
  });

  it("muestra mensaje cuando no hay datos de calendario", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{ calendar: {} }}
        badges={null}
      />,
    );
    expect(
      screen.getByText(/Sin información de calendario disponible/i),
    ).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque apoyo en casa", () => {
  it("renderiza lista de tips", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          support_at_home: {
            tips: ["Dormir 9 horas", "Hidratarse bien"],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-support")).toBeInTheDocument();
    expect(screen.getByText(/Dormir 9 horas/i)).toBeInTheDocument();
    expect(screen.getByText(/Hidratarse bien/i)).toBeInTheDocument();
  });

  it("muestra mensaje cuando no hay tips", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{ support_at_home: {} }}
        badges={null}
      />,
    );
    expect(
      screen.getByText(/Sin recomendaciones para este mes/i),
    ).toBeInTheDocument();
  });

  it("BUG-001: renderiza tips como objetos {text, title, category} sin crashar", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          support_at_home: {
            tips: [
              { text: "Hidratación post", title: "Hidrata", category: "recovery" },
            ],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-support")).toBeInTheDocument();
    expect(screen.getByText(/Hidratación post/i)).toBeInTheDocument();
  });

  it("BUG-001: acepta tips como strings simples (back-compat)", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          support_at_home: {
            tips: ["Tip simple string"],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/Tip simple string/i)).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque fotos", () => {
  it("renderiza fotos con placeholder cuando no hay thumbnail", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          photos: {
            photos: [{ media_id: 1, caption: "Entrenamiento" }],
            total: 1,
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-photos")).toBeInTheDocument();
    // Debería tener el contenedor de fotos
  });

  it("muestra 'Sin fotos' cuando no hay fotos", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{ photos: { photos: [], total: 0 } }}
        badges={null}
      />,
    );
    expect(screen.getByText(/Sin fotos etiquetadas este mes/i)).toBeInTheDocument();
  });

  it("muestra mensaje de fotos adicionales cuando total > 8", () => {
    const photos = Array.from({ length: 8 }, (_, i) => ({
      media_id: i + 1,
      caption: `Foto ${i + 1}`,
    }));
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          photos: { photos, total: 12 },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/\+4 fotos adicionales en el PDF/i)).toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — bloque badges", () => {
  it("renderiza insignias desde badges_earned raíz", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={null}
        badges={[
          { badge_type: "attendance_90", label: "Asistencia 90%" },
        ]}
      />,
    );
    expect(screen.getByTestId("block-badges")).toBeInTheDocument();
    expect(screen.getByText(/Asistencia 90%/i)).toBeInTheDocument();
  });

  it("renderiza insignias desde email_blocks.badges", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          badges: {
            badges: [{ badge_type: "first_podium", label: "Primer Top 5" }],
          },
        }}
        badges={null}
      />,
    );
    expect(screen.getByText(/Primer Top 5/i)).toBeInTheDocument();
  });

  it("muestra 'Sin insignias' cuando no hay badges", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{ badges: { badges: [] } }}
        badges={[]}
      />,
    );
    // Con badges vacío no debería mostrar el bloque de badges
    expect(screen.queryByTestId("block-badges")).not.toBeInTheDocument();
  });
});

describe("NewsletterPreviewBlocks — skip de bloques faltantes", () => {
  it("omite bloques que no están en email_blocks", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 80 },
          // No technical_load, no races, etc.
        }}
        badges={null}
      />,
    );
    expect(screen.getByTestId("block-attendance")).toBeInTheDocument();
    expect(screen.queryByTestId("block-technical-load")).not.toBeInTheDocument();
    expect(screen.queryByTestId("block-races")).not.toBeInTheDocument();
  });

  it("renderiza todos los bloques cuando todos están presentes", () => {
    render(
      <NewsletterPreviewBlocks
        emailBlocks={{
          attendance: { attendance_pct: 80 },
          technical_load: { focos_tecnicos: ["Frenada"] },
          races: { races: [] },
          calendar: { next_race_name: "Válida V" },
          support_at_home: { tips: ["Dormir bien"] },
          photos: { photos: [] },
        }}
        badges={[{ badge_type: "attendance_90", label: "Asistencia 90%" }]}
      />,
    );
    expect(screen.getByTestId("block-attendance")).toBeInTheDocument();
    expect(screen.getByTestId("block-technical-load")).toBeInTheDocument();
    expect(screen.getByTestId("block-races")).toBeInTheDocument();
    expect(screen.getByTestId("block-calendar")).toBeInTheDocument();
    expect(screen.getByTestId("block-support")).toBeInTheDocument();
    expect(screen.getByTestId("block-photos")).toBeInTheDocument();
    expect(screen.getByTestId("block-badges")).toBeInTheDocument();
  });
});
