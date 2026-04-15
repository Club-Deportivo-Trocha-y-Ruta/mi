import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import axios from "axios";

import { ParentRegisterPage } from "../ParentRegisterPage";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/auth", () => ({
  validateInviteToken: vi.fn(),
  registerParent: vi.fn(),
  login: vi.fn(),
  refreshToken: vi.fn(),
  getMe: vi.fn(),
}));

// import after mock (Vitest hoists vi.mock automatically)
import { validateInviteToken, registerParent } from "@/api/auth";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithToken(token?: string) {
  const url = token ? `/registro-padre?token=${token}` : "/registro-padre";
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/registro-padre" element={<ParentRegisterPage />} />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const validTokenData = {
  athlete_id: 5,
  athlete_name: "Santiago López",
  email: "padre@example.com",
  expires_at: "2026-12-31T00:00:00Z",
  valid: true,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ParentRegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Sin token en la URL
  // -------------------------------------------------------------------------
  it("sin token en la URL muestra 'Invitación inválida o expirada'", async () => {
    renderWithToken();

    await waitFor(() => {
      expect(screen.getByText("Invitación inválida o expirada")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Token inválido (valid: false)
  // -------------------------------------------------------------------------
  it("token inválido (valid: false) muestra estado de error", async () => {
    vi.mocked(validateInviteToken).mockResolvedValue({
      ...validTokenData,
      valid: false,
    });

    renderWithToken("token-invalido");

    await waitFor(() => {
      expect(screen.getByText("Invitación inválida o expirada")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Error de red en validateInviteToken
  // -------------------------------------------------------------------------
  it("error de red en validateInviteToken muestra estado inválido", async () => {
    vi.mocked(validateInviteToken).mockRejectedValue(new Error("Network error"));

    renderWithToken("token-red-error");

    await waitFor(() => {
      expect(screen.getByText("Invitación inválida o expirada")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Token válido → muestra formulario con email pre-rellenado
  // -------------------------------------------------------------------------
  it("token válido muestra formulario con email pre-rellenado (readonly)", async () => {
    vi.mocked(validateInviteToken).mockResolvedValue(validTokenData);

    renderWithToken("token-valido");

    await waitFor(() => {
      const emailInput = screen.getByRole("textbox", { name: /correo/i });
      expect(emailInput).toBeInTheDocument();
      expect(emailInput).toHaveValue("padre@example.com");
      expect(emailInput).toHaveAttribute("readonly");
    });
  });

  // -------------------------------------------------------------------------
  // Submit exitoso
  // -------------------------------------------------------------------------
  it("submit exitoso muestra '¡Cuenta creada exitosamente!'", async () => {
    vi.mocked(validateInviteToken).mockResolvedValue(validTokenData);
    vi.mocked(registerParent).mockResolvedValue({
      id: 1,
      email: "padre@example.com",
      first_name: "Carlos",
      last_name: "García",
      message: "ok",
    });

    renderWithToken("token-valido");

    // Esperar el formulario
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: /nombre/i })).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: /nombre/i }), "Carlos");
    await user.type(screen.getByRole("textbox", { name: /apellido/i }), "García");
    await user.type(screen.getByLabelText(/contraseña/i), "Password123!");

    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    await waitFor(() => {
      expect(screen.getByText("¡Cuenta creada exitosamente!")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Submit falla con HTTP 410
  // -------------------------------------------------------------------------
  it("submit falla con 410 muestra 'La invitación expiró o ya fue usada.'", async () => {
    vi.mocked(validateInviteToken).mockResolvedValue(validTokenData);

    const axiosError = new axios.AxiosError(
      "Gone",
      "ERR_BAD_RESPONSE",
      undefined,
      undefined,
      { status: 410, data: {} } as any,
    );
    vi.mocked(registerParent).mockRejectedValue(axiosError);

    renderWithToken("token-expirado");

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: /nombre/i })).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: /nombre/i }), "Carlos");
    await user.type(screen.getByRole("textbox", { name: /apellido/i }), "García");
    await user.type(screen.getByLabelText(/contraseña/i), "Password123!");

    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    await waitFor(() => {
      expect(
        screen.getByText("La invitación expiró o ya fue usada."),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Submit falla con HTTP 409
  // -------------------------------------------------------------------------
  it("submit falla con 409 muestra 'Ya existe una cuenta con este correo.'", async () => {
    vi.mocked(validateInviteToken).mockResolvedValue(validTokenData);

    const axiosError = new axios.AxiosError(
      "Conflict",
      "ERR_BAD_RESPONSE",
      undefined,
      undefined,
      { status: 409, data: {} } as any,
    );
    vi.mocked(registerParent).mockRejectedValue(axiosError);

    renderWithToken("token-conflicto");

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: /nombre/i })).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: /nombre/i }), "Carlos");
    await user.type(screen.getByRole("textbox", { name: /apellido/i }), "García");
    await user.type(screen.getByLabelText(/contraseña/i), "Password123!");

    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Ya existe una cuenta con este correo."),
      ).toBeInTheDocument();
    });
  });
});
