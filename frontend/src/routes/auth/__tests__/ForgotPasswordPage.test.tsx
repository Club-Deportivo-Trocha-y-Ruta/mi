import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

vi.mock("@/api/auth", () => ({
  requestPasswordReset: vi.fn(),
}));

import { requestPasswordReset } from "@/api/auth";
import { ForgotPasswordPage } from "../ForgotPasswordPage";

expect.extend(toHaveNoViolations);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/recuperar-contrasena"]}>
      <Routes>
        <Route path="/recuperar-contrasena" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza el formulario de solicitud", () => {
    renderPage();
    expect(screen.getByLabelText("Correo")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enviar enlace" }),
    ).toBeInTheDocument();
  });

  it("muestra error de validación con correo inválido", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Correo"), "no-es-correo");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));
    expect(await screen.findByText("Ingresa un correo válido")).toBeInTheDocument();
    expect(requestPasswordReset).not.toHaveBeenCalled();
  });

  it("envía y muestra confirmación neutral", async () => {
    vi.mocked(requestPasswordReset).mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Correo"), "coach@test.com");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));

    await waitFor(() =>
      expect(requestPasswordReset).toHaveBeenCalledWith({
        email: "coach@test.com",
      }),
    );
    expect(
      await screen.findByText(/Si el correo está registrado/),
    ).toBeInTheDocument();
  });

  it("muestra error genérico ante fallo del servidor", async () => {
    vi.mocked(requestPasswordReset).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("Correo"), "coach@test.com");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));
    expect(
      await screen.findByText(/No fue posible procesar tu solicitud/),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
