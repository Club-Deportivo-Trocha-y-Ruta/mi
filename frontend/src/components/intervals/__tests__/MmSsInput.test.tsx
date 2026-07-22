/**
 * Tests para MmSsInput (feature 034, T005):
 *   - Helpers puros `splitSeconds`/`combineMmSs`: round-trip segundos ⇄
 *     (min, seg), Seg acotado 0–59, `null` en ambos campos vacíos.
 *   - Componente: renderiza Min/Seg con las etiquetas accesibles
 *     "Minutos"/"Segundos"; hidrata un valor existente; reporta el valor
 *     combinado en segundos al tipear; normaliza Seg > 59 a 59; `value=null`
 *     deja ambos campos vacíos; `disabled` deshabilita ambos campos.
 */
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MmSsInput, splitSeconds, combineMmSs } from "../MmSsInput";

// ---------------------------------------------------------------------------
// Suite: helpers puros
// ---------------------------------------------------------------------------

describe("splitSeconds — función pura", () => {
  it("descompone 300 en { min: '5', sec: '0' }", () => {
    expect(splitSeconds(300)).toEqual({ min: "5", sec: "0" });
  });

  it("descompone 90 en { min: '1', sec: '30' }", () => {
    expect(splitSeconds(90)).toEqual({ min: "1", sec: "30" });
  });

  it("null/undefined ⇒ ambos campos vacíos", () => {
    expect(splitSeconds(null)).toEqual({ min: "", sec: "" });
    expect(splitSeconds(undefined)).toEqual({ min: "", sec: "" });
  });
});

describe("combineMmSs — función pura", () => {
  it("combina '5'/'0' en 300", () => {
    expect(combineMmSs("5", "0")).toBe(300);
  });

  it("combina '1'/'30' en 90", () => {
    expect(combineMmSs("1", "30")).toBe(90);
  });

  it("ambos vacíos ⇒ null", () => {
    expect(combineMmSs("", "")).toBeNull();
  });

  it("min vacío + seg con valor ⇒ trata el vacío como 0", () => {
    expect(combineMmSs("", "30")).toBe(30);
  });

  it("seg vacío + min con valor ⇒ trata el vacío como 0", () => {
    expect(combineMmSs("5", "")).toBe(300);
  });

  it("acota seg > 59 a 59 (defensa adicional, aunque el handler ya normaliza)", () => {
    expect(combineMmSs("1", "75")).toBe(1 * 60 + 59);
  });

  it("'0'/'0' ⇒ 0 (no se confunde con 'sin valor')", () => {
    expect(combineMmSs("0", "0")).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Suite: componente
// ---------------------------------------------------------------------------

function setup(overrides: Partial<ComponentProps<typeof MmSsInput>> = {}) {
  const onChange = vi.fn();
  const props = {
    id: "duration",
    label: "Duración",
    value: null,
    onChange,
    ...overrides,
  };
  return { ...render(<MmSsInput {...props} />), onChange };
}

describe("MmSsInput — render e hidratación", () => {
  it("renderiza los campos con las etiquetas accesibles 'Minutos' y 'Segundos'", () => {
    setup();
    expect(screen.getByLabelText("Minutos")).toBeInTheDocument();
    expect(screen.getByLabelText("Segundos")).toBeInTheDocument();
  });

  it("hidrata un valor existente (300s ⇒ Min=5, Seg=0)", () => {
    setup({ value: 300 });
    expect(screen.getByLabelText("Minutos")).toHaveValue(5);
    expect(screen.getByLabelText("Segundos")).toHaveValue(0);
  });

  it("value=null deja ambos campos vacíos", () => {
    setup({ value: null });
    expect(screen.getByLabelText("Minutos")).toHaveValue(null);
    expect(screen.getByLabelText("Segundos")).toHaveValue(null);
  });

  it("usa el id provisto para los campos internos", () => {
    setup({ id: "block-2-duration" });
    expect(document.getElementById("block-2-duration-min")).not.toBeNull();
    expect(document.getElementById("block-2-duration-sec")).not.toBeNull();
  });
});

describe("MmSsInput — edición", () => {
  it("tipear en Minutos reporta el valor combinado en segundos", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ value: 300 }); // 5:00

    const min = screen.getByLabelText("Minutos");
    await user.clear(min);
    await user.type(min, "1");

    // Min=1, Seg conserva 0 ⇒ 60s
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it("tipear en Segundos reporta el valor combinado en segundos", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ value: 60 }); // 1:00

    const sec = screen.getByLabelText("Segundos");
    await user.clear(sec);
    await user.type(sec, "30");

    expect(onChange).toHaveBeenLastCalledWith(90);
  });

  it("normaliza Segundos > 59 a 59 de inmediato (FR-002)", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ value: 60 });

    const sec = screen.getByLabelText("Segundos");
    await user.clear(sec);
    await user.type(sec, "75");

    expect(sec).toHaveValue(59);
    expect(onChange).toHaveBeenLastCalledWith(60 + 59);
  });

  it("limpiar ambos campos reporta null", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ value: 300 });

    await user.clear(screen.getByLabelText("Minutos"));
    await user.clear(screen.getByLabelText("Segundos"));

    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("disabled deshabilita ambos campos", () => {
    setup({ value: 300, disabled: true });
    expect(screen.getByLabelText("Minutos")).toBeDisabled();
    expect(screen.getByLabelText("Segundos")).toBeDisabled();
  });

  it("muestra el mensaje de error con role=alert y aria-invalid en ambos campos", () => {
    setup({ error: "La duración debe ser mayor a 0 segundos." });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "La duración debe ser mayor a 0 segundos.",
    );
    expect(screen.getByLabelText("Minutos")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Segundos")).toHaveAttribute("aria-invalid", "true");
  });
});
