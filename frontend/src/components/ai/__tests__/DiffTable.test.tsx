/**
 * Tests DiffTable (F-UP-REV5).
 *
 * Cubre:
 *  - Render con diff_rows de acciones mixtas
 *  - Badge color correcto por acción
 *  - Filtro "solo cambios" esconde unchanged
 *  - Diff fields inline correctos para action=update
 *  - Formato tiempo ms → mm:ss.ms
 *  - Mensaje "Esta revisión no cambia ningún resultado" con filtro activo
 *  - Paginación cuando rows > pageSize
 *  - jest-axe sin violaciones
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { DiffTable, formatRaceTimeMs } from "@/components/ai/DiffTable";
import type { DiffRow } from "@/types/raceImports.types";

expect.extend(toHaveNoViolations);

const MIXED: DiffRow[] = [
  {
    action: "create",
    competitor_normalized_name: "maria gomez",
    competitor_display_name: "María Gómez",
    category_code: "INF_A_F",
    before: null,
    after: { position: 7, race_time_ms: 2022000, status: "FINISHED" },
    result_id: null,
  },
  {
    action: "update",
    competitor_normalized_name: "andres mejia",
    competitor_display_name: "Andrés Mejía",
    category_code: "JUN_M",
    before: { position: 5, race_time_ms: 3012000, status: "FINISHED" },
    after: { position: 3, race_time_ms: 2948000, status: "FINISHED" },
    result_id: 891,
  },
  {
    action: "delete",
    competitor_normalized_name: "diego rojas",
    competitor_display_name: "Diego Rojas",
    category_code: "JUN_M",
    before: { position: 8, race_time_ms: 3142000, status: "FINISHED" },
    after: null,
    result_id: 234,
  },
  {
    action: "unchanged",
    competitor_normalized_name: "juan perez",
    competitor_display_name: "Juan Pérez",
    category_code: "INF_A_M",
    before: { position: 4, race_time_ms: 2500000, status: "FINISHED" },
    after: { position: 4, race_time_ms: 2500000, status: "FINISHED" },
    result_id: 100,
  },
];

describe("formatRaceTimeMs", () => {
  it("formatea correctamente ms a mm:ss.ms", () => {
    expect(formatRaceTimeMs(0)).toBe("00:00.000");
    expect(formatRaceTimeMs(2948000)).toBe("49:08.000");
    expect(formatRaceTimeMs(3012345)).toBe("50:12.345");
    expect(formatRaceTimeMs(null)).toBe("—");
    expect(formatRaceTimeMs(undefined)).toBe("—");
  });
});

describe("DiffTable — render", () => {
  it("renderiza filas con todas las acciones cuando filtro 'solo cambios' está OFF", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    expect(screen.getByText("María Gómez")).toBeInTheDocument();
    expect(screen.getByText("Andrés Mejía")).toBeInTheDocument();
    expect(screen.getByText("Diego Rojas")).toBeInTheDocument();
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
  });

  it("badges con className correcto por acción", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    const createBadge = screen.getByTestId("diff-badge-create");
    const updateBadge = screen.getByTestId("diff-badge-update");
    const deleteBadge = screen.getByTestId("diff-badge-delete");
    const unchangedBadge = screen.getByTestId("diff-badge-unchanged");

    expect(createBadge.className).toContain("emerald");
    expect(updateBadge.className).toContain("blue");
    expect(deleteBadge.className).toContain("red");
    expect(unchangedBadge.className).toMatch(/light-gray|mid-gray/);
  });

  it("filtro 'solo cambios' esconde filas unchanged", async () => {
    const user = userEvent.setup();
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
    await user.click(screen.getByTestId("diff-toggle-only-changes"));
    expect(screen.queryByText("Juan Pérez")).not.toBeInTheDocument();
    expect(screen.getByText("Andrés Mejía")).toBeInTheDocument();
  });

  it("muestra diff inline correcto para action=update", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    const row = screen.getByTestId("diff-row-update-andres mejia");
    expect(within(row).getByText("Posición:")).toBeInTheDocument();
    // before "5" y after "3"
    expect(within(row).getByText("5")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    // tiempo formateado (mm:ss.ms)
    expect(within(row).getByText("50:12.000")).toBeInTheDocument();
    expect(within(row).getByText("49:08.000")).toBeInTheDocument();
  });

  it("formato create muestra 'Nuevo en P{after.position}'", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    const row = screen.getByTestId("diff-row-create-maria gomez");
    expect(within(row).getByText(/Nuevo en P7/)).toBeInTheDocument();
    expect(within(row).getByText("33:42.000")).toBeInTheDocument();
  });

  it("formato delete muestra 'Removido (era P{before.position})'", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);

    const row = screen.getByTestId("diff-row-delete-diego rojas");
    expect(within(row).getByText(/Removido \(era P8\)/)).toBeInTheDocument();
  });

  it("muestra mensaje friendly cuando todo es unchanged y filtro está ON", async () => {
    const onlyUnchanged: DiffRow[] = [MIXED[3]];
    render(<DiffTable diffRows={onlyUnchanged} defaultOnlyChanges={true} />);

    expect(
      screen.getByText(/Esta revisión no cambia ningún resultado/i),
    ).toBeInTheDocument();
  });

  it("default activa filtro solo cambios cuando unchanged > 20", () => {
    const many: DiffRow[] = [...MIXED];
    for (let i = 0; i < 25; i++) {
      many.push({
        action: "unchanged",
        competitor_normalized_name: `noop-${i}`,
        competitor_display_name: `Sin cambio ${i}`,
        category_code: "INF_A_M",
        before: { position: i, race_time_ms: 1000, status: "FINISHED" },
        after: { position: i, race_time_ms: 1000, status: "FINISHED" },
        result_id: 1000 + i,
      });
    }
    render(<DiffTable diffRows={many} />);
    const toggle = screen.getByTestId(
      "diff-toggle-only-changes",
    ) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    // Las filas unchanged no deben aparecer
    expect(screen.queryByText("Sin cambio 0")).not.toBeInTheDocument();
  });

  it("paginación visible cuando filtered > pageSize", async () => {
    const many: DiffRow[] = [];
    for (let i = 0; i < 60; i++) {
      many.push({
        action: "update",
        competitor_normalized_name: `comp-${i}`,
        competitor_display_name: `Competidor ${i}`,
        category_code: "INF_A_M",
        before: { position: i, race_time_ms: 1000, status: "FINISHED" },
        after: { position: i + 1, race_time_ms: 1500, status: "FINISHED" },
        result_id: 500 + i,
      });
    }
    const user = userEvent.setup();
    render(<DiffTable diffRows={many} pageSize={50} defaultOnlyChanges={false} />);

    expect(screen.getByTestId("diff-pagination")).toBeInTheDocument();
    expect(screen.getByText(/Página 1 de 2/)).toBeInTheDocument();
    // pag 1 → Competidor 0..49
    expect(screen.getByText("Competidor 0")).toBeInTheDocument();
    expect(screen.queryByText("Competidor 55")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("diff-page-next"));
    expect(screen.queryByText("Competidor 0")).not.toBeInTheDocument();
    expect(screen.getByText("Competidor 55")).toBeInTheDocument();
  });

  it("tabla tiene role + aria-label apropiados (a11y básico)", () => {
    render(<DiffTable diffRows={MIXED} defaultOnlyChanges={false} />);
    const table = screen.getByRole("table", {
      name: /Diferencias entre el PDF nuevo/i,
    });
    expect(table).toBeInTheDocument();
    // 4 <th> con scope="col"
    const ths = table.querySelectorAll("th[scope='col']");
    expect(ths.length).toBe(4);
  });

  it("jest-axe — sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <DiffTable diffRows={MIXED} defaultOnlyChanges={false} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
