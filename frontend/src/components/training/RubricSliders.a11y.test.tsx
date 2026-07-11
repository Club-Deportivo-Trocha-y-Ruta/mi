import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
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

const GROUP_NAMES = ["RPE OMNI 0-10", "Esfuerzo", "Actitud", "Técnica"];

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

  it("no renderiza ningún input de rango (role=slider) — reemplazado por ToggleGroup", () => {
    render(<Wrapper />);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: /RPE OMNI/i })).not.toBeInTheDocument();
  });

  it("los 4 grupos (RPE + 3 rúbrica) se renderizan como ToggleGroup (role=group) con nombre accesible", () => {
    render(<Wrapper />);
    for (const name of GROUP_NAMES) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument();
    }
  });

  it("el grupo RPE OMNI expone 11 opciones discretas con nombre accesible", () => {
    render(<Wrapper />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    const options = within(group).getAllByRole("radio");
    expect(options).toHaveLength(11);

    for (const option of options) {
      const accessibleName = option.getAttribute("aria-label") ?? "";
      expect(accessibleName.length).toBeGreaterThan(0);
      expect(option).toHaveAttribute("aria-checked");
    }
  });

  it("los 3 grupos de rúbrica exponen 5 opciones discretas con nombre accesible", () => {
    render(<Wrapper />);
    for (const name of ["Esfuerzo", "Actitud", "Técnica"]) {
      const group = screen.getByRole("group", { name });
      const options = within(group).getAllByRole("radio");
      expect(options).toHaveLength(5);

      for (const option of options) {
        const accessibleName = option.getAttribute("aria-label") ?? "";
        expect(accessibleName.length).toBeGreaterThan(0);
        expect(option).toHaveAttribute("aria-checked");
      }
    }
  });

  it("cada grupo tiene exactamente una opción marcada (aria-checked=true)", () => {
    render(<Wrapper />);
    for (const name of GROUP_NAMES) {
      const group = screen.getByRole("group", { name });
      const checked = within(group).getAllByRole("radio", { checked: true });
      expect(checked).toHaveLength(1);
    }
  });

  it("todas las opciones quedan deshabilitadas (no solo visualmente) cuando disabled=true", () => {
    render(<Wrapper disabled />);
    const options = screen.getAllByRole("radio");
    expect(options.length).toBeGreaterThan(0);
    options.forEach((o) => expect(o).toBeDisabled());
  });
});
