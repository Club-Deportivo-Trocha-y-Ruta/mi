import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { StatusStepper, currentStepFromStatus } from "@/components/newsletter/studio/StatusStepper";

describe("currentStepFromStatus", () => {
  it("draft → draft", () => {
    expect(currentStepFromStatus("draft", null)).toBe("draft");
  });
  it("approved → approved", () => {
    expect(currentStepFromStatus("approved", null)).toBe("approved");
  });
  it("sent sin read_at → sent", () => {
    expect(currentStepFromStatus("sent", null)).toBe("sent");
  });
  it("sent con read_at → read", () => {
    expect(currentStepFromStatus("sent", "2026-07-05T09:00:00Z")).toBe("read");
  });
});

describe("StatusStepper", () => {
  it("muestra los 4 estados incluido Leído", () => {
    render(<StatusStepper status="sent" readAt="2026-07-05T09:00:00Z" />);
    expect(screen.getByTestId("stepper-step-draft")).toHaveTextContent("Borrador");
    expect(screen.getByTestId("stepper-step-approved")).toHaveTextContent("Aprobado");
    expect(screen.getByTestId("stepper-step-sent")).toHaveTextContent("Enviado");
    expect(screen.getByTestId("stepper-step-read")).toHaveTextContent("Leído");
  });

  it("marca el paso actual con aria-current=step", () => {
    render(<StatusStepper status="approved" readAt={null} />);
    expect(screen.getByTestId("stepper-step-approved")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.getByTestId("stepper-step-draft")).not.toHaveAttribute("aria-current");
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(<StatusStepper status="sent" readAt={null} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
