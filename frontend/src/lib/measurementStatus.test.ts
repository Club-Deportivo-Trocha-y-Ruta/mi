import { describe, it, expect } from "vitest";
import { STATUS_META, getMeasurementStatusMeta } from "./measurementStatus";
import type { MeasurementStatus } from "@/types/alerts.types";

const ALL_STATUSES: MeasurementStatus[] = ["overdue", "due_soon", "ok", "never"];

describe("measurementStatus", () => {
  it("define una entrada para cada MeasurementStatus", () => {
    ALL_STATUSES.forEach((status) => {
      expect(STATUS_META[status]).toBeDefined();
    });
  });

  it("nunca comunica el estado solo por color: cada entrada trae rowLabel y summaryLabel", () => {
    ALL_STATUSES.forEach((status) => {
      const meta = STATUS_META[status];
      expect(meta.rowLabel.length).toBeGreaterThan(0);
      expect(meta.summaryLabel.length).toBeGreaterThan(0);
    });
  });

  it("mapea overdue → danger, due_soon → warning, ok → success, never → neutral", () => {
    expect(STATUS_META.overdue.tone).toBe("danger");
    expect(STATUS_META.due_soon.tone).toBe("warning");
    expect(STATUS_META.ok.tone).toBe("success");
    expect(STATUS_META.never.tone).toBe("neutral");
  });

  it("las etiquetas de fila están en español neutro", () => {
    expect(STATUS_META.overdue.rowLabel).toBe("Vencida");
    expect(STATUS_META.due_soon.rowLabel).toBe("Próxima");
    expect(STATUS_META.ok.rowLabel).toBe("Al día");
    expect(STATUS_META.never.rowLabel).toBe("Sin medir");
  });

  it("getMeasurementStatusMeta retorna la misma entrada que STATUS_META[status]", () => {
    ALL_STATUSES.forEach((status) => {
      expect(getMeasurementStatusMeta(status)).toEqual(STATUS_META[status]);
    });
  });
});
