import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";

import { RubricSliders } from "./RubricSliders";
import type { AttendanceFormValues } from "./AttendanceTable";

function Wrapper({
  defaultValues,
  feedbackLength = 0,
  disabled = false,
}: {
  defaultValues?: Partial<AttendanceFormValues>;
  feedbackLength?: number;
  disabled?: boolean;
}) {
  const { control } = useForm<AttendanceFormValues>({
    defaultValues: {
      status: "presente",
      excuse_reason: null,
      rpe_omni: 5,
      rubric_effort: 3,
      rubric_attitude: 3,
      rubric_technique: 3,
      individual_feedback: null,
      ...defaultValues,
    },
  });
  return (
    <RubricSliders
      control={control}
      disabled={disabled}
      feedbackLength={feedbackLength}
    />
  );
}

describe("RubricSliders", () => {
  describe("RPE OMNI slider", () => {
    it("renderiza con rango 0-10", () => {
      render(<Wrapper />);
      const rpe = screen.getByRole("slider", { name: /RPE OMNI 0-10/i });
      expect(rpe).toHaveAttribute("min", "0");
      expect(rpe).toHaveAttribute("max", "10");
    });

    it("muestra el valor inicial", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 7 }} />);
      const rpe = screen.getByRole("slider", { name: /RPE OMNI 0-10/i });
      expect(rpe).toHaveValue("7");
    });

    it("aria-valuenow refleja el valor", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 3 }} />);
      const rpe = screen.getByRole("slider", { name: /RPE OMNI 0-10/i });
      expect(rpe).toHaveAttribute("aria-valuenow", "3");
      expect(rpe).toHaveAttribute("aria-valuemin", "0");
      expect(rpe).toHaveAttribute("aria-valuemax", "10");
    });
  });

  describe("sliders de rúbrica 1-5", () => {
    it("Esfuerzo tiene rango 1-5", () => {
      render(<Wrapper />);
      const slider = screen.getByRole("slider", { name: /Esfuerzo/i });
      expect(slider).toHaveAttribute("min", "1");
      expect(slider).toHaveAttribute("max", "5");
    });

    it("Actitud tiene rango 1-5", () => {
      render(<Wrapper />);
      const slider = screen.getByRole("slider", { name: /Actitud/i });
      expect(slider).toHaveAttribute("min", "1");
      expect(slider).toHaveAttribute("max", "5");
    });

    it("Técnica tiene rango 1-5", () => {
      render(<Wrapper />);
      const slider = screen.getByRole("slider", { name: /Técnica/i });
      expect(slider).toHaveAttribute("min", "1");
      expect(slider).toHaveAttribute("max", "5");
    });

    it("aria-valuenow en slider de Esfuerzo", () => {
      render(<Wrapper defaultValues={{ rubric_effort: 4 }} />);
      const slider = screen.getByRole("slider", { name: /Esfuerzo/i });
      expect(slider).toHaveAttribute("aria-valuenow", "4");
      expect(slider).toHaveAttribute("aria-valuemin", "1");
      expect(slider).toHaveAttribute("aria-valuemax", "5");
    });
  });

  describe("contador de comentario", () => {
    it("muestra el contador con la longitud correcta", () => {
      render(<Wrapper feedbackLength={42} />);
      expect(screen.getByText("42/500")).toBeInTheDocument();
    });

    it("muestra 0/500 por defecto", () => {
      render(<Wrapper feedbackLength={0} />);
      expect(screen.getByText("0/500")).toBeInTheDocument();
    });
  });

  describe("disabled", () => {
    it("todos los sliders deshabilitados cuando disabled=true", () => {
      render(<Wrapper disabled />);
      const sliders = screen.getAllByRole("slider");
      sliders.forEach((s) => expect(s).toBeDisabled());
    });

    it("textarea deshabilitado cuando disabled=true", () => {
      render(<Wrapper disabled />);
      const textarea = screen.getByRole("textbox", { name: /Comentario del coach/i });
      expect(textarea).toBeDisabled();
    });
  });
});
