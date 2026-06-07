import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

vi.mock("@/api/auth", () => ({
  validateResetToken: vi.fn(),
  confirmPasswordReset: vi.fn(),
}));

import { validateResetToken, confirmPasswordReset } from "@/api/auth";
import { ResetPasswordPage } from "../ResetPasswordPage";

expect.extend(toHaveNoViolations);

function renderPage(token = "tok-123") {
  return render(
    <MemoryRouter initialEntries={[`/restablecer-contrasena?token=${token}`]}>
      <Routes>
        <Route path="/restablecer-contrasena" element={<ResetPasswordPage />} />
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/recuperar-contrasena"
          element={<div>Solicitar enlace page</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra el formulario cuando el token es válido", async () => {
    vi.mocked(validateResetToken).mockResolvedValue({ valid: true });
    renderPage();
    expect(await screen.findByLabelText("Nueva contraseña")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirmar contraseña")).toBeInTheDocument();
  });

  it("muestra estado de enlace inválido cuando la validación falla", async () => {
    vi.mocked(validateResetToken).mockRejectedValue({
      response: { status: 410 },
    });
    renderPage();
    expect(
      await screen.findByText(/El enlace ha expirado o ya fue utilizado/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Solicitar un nuevo enlace" }),
    ).toBeInTheDocument();
  });

  it("valida que las contraseñas coincidan y la longitud mínima", async () => {
    vi.mocked(validateResetToken).mockResolvedValue({ valid: true });
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText("Nueva contraseña");

    await user.type(screen.getByLabelText("Nueva contraseña"), "short");
    await user.type(screen.getByLabelText("Confirmar contraseña"), "short");
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );
    expect(
      await screen.findByText("La contraseña debe tener al menos 8 caracteres"),
    ).toBeInTheDocument();
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("actualiza la contraseña y muestra el estado de éxito", async () => {
    vi.mocked(validateResetToken).mockResolvedValue({ valid: true });
    vi.mocked(confirmPasswordReset).mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    renderPage("tok-123");
    await screen.findByLabelText("Nueva contraseña");

    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPass456");
    await user.type(screen.getByLabelText("Confirmar contraseña"), "NewPass456");
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );

    await waitFor(() =>
      expect(confirmPasswordReset).toHaveBeenCalledWith({
        token: "tok-123",
        new_password: "NewPass456",
      }),
    );
    expect(
      await screen.findByText(/Tu contraseña fue actualizada/),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con el formulario visible", async () => {
    vi.mocked(validateResetToken).mockResolvedValue({ valid: true });
    const { container } = renderPage();
    await screen.findByLabelText("Nueva contraseña");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
