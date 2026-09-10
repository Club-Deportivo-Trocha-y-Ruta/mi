/**
 * Tests para useClubAuditLog / useAthleteAuditLog (feature 041 — gobernanza
 * multi-coach). Contrato: audit-log-api.md §12.
 *
 * Cubre: enabled guard (id nulo/no finito), queryKey incluye filtros
 * (caché independiente por combinación), y que la queryFn delega en
 * getClubAuditLog / getAthleteAuditLog con los argumentos correctos.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

vi.mock("@/api/audit", () => ({
  getClubAuditLog: vi.fn(),
  getAthleteAuditLog: vi.fn(),
  getAuditReasonCodes: vi.fn(),
}));

import { useAthleteAuditLog, useClubAuditLog } from "@/hooks/governance/useAuditLog";
import * as auditApi from "@/api/audit";
import type { AuditListOut } from "@/types/audit.types";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const MOCK_RESPONSE: AuditListOut = {
  items: [
    {
      id: 1,
      occurred_at: "2026-03-14T22:05:41.482913",
      actor_user_id: 10,
      actor_kind: "user",
      actor_role: "coach",
      actor_display_name: "Ana Coach",
      action: "update",
      entity_type: "training_session",
      entity_id: 55,
      entity_label: "la sesión de entrenamiento",
      club_id: 1,
      athlete_id: null,
      reason_code: null,
      reason_label: null,
      sentence_es: "Ana Coach actualizó la sesión de entrenamiento.",
      request_id: "9f1c2b7a4d5e46a8b0c3d9e2f1a7b6c4",
      detail: {
        changed_fields: ["scheduled_date"],
        changed_field_labels: ["Fecha programada"],
        diff: { scheduled_date: { before: "2026-03-10", after: "2026-03-14" } },
        meta: null,
      },
    },
  ],
  total: 1,
  limit: 15,
  offset: 0,
};

describe("useClubAuditLog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("no dispara la query cuando clubId es null", async () => {
    const { result } = renderHook(() => useClubAuditLog(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    await new Promise((r) => setTimeout(r, 30));
    expect(auditApi.getClubAuditLog).not.toHaveBeenCalled();
  });

  it("no dispara la query cuando clubId no es finito", async () => {
    const { result } = renderHook(() => useClubAuditLog(NaN), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    await new Promise((r) => setTimeout(r, 30));
    expect(auditApi.getClubAuditLog).not.toHaveBeenCalled();
  });

  it("dispara la query con clubId válido y delega en getClubAuditLog", async () => {
    vi.mocked(auditApi.getClubAuditLog).mockResolvedValue(MOCK_RESPONSE);

    const { result } = renderHook(() => useClubAuditLog(1, { action: "update" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(auditApi.getClubAuditLog).toHaveBeenCalledWith(
      1,
      { action: "update" },
      expect.objectContaining({ signal: expect.anything() }),
    );
    expect(result.current.data).toEqual(MOCK_RESPONSE);
  });

  it("distintos filtros producen queryKeys distintas (caché independiente)", async () => {
    vi.mocked(auditApi.getClubAuditLog).mockResolvedValue(MOCK_RESPONSE);
    const wrapper = createWrapper();

    const { result: r1 } = renderHook(
      () => useClubAuditLog(1, { action: "update" }),
      { wrapper },
    );
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));

    const { result: r2 } = renderHook(
      () => useClubAuditLog(1, { action: "delete" }),
      { wrapper },
    );
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));

    expect(auditApi.getClubAuditLog).toHaveBeenCalledTimes(2);
    expect(auditApi.getClubAuditLog).toHaveBeenCalledWith(
      1,
      { action: "update" },
      expect.anything(),
    );
    expect(auditApi.getClubAuditLog).toHaveBeenCalledWith(
      1,
      { action: "delete" },
      expect.anything(),
    );
  });
});

describe("useAthleteAuditLog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("no dispara la query cuando athleteId es null", async () => {
    const { result } = renderHook(() => useAthleteAuditLog(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    await new Promise((r) => setTimeout(r, 30));
    expect(auditApi.getAthleteAuditLog).not.toHaveBeenCalled();
  });

  it("dispara la query con athleteId válido y delega en getAthleteAuditLog", async () => {
    vi.mocked(auditApi.getAthleteAuditLog).mockResolvedValue(MOCK_RESPONSE);

    const { result } = renderHook(() => useAthleteAuditLog(7), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(auditApi.getAthleteAuditLog).toHaveBeenCalledWith(
      7,
      {},
      expect.objectContaining({ signal: expect.anything() }),
    );
    expect(result.current.data).toEqual(MOCK_RESPONSE);
  });

  it("propaga el error cuando getAthleteAuditLog falla", async () => {
    vi.mocked(auditApi.getAthleteAuditLog).mockRejectedValue(
      new Error("Error de red ficticio"),
    );

    const { result } = renderHook(() => useAthleteAuditLog(7), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
