import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AthleteSwitcher } from "@/components/parents/AthleteSwitcher";
import { useParentContextStore } from "@/store/parentContext.store";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";
import type { MyAthleteOut } from "@/types/parent.types";

// ---------------------------------------------------------------------------
// Mocks: useMyAthletes y queryClientHandle (para que purgeQueriesForAthlete
// no warne durante el test del setter del store).
// ---------------------------------------------------------------------------

vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(),
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";

function mkAthlete(id: number, first: string, last = "López"): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: first,
    athlete_last_name: last,
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

function mockAthletes(athletes: MyAthleteOut[], isLoading = false) {
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

describe("AthleteSwitcher", () => {
  beforeEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    vi.clearAllMocks();
  });

  afterEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
  });

  describe("cuando hay 0 atletas", () => {
    it("no renderiza nada", () => {
      mockAthletes([]);
      const { container } = render(<AthleteSwitcher />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe("cuando hay 1 atleta", () => {
    it("renderiza un label estático sin dropdown", () => {
      mockAthletes([mkAthlete(7, "Santiago", "López")]);
      render(<AthleteSwitcher />);
      expect(screen.getByTestId("athlete-switcher-single")).toBeInTheDocument();
      expect(screen.getByText("Santiago López")).toBeInTheDocument();
      // No hay trigger de dropdown
      expect(
        screen.queryByTestId("athlete-switcher-trigger"),
      ).not.toBeInTheDocument();
    });

    it("muestra edad y categoría como subtítulo", () => {
      mockAthletes([mkAthlete(7, "Santiago", "López")]);
      render(<AthleteSwitcher />);
      // 12.8 años · Pre-juvenil A
      expect(screen.getByText(/12\.8 años/)).toBeInTheDocument();
    });
  });

  describe("cuando hay 2+ atletas", () => {
    beforeEach(() => {
      mockAthletes([
        mkAthlete(7, "Santiago", "López"),
        mkAthlete(9, "Mateo", "López"),
      ]);
    });

    it("renderiza el trigger del dropdown con aria-label accesible", () => {
      render(<AthleteSwitcher />);
      const trigger = screen.getByLabelText("Cambiar atleta activo");
      expect(trigger).toBeInTheDocument();
    });

    it("al hacer click abre el menú con todas las opciones", async () => {
      const user = userEvent.setup();
      render(<AthleteSwitcher />);
      await user.click(screen.getByTestId("athlete-switcher-trigger"));

      expect(screen.getByTestId("athlete-switcher-item-all")).toBeInTheDocument();
      expect(screen.getByTestId("athlete-switcher-item-7")).toBeInTheDocument();
      expect(screen.getByTestId("athlete-switcher-item-9")).toBeInTheDocument();
    });

    it("al seleccionar un atleta dispara setActiveAthlete con su id", async () => {
      const user = userEvent.setup();
      render(<AthleteSwitcher />);

      await user.click(screen.getByTestId("athlete-switcher-trigger"));
      await user.click(screen.getByTestId("athlete-switcher-item-9"));

      expect(useParentContextStore.getState().activeAthleteId).toBe(9);
    });

    it("al seleccionar 'Todos' dispara setActiveAthlete(null)", async () => {
      const user = userEvent.setup();
      useParentContextStore.setState({ activeAthleteId: 7 });
      render(<AthleteSwitcher />);

      await user.click(screen.getByTestId("athlete-switcher-trigger"));
      await user.click(screen.getByTestId("athlete-switcher-item-all"));

      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
    });

    it("muestra el nombre del atleta activo en el trigger cuando hay selección", () => {
      useParentContextStore.setState({ activeAthleteId: 9 });
      render(<AthleteSwitcher />);
      const trigger = screen.getByTestId("athlete-switcher-trigger");
      expect(within(trigger).getByText("Mateo López")).toBeInTheDocument();
    });

    it("muestra 'Todos mis atletas' en el trigger cuando no hay selección", () => {
      render(<AthleteSwitcher />);
      const trigger = screen.getByTestId("athlete-switcher-trigger");
      expect(within(trigger).getByText("Todos mis atletas")).toBeInTheDocument();
    });
  });

  describe("loading state", () => {
    it("no renderiza nada mientras useMyAthletes está cargando", () => {
      mockAthletes([], true);
      const { container } = render(<AthleteSwitcher />);
      expect(container.firstChild).toBeNull();
    });
  });
});
