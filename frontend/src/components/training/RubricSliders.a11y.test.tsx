import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { useForm } from "react-hook-form";
import { RubricSliders } from "./RubricSliders";
import type { AttendanceFormValues } from "./AttendanceTable";

expect.extend(toHaveNoViolations);

function Wrapper({ disabled = false }: { disabled?: boolean }) {
  const { control } = useForm<AttendanceFormValues>({
    defaultValues: {
      status: "presente",
      excuse_reason: null,
      rpe_omni: 6,
      rubric_effort: 4,
      rubric_attitude: 3,
      rubric_technique: 5,
      individual_feedback: null,
    },
  });
  return <RubricSliders control={control} disabled={disabled} feedbackLength={0} />;
}

describe("RubricSliders — accesibilidad", () => {
  it("sin violaciones axe en estado normal", async () => {
    const { container } = render(<Wrapper />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en estado deshabilitado", async () => {
    const { container } = render(<Wrapper disabled />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("los 4 sliders (RPE + 3 rúbrica) tienen nombres accesibles", () => {
    render(<Wrapper />);
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(4);

    for (const slider of sliders) {
      const ariaLabel = slider.getAttribute("aria-label") ?? "";
      expect(ariaLabel.length).toBeGreaterThan(0);
    }
  });

  it("todos los sliders tienen aria-valuenow, aria-valuemin y aria-valuemax", () => {
    render(<Wrapper />);
    const sliders = screen.getAllByRole("slider");

    for (const slider of sliders) {
      expect(slider).toHaveAttribute("aria-valuenow");
      expect(slider).toHaveAttribute("aria-valuemin");
      expect(slider).toHaveAttribute("aria-valuemax");
    }
  });

  it("el slider RPE tiene rango 0-10", () => {
    render(<Wrapper />);
    const rpe = screen.getByRole("slider", { name: /RPE OMNI/i });
    expect(rpe).toHaveAttribute("aria-valuemin", "0");
    expect(rpe).toHaveAttribute("aria-valuemax", "10");
  });

  it("los 3 sliders de rúbrica tienen rango 1-5", () => {
    render(<Wrapper />);
    const sliders = screen.getAllByRole("slider");
    const rubricSliders = sliders.filter((s) => s.getAttribute("aria-valuemax") === "5");
    expect(rubricSliders).toHaveLength(3);

    for (const slider of rubricSliders) {
      expect(slider).toHaveAttribute("aria-valuemin", "1");
    }
  });
});
