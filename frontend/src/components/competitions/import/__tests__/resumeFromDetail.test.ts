/**
 * parseResultFromDetail — rehidrata el parse del wizard desde el detalle
 * persistido (feature 045). El meta solo guarda el CONTEO de filas por
 * categoría y no expone `corrections`.
 */
import { describe, expect, it } from "vitest";

import { parseResultFromDetail } from "@/components/competitions/import/resumeFromDetail";
import { makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";

describe("parseResultFromDetail", () => {
  it("usa el id de la carga como parse_id y copia el encabezado", () => {
    const parsed = parseResultFromDetail(makeImportDetail({ id: 42 }));
    expect(parsed.parse_id).toBe("42");
    expect(parsed.header).toMatchObject({
      series_name: "Copa Valle de Ciclomontañismo",
      season: 2026,
      valida_num: 1,
    });
    expect(parsed.n_rows_resultados).toBe(20);
  });

  it("las categorías llevan el conteo en row_count y ninguna fila", () => {
    const parsed = parseResultFromDetail(makeImportDetail());
    expect(parsed.categories).toHaveLength(2);
    for (const category of parsed.categories ?? []) {
      expect(category.rows).toEqual([]);
    }
    expect(parsed.categories?.map((c) => c.row_count)).toEqual([12, 8]);
  });

  it("conserva la completitud y las filas ilegibles del meta", () => {
    const parsed = parseResultFromDetail(
      makeImportDetail({
        parse_meta: {
          header: { series_name: "Copa Prueba", season: 2025, valida_num: 2 },
          categories: [
            {
              header_raw: "Sub-13 Mujeres",
              code: null,
              mapping_kind: "unknown",
              rows: 5,
              completeness: { status: "inconsistent", missing: [3], duplicated: [] },
            },
          ],
          unreadable_rows: [{ page: 2, ordinal: null }],
        },
      }),
    );
    expect(parsed.categories?.[0]).toMatchObject({
      code: null,
      completeness: { status: "inconsistent", missing: [3] },
    });
    expect(parsed.unreadable_rows).toEqual([{ page: 2, ordinal: null }]);
  });

  it("conserva cuándo se confirmó la versión previa (aviso de revisión)", () => {
    const parsed = parseResultFromDetail(
      makeImportDetail({ parent_committed_at: "2026-05-17T18:42:00" }),
    );
    expect(parsed.parent_committed_at).toBe("2026-05-17T18:42:00");
  });

  it("sin versión previa (null o ausente) no inventa parent_committed_at", () => {
    expect(
      parseResultFromDetail(makeImportDetail({ parent_committed_at: null }))
        .parent_committed_at,
    ).toBeUndefined();
    expect(
      parseResultFromDetail(makeImportDetail()).parent_committed_at,
    ).toBeUndefined();
  });

  it("tolera un meta escueto: temporada del detalle y listas vacías", () => {
    const parsed = parseResultFromDetail(
      makeImportDetail({ season: 2024, parse_meta: { header: {} } }),
    );
    expect(parsed.header.season).toBe(2024);
    expect(parsed.categories).toEqual([]);
    expect(parsed.unreadable_rows).toEqual([]);
    expect(parsed.conditions).toBeNull();
  });
});
