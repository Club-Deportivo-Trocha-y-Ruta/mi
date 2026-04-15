import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChildCard } from "../ChildCard";
import type { MyAthleteOut } from "@/types/parent.types";
import { FamilyRelationship, MaturationStatus, Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAthlete(overrides?: Partial<MyAthleteOut>): MyAthleteOut {
  return {
    athlete_id: 7,
    athlete_first_name: "Santiago",
    athlete_last_name: "López",
    birth_date: "2013-06-15",
    sex: Sex.M,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    relationship: FamilyRelationship.padre,
    latest_anthropometry_date: "2026-01-15",
    maturation_status: MaturationStatus.PrePHV,
    standing_height_cm: "148.5",
    weight_kg: "40.2",
    measurement_status: "ok",
    ...overrides,
  };
}

function renderCard(athlete: MyAthleteOut) {
  return render(
    <MemoryRouter>
      <ChildCard athlete={athlete} />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ChildCard", () => {
  // -------------------------------------------------------------------------
  // Nombre del atleta
  // -------------------------------------------------------------------------
  it("debería renderizar el nombre y apellido del atleta", () => {
    renderCard(makeAthlete());
    expect(screen.getByText("Santiago López")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Badges de estado de medición
  // -------------------------------------------------------------------------
  describe("badge de estado de medición", () => {
    it("debería mostrar badge 'Al día' cuando measurement_status es ok", () => {
      renderCard(makeAthlete({ measurement_status: "ok" }));
      expect(screen.getByText("Al día")).toBeInTheDocument();
    });

    it("debería mostrar badge 'Medición vencida' cuando measurement_status es overdue", () => {
      renderCard(makeAthlete({ measurement_status: "overdue" }));
      expect(screen.getByText("Medición vencida")).toBeInTheDocument();
    });

    it("debería mostrar badge 'Sin mediciones' cuando measurement_status es never", () => {
      renderCard(makeAthlete({ measurement_status: "never" }));
      expect(screen.getByText("Sin mediciones")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Estado de maduración (PHV)
  // -------------------------------------------------------------------------
  describe("estado de maduración PHV", () => {
    it("debería mostrar 'En etapa de desarrollo temprano' para Pre-PHV", () => {
      renderCard(makeAthlete({ maturation_status: MaturationStatus.PrePHV }));
      expect(screen.getByText("En etapa de desarrollo temprano")).toBeInTheDocument();
    });

    it("debería mostrar 'En pico de crecimiento — etapa clave' para Circa-PHV", () => {
      renderCard(makeAthlete({ maturation_status: MaturationStatus.CircaPHV }));
      expect(screen.getByText("En pico de crecimiento — etapa clave")).toBeInTheDocument();
    });

    it("debería mostrar 'Crecimiento estabilizándose' para Post-PHV", () => {
      renderCard(makeAthlete({ maturation_status: MaturationStatus.PostPHV }));
      expect(screen.getByText("Crecimiento estabilizándose")).toBeInTheDocument();
    });

    it("debería mostrar 'Sin evaluación de crecimiento' cuando maturation_status es null", () => {
      renderCard(
        makeAthlete({
          maturation_status: null,
          latest_anthropometry_date: "2026-01-15",
        }),
      );
      expect(screen.getByText("Sin evaluación de crecimiento")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Datos de antropometría
  // -------------------------------------------------------------------------
  describe("datos de antropometría", () => {
    it("debería mostrar 'Sin mediciones registradas' cuando latest_anthropometry_date es null", () => {
      renderCard(
        makeAthlete({
          latest_anthropometry_date: null,
          measurement_status: "never",
        }),
      );
      expect(screen.getByText("Sin mediciones registradas")).toBeInTheDocument();
    });

    it("debería mostrar la talla formateada cuando hay datos de antropometría", () => {
      renderCard(makeAthlete({ standing_height_cm: "148.5" }));
      expect(screen.getByText("148.5 cm")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Navegación
  // -------------------------------------------------------------------------
  describe("navegación", () => {
    it("el link 'Ver detalle' debe apuntar a /my-athletes/{athlete_id}", () => {
      renderCard(makeAthlete({ athlete_id: 7 }));
      const link = screen.getByRole("link", { name: /ver detalle/i });
      expect(link).toHaveAttribute("href", "/my-athletes/7");
    });
  });
});
