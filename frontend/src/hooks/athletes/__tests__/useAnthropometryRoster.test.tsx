/**
 * useAnthropometryRoster (feature 048, T043): clave por fecha e invalidación
 * desde alta, edición y borrado de mediciones. Datos ficticios.
 */
import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/athletes", () => ({
  getAnthropometryRoster: vi.fn(),
  createAnthropometry: vi.fn(),
  updateAnthropometry: vi.fn(),
  deleteAnthropometry: vi.fn(),
  getAnthropometry: vi.fn(),
  checkPlausibility: vi.fn(),
}));

import * as athletesApi from "@/api/athletes";
import {
  useAnthropometryRoster,
  useCreateAnthropometry,
  useDeleteAnthropometry,
  useUpdateAnthropometry,
} from "@/hooks/athletes/useAnthropometry";

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

const PAYLOAD = {
  evaluation_date: "2026-09-20",
  weight_kg: 40,
  standing_height_cm: 150,
  sitting_height_cm: 75,
};

describe("useAnthropometryRoster", () => {
  it("consulta con la fecha y usa la clave [anthropometry-roster, fecha]", async () => {
    vi.mocked(athletesApi.getAnthropometryRoster).mockResolvedValue([]);
    const { queryClient, wrapper } = setup();
    const { result } = renderHook(() => useAnthropometryRoster("2026-09-20"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(athletesApi.getAnthropometryRoster).toHaveBeenCalledWith("2026-09-20");
    expect(queryClient.getQueryData(["anthropometry-roster", "2026-09-20"])).toEqual([]);
  });

  it("no consulta si está deshabilitado", () => {
    vi.mocked(athletesApi.getAnthropometryRoster).mockClear();
    const { wrapper } = setup();
    renderHook(() => useAnthropometryRoster("2026-09-20", false), { wrapper });
    expect(athletesApi.getAnthropometryRoster).not.toHaveBeenCalled();
  });

  it.each([
    [
      "alta",
      () => {
        vi.mocked(athletesApi.createAnthropometry).mockResolvedValue({ id: 1 } as never);
        return (hook: ReturnType<typeof useCreateAnthropometry>) => hook.mutateAsync(PAYLOAD);
      },
      useCreateAnthropometry,
    ],
    [
      "edición",
      () => {
        vi.mocked(athletesApi.updateAnthropometry).mockResolvedValue({ id: 1 } as never);
        return (hook: ReturnType<typeof useUpdateAnthropometry>) =>
          hook.mutateAsync({ recordId: 1, payload: PAYLOAD });
      },
      useUpdateAnthropometry,
    ],
    [
      "borrado",
      () => {
        vi.mocked(athletesApi.deleteAnthropometry).mockResolvedValue(undefined as never);
        return (hook: ReturnType<typeof useDeleteAnthropometry>) => hook.mutateAsync(1);
      },
      useDeleteAnthropometry,
    ],
  ] as const)("la %s invalida el roster", async (_label, arrange, useMutationHook) => {
    const run = arrange() as (hook: unknown) => Promise<unknown>;
    const { queryClient, wrapper } = setup();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => (useMutationHook as (id: number) => unknown)(17), {
      wrapper,
    });
    await act(async () => {
      await run(result.current);
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["anthropometry-roster"] });
  });
});
