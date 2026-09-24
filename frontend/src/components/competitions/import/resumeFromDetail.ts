/**
 * Rehidrata el `ImportParseResponse` que el wizard tenía en memoria a partir
 * del detalle persistido (`GET /imports/{id}`, feature 045 US3).
 *
 * El meta público solo guarda lo necesario para mostrar el paso 2: encabezado,
 * condiciones y categorías con su completitud. `categories[].rows` es un
 * CONTEO en el servidor (las filas viven en el archivo almacenado), así que
 * aquí `rows` queda vacío y el conteo viaja en `row_count`.
 *
 * Privacidad: no se reconstruye ninguna fila de resultados ni `corrections`
 * (el backend no las expone).
 */
import type {
  ImportDetail,
  ImportParseResponse,
  ParsedCategory,
} from "@/types/raceImports.types";

export function parseResultFromDetail(detail: ImportDetail): ImportParseResponse {
  const meta = detail.parse_meta ?? {};
  const header = meta.header ?? {};

  const categories: ParsedCategory[] = (meta.categories ?? []).map((c) => ({
    header_raw: c.header_raw,
    code: c.code,
    mapping_kind: c.mapping_kind,
    rows: [],
    row_count: c.rows,
    completeness: c.completeness,
  }));

  return {
    parse_id: String(detail.id),
    // El hash no se expone en el detalle público; el paso 2 no lo usa.
    sha256: "",
    header: {
      series_name: header.series_name ?? "",
      season: header.season ?? detail.season ?? 0,
      valida_num: header.valida_num ?? 0,
      event_name: header.event_name ?? "",
    },
    n_rows_resultados: meta.n_rows_resultados ?? 0,
    n_rows_general: meta.n_rows_general ?? 0,
    warnings: [],
    conditions: meta.conditions ?? null,
    categories,
    unreadable_rows: meta.unreadable_rows ?? [],
    // El aviso de revisión del paso 2 lo lee de aquí: sin esto, retomar una
    // revisión mostraba «—» donde va la fecha de la versión previa.
    parent_committed_at: detail.parent_committed_at ?? undefined,
  };
}
