import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AthleteInfoCard } from "./AthleteInfoCard";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseAthlete: AthleteDetailOut = {
  id: 1,
  user_id: 10,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2013-06-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2.3,
  age_decimal: 12.8,
  category: "Pre-juvenil A",
  club_id: 1,
  created_at: "2026-01-01T00:00:00Z",
  latest_anthropometry: null,
};

const athleteWithAnthropometry: AthleteDetailOut = {
  ...baseAthlete,
  latest_anthropometry: {
    id: 1,
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    mesocycle: 1,
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 73.0,
    leg_length_cm: 82.0,
    leg_sitting_ratio: 1.1233,
    maturity_offset: -0.5,
    age_at_phv: 13.5,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
  },
};

const athleteWithoutCategory: AthleteDetailOut = {
  ...baseAthlete,
  category: null,
};

const athleteWithNullDecimalAge: AthleteDetailOut = {
  ...baseAthlete,
  age_decimal: null,
};

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthleteInfoCard", () => {
  // -------------------------------------------------------------------------
  // Datos básicos del atleta
  // -------------------------------------------------------------------------
  describe("datos básicos del atleta", () => {
    it("debería mostrar el nombre y apellido del atleta", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    });

    it("debería mostrar las iniciales en el avatar", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("SG")).toBeInTheDocument();
    });

    it("debería mostrar la edad decimal en el subtítulo", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/12\.8 años/)).toBeInTheDocument();
    });

    it("debería mostrar '—' cuando age_decimal es null", () => {
      renderWithRouter(<AthleteInfoCard athlete={athleteWithNullDecimalAge} />);
      expect(screen.getByText(/— años/)).toBeInTheDocument();
    });

    it("debería mostrar 'Masculino' para sexo M", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/Masculino/)).toBeInTheDocument();
    });

    it("debería mostrar la categoría del atleta", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/Pre-juvenil A/)).toBeInTheDocument();
    });

    it("debería mostrar 'Sin categoría' cuando category es null", () => {
      renderWithRouter(<AthleteInfoCard athlete={athleteWithoutCategory} />);
      expect(screen.getByText(/Sin categoría/)).toBeInTheDocument();
    });

    it("debería mostrar los años en el club como stat pill", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("2.3 años")).toBeInTheDocument();
    });

    it("no debería mostrar pill de club cuando years_in_club es null", () => {
      const athlete = { ...baseAthlete, years_in_club: null, club_join_date: null };
      renderWithRouter(<AthleteInfoCard athlete={athlete} />);
      expect(screen.queryByText("En club")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Sin evaluación antropométrica
  // -------------------------------------------------------------------------
  describe("cuando no hay evaluación antropométrica", () => {
    it("debería mostrar badge 'Sin evaluar'", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("Sin evaluar")).toBeInTheDocument();
    });

    it("no debería mostrar stat pills de talla ni peso", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.queryByText("Talla")).not.toBeInTheDocument();
      expect(screen.queryByText("Peso")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Con evaluación antropométrica
  // -------------------------------------------------------------------------
  describe("cuando hay evaluación antropométrica", () => {
    it("debería mostrar el badge del estado de maduración", () => {
      renderWithRouter(<AthleteInfoCard athlete={athleteWithAnthropometry} />);
      expect(screen.getByText(MaturationStatus.CircaPHV)).toBeInTheDocument();
    });

    it("debería mostrar stat pills de talla y peso", () => {
      renderWithRouter(<AthleteInfoCard athlete={athleteWithAnthropometry} />);
      expect(screen.getByText("155 cm")).toBeInTheDocument();
      expect(screen.getByText("45 kg")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Navegación
  // -------------------------------------------------------------------------
  describe("navegación", () => {
    it("debería tener link para volver a la lista", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("Volver a lista")).toBeInTheDocument();
    });

    it("debería tener link para editar", () => {
      renderWithRouter(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("Editar")).toBeInTheDocument();
    });
  });
});
