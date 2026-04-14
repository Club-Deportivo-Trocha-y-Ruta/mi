import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthleteInfoCard", () => {
  // -------------------------------------------------------------------------
  // Datos básicos del atleta
  // -------------------------------------------------------------------------
  describe("datos básicos del atleta", () => {
    it("debería mostrar el nombre y apellido del atleta", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    });

    it("debería mostrar la edad decimal con 1 decimal", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/12\.8/)).toBeInTheDocument();
    });

    it("debería mostrar '-' cuando age_decimal es null", () => {
      render(<AthleteInfoCard athlete={athleteWithNullDecimalAge} />);
      expect(screen.getByText(/Edad:.*-/)).toBeInTheDocument();
    });

    it("debería mostrar el sexo del atleta", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/Sexo:.*M/)).toBeInTheDocument();
    });

    it("debería mostrar la categoría del atleta", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/Pre-juvenil A/)).toBeInTheDocument();
    });

    it("debería mostrar 'Sin categoria' cuando category es null", () => {
      render(<AthleteInfoCard athlete={athleteWithoutCategory} />);
      expect(screen.getByText(/Sin categoria/)).toBeInTheDocument();
    });

    it("debería mostrar los años en el club", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(screen.getByText(/En club:.*2/)).toBeInTheDocument();
    });

    it("debería mostrar — cuando years_in_club es null", () => {
      const athlete = { ...baseAthlete, years_in_club: null, club_join_date: null };
      render(<AthleteInfoCard athlete={athlete} />);
      expect(screen.getByText(/En club:.*—/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Sin evaluación antropométrica
  // -------------------------------------------------------------------------
  describe("cuando no hay evaluación antropométrica", () => {
    it("debería mostrar el mensaje 'Sin evaluacion antropometrica registrada.'", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(
        screen.getByText("Sin evaluacion antropometrica registrada."),
      ).toBeInTheDocument();
    });

    it("no debería mostrar el panel de última evaluación", () => {
      render(<AthleteInfoCard athlete={baseAthlete} />);
      expect(
        screen.queryByText(/Ultima evaluacion/i),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Con evaluación antropométrica
  // -------------------------------------------------------------------------
  describe("cuando hay evaluación antropométrica", () => {
    it("debería mostrar la fecha de la última evaluación", () => {
      render(<AthleteInfoCard athlete={athleteWithAnthropometry} />);
      expect(screen.getByText(/Ultima evaluacion:.*2026-01-15/)).toBeInTheDocument();
    });

    it("debería mostrar el badge del estado de maduración", () => {
      render(<AthleteInfoCard athlete={athleteWithAnthropometry} />);
      expect(screen.getByText(MaturationStatus.CircaPHV)).toBeInTheDocument();
    });

    it("no debería mostrar el mensaje de sin evaluación", () => {
      render(<AthleteInfoCard athlete={athleteWithAnthropometry} />);
      expect(
        screen.queryByText("Sin evaluacion antropometrica registrada."),
      ).not.toBeInTheDocument();
    });
  });
});
