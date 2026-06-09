/**
 * Tests for ConfirmEmailChangePage — spec 004-user-profile.
 *
 * Tests the full state machine:
 *  - checking → success (200)
 *  - checking → not-found (404)
 *  - checking → expired (410)
 *  - checking → conflict (409)
 *  - checking → error (generic failure)
 *  - missing token → not-found (no API call)
 *  - Accessibility (jest-axe, 0 violations on final states)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

vi.mock("@/api/profile", () => ({
  confirmEmailChange: vi.fn(),
}));

import { confirmEmailChange } from "@/api/profile";
import { ConfirmEmailChangePage } from "../ConfirmEmailChangePage";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage(token?: string) {
  const search = token ? `?token=${token}` : "";
  return render(
    <MemoryRouter
      initialEntries={[`/confirmar-correo${search}`]}
    >
      <Routes>
        <Route
          path="/confirmar-correo"
          element={<ConfirmEmailChangePage />}
        />
        <Route path="/login" element={<div>Login</div>} />
        <Route path="/perfil" element={<div>Perfil</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function makeAxiosError(status: number) {
  return {
    isAxiosError: true,
    response: { status, data: { detail: "error" } },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConfirmEmailChangePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra 'Verificando enlace...' mientras procesa", () => {
    vi.mocked(confirmEmailChange).mockImplementation(
      () => new Promise(() => {}), // never resolves
    );
    renderPage("some-token");
    expect(screen.getByText("Verificando enlace...")).toBeInTheDocument();
  });

  it("muestra éxito cuando el token es válido (200)", async () => {
    vi.mocked(confirmEmailChange).mockResolvedValue({
      message:
        "Tu correo fue actualizado. Inicia sesión con tu nueva dirección.",
    });
    renderPage("valid-token");

    await waitFor(() =>
      expect(
        screen.getByText(/Tu correo fue actualizado/),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: "Ir a iniciar sesión" }),
    ).toBeInTheDocument();
    expect(confirmEmailChange).toHaveBeenCalledWith({ token: "valid-token" });
  });

  it("muestra estado 'enlace no válido' para error 404", async () => {
    vi.mocked(confirmEmailChange).mockRejectedValue(makeAxiosError(404));
    renderPage("bad-token");

    await waitFor(() =>
      expect(screen.getByText(/Enlace no válido/)).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: "Volver a mi perfil" }),
    ).toBeInTheDocument();
  });

  it("muestra estado 'expirado o ya utilizado' para error 410", async () => {
    vi.mocked(confirmEmailChange).mockRejectedValue(makeAxiosError(410));
    renderPage("expired-token");

    await waitFor(() =>
      expect(
        screen.getByText(/El enlace ha expirado o ya fue utilizado/),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: "Solicitar nuevamente" }),
    ).toBeInTheDocument();
  });

  it("muestra estado de conflicto para error 409", async () => {
    vi.mocked(confirmEmailChange).mockRejectedValue(makeAxiosError(409));
    renderPage("conflict-token");

    await waitFor(() =>
      expect(
        screen.getByText(/No se pudo aplicar el cambio/),
      ).toBeInTheDocument(),
    );
  });

  it("muestra error genérico para fallo inesperado", async () => {
    vi.mocked(confirmEmailChange).mockRejectedValue(new Error("network error"));
    renderPage("some-token");

    await waitFor(() =>
      expect(
        screen.getByText(/No fue posible procesar la solicitud/),
      ).toBeInTheDocument(),
    );
  });

  it("muestra 'enlace no válido' si no hay token en la URL (sin llamar al API)", async () => {
    renderPage(); // no token
    await waitFor(() =>
      expect(screen.getByText(/Enlace no válido/)).toBeInTheDocument(),
    );
    expect(confirmEmailChange).not.toHaveBeenCalled();
  });

  // ── Accessibility ───────────────────────────────────────────────────────

  it("no tiene violaciones de accesibilidad en estado de éxito", async () => {
    vi.mocked(confirmEmailChange).mockResolvedValue({
      message: "Tu correo fue actualizado. Inicia sesión con tu nueva dirección.",
    });
    const { container } = renderPage("valid-token");
    await screen.findByText(/Tu correo fue actualizado/);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad en estado expirado", async () => {
    vi.mocked(confirmEmailChange).mockRejectedValue(makeAxiosError(410));
    const { container } = renderPage("expired-token");
    await screen.findByText(/El enlace ha expirado/);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
