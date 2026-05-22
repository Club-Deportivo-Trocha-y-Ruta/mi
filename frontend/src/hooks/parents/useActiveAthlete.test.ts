import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useActiveAthlete } from "./useActiveAthlete";
import { useParentContextStore } from "@/store/parentContext.store";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";
import type { MyAthleteOut } from "@/types/parent.types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(),
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";

function mkAthlete(id: number, first: string): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: first,
    athlete_last_name: "Test",
    birth_date: "2013-06-15",
    sex: Sex.M,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    relationship: FamilyRelationship.padre,
    latest_anthropometry_date: null,
    maturation_status: MaturationStatus.PrePHV,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function mockAthletes(athletes: MyAthleteOut[] | undefined, isLoading = false) {
  vi.mocked(useMyAthletes).mockReturnValue({
    data: athletes,
    isLoading,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useMyAthletes>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useActiveAthlete", () => {
  beforeEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    vi.clearAllMocks();
  });

  afterEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
  });

  describe("fallback single-child", () => {
    it("retorna el único atleta cuando hay un solo hijo y no hay id seleccionado", () => {
      mockAthletes([mkAthlete(7, "Santiago")]);
      const { result } = renderHook(() => useActiveAthlete());
      expect(result.current.athlete?.athlete_id).toBe(7);
      expect(result.current.activeAthleteId).toBeNull();
    });

    it("respeta el id elegido aunque haya un solo hijo", () => {
      mockAthletes([mkAthlete(7, "Santiago")]);
      useParentContextStore.setState({ activeAthleteId: 7 });
      const { result } = renderHook(() => useActiveAthlete());
      expect(result.current.athlete?.athlete_id).toBe(7);
    });
  });

  describe("multi-hijo", () => {
    it("retorna null cuando hay 2+ hijos y no hay id seleccionado", () => {
      mockAthletes([mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")]);
      const { result } = renderHook(() => useActiveAthlete());
      expect(result.current.athlete).toBeNull();
      expect(result.current.athletes).toHaveLength(2);
    });

    it("retorna el atleta seleccionado cuando el id existe en la lista", () => {
      mockAthletes([mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")]);
      useParentContextStore.setState({ activeAthleteId: 9 });
      const { result } = renderHook(() => useActiveAthlete());
      expect(result.current.athlete?.athlete_id).toBe(9);
      expect(result.current.athlete?.athlete_first_name).toBe("Mateo");
    });
  });

  describe("id huérfano (atleta removido)", () => {
    it("resetea activeAthleteId a null si el id persistido ya no está en la lista", async () => {
      // Setup: el padre tenía elegido el hijo 9, pero ese vínculo fue removido
      useParentContextStore.setState({ activeAthleteId: 9 });
      mockAthletes([mkAthlete(7, "Santiago")]);

      const { result } = renderHook(() => useActiveAthlete());

      // El efecto corre tras el render; comprobamos tras una macrotask
      await act(async () => {
        await Promise.resolve();
      });

      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
      // Y el atleta efectivo cae en el fallback single-child
      expect(result.current.athletes).toHaveLength(1);
    });

    it("no toca el store si la lista todavía está vacía (carga inicial)", () => {
      useParentContextStore.setState({ activeAthleteId: 9 });
      mockAthletes([], false);
      renderHook(() => useActiveAthlete());
      // Como la lista está vacía, NO reseteamos — pudo no haber cargado aún.
      expect(useParentContextStore.getState().activeAthleteId).toBe(9);
    });
  });

  describe("setter expuesto", () => {
    it("setActiveAthlete actualiza el store", () => {
      mockAthletes([mkAthlete(7, "Santiago"), mkAthlete(9, "Mateo")]);
      const { result } = renderHook(() => useActiveAthlete());

      act(() => {
        result.current.setActiveAthlete(9);
      });

      expect(useParentContextStore.getState().activeAthleteId).toBe(9);
    });
  });

  describe("loading state", () => {
    it("propaga isLoading de useMyAthletes", () => {
      mockAthletes(undefined, true);
      const { result } = renderHook(() => useActiveAthlete());
      expect(result.current.isLoading).toBe(true);
      expect(result.current.athletes).toEqual([]);
    });
  });
});
