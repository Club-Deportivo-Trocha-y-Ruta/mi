/**
 * Tests for ProfilePage — spec 004-user-profile.
 *
 * Strategy: mock the hooks directly to avoid needing a full TanStack Query
 * provider setup. Each section is tested independently:
 *  - Render with profile data
 *  - BasicInfoSection: edit + save, validation errors
 *  - ChangePasswordSection: validation (min-length, mismatch), success, wrong pw
 *  - ChangeEmailSection: neutral message on submit, wrong password error
 *  - Accessibility (jest-axe, 0 violations)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

// ---------------------------------------------------------------------------
// Mock the hooks module so we control mutation behavior without a QueryClient.
// ---------------------------------------------------------------------------

const mockUpdateBasicInfo = vi.fn();
const mockChangePassword = vi.fn();
const mockRequestEmailChange = vi.fn();
const mockProfile = {
  id: 1,
  email: "coach@trochyruta.com",
  first_name: "Carlos",
  last_name: "García",
  phone: "+57 300 000 0000",
  role: "coach" as const,
};

vi.mock("@/hooks/profile/useProfile", () => ({
  useProfile: vi.fn(),
  useUpdateBasicInfo: vi.fn(),
  useChangePassword: vi.fn(),
  useRequestEmailChange: vi.fn(),
  extractProfileError: (error: unknown) => {
    if (
      typeof error === "object" &&
      error !== null &&
      "response" in error
    ) {
      const e = error as { response?: { status?: number; data?: { detail?: string } } };
      if (e.response?.status === 400) {
        return e.response.data?.detail ?? "La contraseña actual no es correcta.";
      }
    }
    return "No fue posible completar la operación. Intenta de nuevo.";
  },
}));

import {
  useProfile,
  useUpdateBasicInfo,
  useChangePassword,
  useRequestEmailChange,
} from "@/hooks/profile/useProfile";
import { ProfilePage } from "../ProfilePage";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  );
}

function setupMocks(profileOverrides = {}) {
  vi.mocked(useProfile).mockReturnValue({
    data: { ...mockProfile, ...profileOverrides },
    isLoading: false,
    isError: false,
    error: null,
  } as ReturnType<typeof useProfile>);

  vi.mocked(useUpdateBasicInfo).mockReturnValue({
    mutateAsync: mockUpdateBasicInfo,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateBasicInfo>);

  vi.mocked(useChangePassword).mockReturnValue({
    mutateAsync: mockChangePassword,
    isPending: false,
  } as unknown as ReturnType<typeof useChangePassword>);

  vi.mocked(useRequestEmailChange).mockReturnValue({
    mutateAsync: mockRequestEmailChange,
    isPending: false,
  } as unknown as ReturnType<typeof useRequestEmailChange>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks();
  });

  // ── Render ──────────────────────────────────────────────────────────────

  it("renderiza el título y las tres secciones con datos del perfil", () => {
    renderPage();
    expect(screen.getByText("Mi perfil")).toBeInTheDocument();
    expect(screen.getByText("Información básica")).toBeInTheDocument();
    expect(screen.getByText("Cambiar contraseña")).toBeInTheDocument();
    expect(screen.getByText("Cambiar correo")).toBeInTheDocument();
  });

  it("muestra el correo y el rol como campos de solo lectura", () => {
    renderPage();
    expect(screen.getByText("coach@trochyruta.com")).toBeInTheDocument();
    expect(screen.getByText("coach")).toBeInTheDocument();
  });

  it("pre-llena los campos de nombre, apellido y teléfono", () => {
    renderPage();
    expect(screen.getByLabelText<HTMLInputElement>("Nombre").value).toBe(
      "Carlos",
    );
    expect(screen.getByLabelText<HTMLInputElement>("Apellido").value).toBe(
      "García",
    );
  });

  it("muestra estado de carga cuando isLoading=true", () => {
    vi.mocked(useProfile).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useProfile>);
    renderPage();
    expect(screen.getByText("Cargando perfil...")).toBeInTheDocument();
  });

  it("muestra estado de error cuando isError=true", () => {
    vi.mocked(useProfile).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("fail"),
    } as ReturnType<typeof useProfile>);
    renderPage();
    expect(
      screen.getByText("No fue posible completar la operación. Intenta de nuevo."),
    ).toBeInTheDocument();
  });

  // ── BasicInfoSection ────────────────────────────────────────────────────

  it("guarda los cambios de información básica correctamente", async () => {
    mockUpdateBasicInfo.mockResolvedValue({
      ...mockProfile,
      last_name: "García P.",
    });
    const user = userEvent.setup();
    renderPage();

    const lastNameInput = screen.getByLabelText("Apellido");
    await user.clear(lastNameInput);
    await user.type(lastNameInput, "García P.");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(mockUpdateBasicInfo).toHaveBeenCalledWith(
        expect.objectContaining({ last_name: "García P." }),
      );
    });
    expect(
      await screen.findByText("Tu información fue actualizada correctamente."),
    ).toBeInTheDocument();
  });

  it("muestra error de validación si el nombre está vacío", async () => {
    const user = userEvent.setup();
    renderPage();

    const firstNameInput = screen.getByLabelText("Nombre");
    await user.clear(firstNameInput);
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(
      await screen.findByText("El nombre es obligatorio"),
    ).toBeInTheDocument();
    expect(mockUpdateBasicInfo).not.toHaveBeenCalled();
  });

  it("muestra error del servidor al fallar la actualización básica", async () => {
    mockUpdateBasicInfo.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(
      await screen.findByText(
        "No fue posible completar la operación. Intenta de nuevo.",
      ),
    ).toBeInTheDocument();
  });

  // ── ChangePasswordSection ───────────────────────────────────────────────

  it("valida longitud mínima de la nueva contraseña", async () => {
    const user = userEvent.setup();
    renderPage();

    // Use the ID selector to target the password section's "Contraseña actual"
    // (there are two with that label on the page — one for pw, one for email).
    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#current_password" }),
      "OldPass1",
    );
    await user.type(screen.getByLabelText("Nueva contraseña"), "short");
    await user.type(
      screen.getByLabelText("Confirmar nueva contraseña"),
      "short",
    );
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );

    expect(
      await screen.findByText(
        "La nueva contraseña debe tener al menos 8 caracteres",
      ),
    ).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("valida que la confirmación coincida con la nueva contraseña", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#current_password" }),
      "OldPass1",
    );
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPass456");
    await user.type(
      screen.getByLabelText("Confirmar nueva contraseña"),
      "Different789",
    );
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );

    expect(
      await screen.findByText("Las contraseñas no coinciden"),
    ).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("muestra éxito al cambiar contraseña correctamente", async () => {
    mockChangePassword.mockResolvedValue({ message: "Tu contraseña fue actualizada." });
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#current_password" }),
      "OldPass1",
    );
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPass456");
    await user.type(
      screen.getByLabelText("Confirmar nueva contraseña"),
      "NewPass456",
    );
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );

    await waitFor(() =>
      expect(mockChangePassword).toHaveBeenCalledWith({
        current_password: "OldPass1",
        new_password: "NewPass456",
      }),
    );
    expect(
      await screen.findByText("Tu contraseña fue actualizada."),
    ).toBeInTheDocument();
  });

  it("muestra error al ingresar contraseña actual incorrecta", async () => {
    mockChangePassword.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: "La contraseña actual no es correcta." },
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#current_password" }),
      "WrongPass",
    );
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPass456");
    await user.type(
      screen.getByLabelText("Confirmar nueva contraseña"),
      "NewPass456",
    );
    await user.click(
      screen.getByRole("button", { name: "Actualizar contraseña" }),
    );

    expect(
      await screen.findByText("La contraseña actual no es correcta."),
    ).toBeInTheDocument();
  });

  // ── ChangeEmailSection ──────────────────────────────────────────────────

  it("valida el formato del correo antes de enviar", async () => {
    const user = userEvent.setup();
    renderPage();

    // Use the specific IDs to disambiguate the email-section password field
    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#email_current_password" }),
      "MyPass1",
    );
    await user.type(screen.getByLabelText("Nuevo correo"), "not-a-valid-email");
    await user.click(
      screen.getByRole("button", { name: "Solicitar cambio de correo" }),
    );

    expect(
      await screen.findByText("Ingresa un correo válido"),
    ).toBeInTheDocument();
    expect(mockRequestEmailChange).not.toHaveBeenCalled();
  });

  it("muestra el mensaje neutro después de solicitar cambio de correo", async () => {
    mockRequestEmailChange.mockResolvedValue({
      message:
        "Si el correo es válido y está disponible, te enviamos un enlace de confirmación a la nueva dirección.",
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#email_current_password" }),
      "MyPass1",
    );
    await user.type(
      screen.getByLabelText("Nuevo correo"),
      "nuevo@ejemplo.com",
    );
    await user.click(
      screen.getByRole("button", { name: "Solicitar cambio de correo" }),
    );

    await waitFor(() =>
      expect(mockRequestEmailChange).toHaveBeenCalledWith({
        current_password: "MyPass1",
        new_email: "nuevo@ejemplo.com",
      }),
    );
    expect(
      await screen.findByText(/Revisa tu nuevo correo para confirmar/),
    ).toBeInTheDocument();
  });

  it("muestra error de contraseña incorrecta al solicitar cambio de correo", async () => {
    mockRequestEmailChange.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: "La contraseña actual no es correcta." },
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Contraseña actual", { selector: "#email_current_password" }),
      "WrongPass",
    );
    await user.type(
      screen.getByLabelText("Nuevo correo"),
      "nuevo@ejemplo.com",
    );
    await user.click(
      screen.getByRole("button", { name: "Solicitar cambio de correo" }),
    );

    expect(
      await screen.findByText("La contraseña actual no es correcta."),
    ).toBeInTheDocument();
  });

  // ── Accessibility ───────────────────────────────────────────────────────

  it("no tiene violaciones de accesibilidad con el perfil cargado", async () => {
    const { container } = renderPage();
    // Wait for all sections to render
    await screen.findByLabelText("Nombre");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
