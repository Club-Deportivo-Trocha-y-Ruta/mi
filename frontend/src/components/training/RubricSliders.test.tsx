import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  describe("grupo RPE OMNI", () => {
    it("no renderiza ningún input de rango (role=slider)", () => {
      render(<Wrapper />);
      expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    });

    it("renderiza como ToggleGroup con 11 opciones discretas (0-10)", () => {
      render(<Wrapper />);
      const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
      const options = within(group).getAllByRole("radio");
      expect(options).toHaveLength(11);
    });

    it("muestra el valor inicial seleccionado", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 7 }} />);
      const selected = screen.getByRole("radio", {
        name: "RPE OMNI 0-10: 7 — Duro",
        checked: true,
      });
      expect(selected).toBeInTheDocument();
    });

    it("aria-checked refleja el valor y solo una opción está seleccionada", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 3 }} />);
      const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
      const checked = within(group).getAllByRole("radio", { checked: true });
      expect(checked).toHaveLength(1);
      expect(checked[0]).toHaveAccessibleName("RPE OMNI 0-10: 3 — Ligero");
    });
  });

  describe("grupos de rúbrica 1-5 (Esfuerzo/Actitud/Técnica)", () => {
    it("Esfuerzo renderiza como ToggleGroup con 5 opciones discretas", () => {
      render(<Wrapper />);
      const group = screen.getByRole("group", { name: "Esfuerzo" });
      expect(within(group).getAllByRole("radio")).toHaveLength(5);
    });

    it("Actitud renderiza como ToggleGroup con 5 opciones discretas", () => {
      render(<Wrapper />);
      const group = screen.getByRole("group", { name: "Actitud" });
      expect(within(group).getAllByRole("radio")).toHaveLength(5);
    });

    it("Técnica renderiza como ToggleGroup con 5 opciones discretas", () => {
      render(<Wrapper />);
      const group = screen.getByRole("group", { name: "Técnica" });
      expect(within(group).getAllByRole("radio")).toHaveLength(5);
    });

    it("Esfuerzo marca la opción del valor inicial como seleccionada", () => {
      render(<Wrapper defaultValues={{ rubric_effort: 4 }} />);
      const group = screen.getByRole("group", { name: "Esfuerzo" });
      const selected = within(group).getByRole("radio", { checked: true });
      expect(selected).toHaveAccessibleName("Esfuerzo: 4 — Bueno");
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

  describe("RPE_LABELS contract (G1–G3)", () => {
    it("G1 — muestra 'Moderado' en valor 5", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 5 }} />);
      expect(screen.getByText("5 — Moderado")).toBeInTheDocument();
    });

    it("G2 — valor 3 NO muestra 'Moderado' (defecto corregido)", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 3 }} />);
      expect(screen.queryByText("3 — Moderado")).not.toBeInTheDocument();
    });

    it("G3 — extremo inferior es 'Reposo' (valor 0)", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 0 }} />);
      expect(screen.getByText("0 — Reposo")).toBeInTheDocument();
    });

    it("G3 — extremo superior es 'Máximo' (valor 10)", () => {
      render(<Wrapper defaultValues={{ rpe_omni: 10 }} />);
      expect(screen.getByText("10 — Máximo")).toBeInTheDocument();
    });
  });

  describe("disabled", () => {
    it("todas las opciones de los 4 grupos quedan deshabilitadas cuando disabled=true", () => {
      render(<Wrapper disabled />);
      const options = screen.getAllByRole("radio");
      expect(options).toHaveLength(11 + 5 + 5 + 5);
      options.forEach((o) => expect(o).toBeDisabled());
    });

    it("textarea deshabilitado cuando disabled=true", () => {
      render(<Wrapper disabled />);
      const textarea = screen.getByRole("textbox", { name: /Comentario del coach/i });
      expect(textarea).toBeDisabled();
    });
  });

  describe("selección dispara field.onChange (wiring de autosave)", () => {
    it("clickear una opción de Esfuerzo actualiza el valor mostrado", async () => {
      const user = userEvent.setup();
      render(<Wrapper defaultValues={{ rubric_effort: 3 }} />);
      // Esfuerzo/Actitud/Técnica comparten el valor por defecto (3 — Regular),
      // así que el texto visible se acota a la sección de Esfuerzo.
      const section = screen.getByText("Esfuerzo").closest("div.space-y-1") as HTMLElement;
      expect(within(section).getByText("3 — Regular")).toBeInTheDocument();

      const group = screen.getByRole("group", { name: "Esfuerzo" });
      await user.click(
        within(group).getByRole("radio", { name: "Esfuerzo: 5 — Excelente" }),
      );

      expect(within(section).getByText("5 — Excelente")).toBeInTheDocument();
      expect(
        within(group).getByRole("radio", { name: "Esfuerzo: 5 — Excelente" }),
      ).toHaveAttribute("aria-checked", "true");
      expect(
        within(group).getByRole("radio", { name: "Esfuerzo: 3 — Regular" }),
      ).toHaveAttribute("aria-checked", "false");
    });

    it("clickear una opción de RPE OMNI actualiza el valor mostrado", async () => {
      const user = userEvent.setup();
      render(<Wrapper defaultValues={{ rpe_omni: 5 }} />);
      expect(screen.getByText("5 — Moderado")).toBeInTheDocument();

      const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
      await user.click(
        within(group).getByRole("radio", { name: "RPE OMNI 0-10: 8 — Muy duro" }),
      );

      expect(screen.getByText("8 — Muy duro")).toBeInTheDocument();
      expect(
        within(group).getByRole("radio", { name: "RPE OMNI 0-10: 8 — Muy duro" }),
      ).toHaveAttribute("aria-checked", "true");
    });

    it("no dispara onChange cuando está disabled (click no cambia selección)", async () => {
      const user = userEvent.setup();
      render(<Wrapper disabled defaultValues={{ rubric_attitude: 3 }} />);
      const group = screen.getByRole("group", { name: "Actitud" });
      const target = within(group).getByRole("radio", { name: "Actitud: 1 — Muy bajo" });
      await user.click(target);

      expect(target).toHaveAttribute("aria-checked", "false");
      expect(
        within(group).getByRole("radio", { name: "Actitud: 3 — Regular" }),
      ).toHaveAttribute("aria-checked", "true");
    });
  });
});
