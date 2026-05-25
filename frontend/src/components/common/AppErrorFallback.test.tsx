import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppErrorFallback } from "@/components/common/AppErrorFallback";

describe("AppErrorFallback", () => {
  it("muestra el mensaje en español", () => {
    render(
      <AppErrorFallback
        error={new Error("kaboom")}
        resetErrorBoundary={() => {}}
      />,
    );
    expect(
      screen.getByText(/ha ocurrido un error inesperado/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/aplicación encontró un problema/i),
    ).toBeInTheDocument();
  });

  it("renderiza botón Reintentar que llama a resetErrorBoundary", async () => {
    const reset = vi.fn();
    render(
      <AppErrorFallback error={new Error("kaboom")} resetErrorBoundary={reset} />,
    );
    const btn = screen.getByRole("button", { name: /reintentar/i });
    await userEvent.click(btn);
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("incluye un link mailto para reportar al equipo", () => {
    render(
      <AppErrorFallback
        error={new Error("kaboom")}
        resetErrorBoundary={() => {}}
      />,
    );
    const link = screen.getByRole("link", { name: /reportar al equipo/i });
    expect(link).toHaveAttribute(
      "href",
      expect.stringMatching(/^mailto:[^?]+\?subject=.+&body=.+$/),
    );
  });

  it("usa role=alert con aria-live=assertive para anunciar el error", () => {
    render(
      <AppErrorFallback
        error={new Error("kaboom")}
        resetErrorBoundary={() => {}}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("aria-live", "assertive");
  });
});
