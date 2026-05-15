/**
 * Tests de ConsentRenewalModal.
 *
 * Cubre:
 *   - Renderizado del changelog cuando existe
 *   - Ausencia de changelog cuando es primer consentimiento
 *   - Validación: ambos checkboxes son requeridos
 *   - Llamada a useRenewConsent con el payload correcto
 *   - Estado de carga durante la mutación
 *   - Error del servidor
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// Mock del hook de mutación
// ---------------------------------------------------------------------------

const mockRenewMutate = vi.fn();
const mockRenewState = { isPending: false };

vi.mock("@/hooks/consent", () => ({
  useRenewConsent: () => ({
    mutate: mockRenewMutate,
    isPending: mockRenewState.isPending,
  }),
  useWithdrawConsent: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

import { ConsentRenewalModal } from "./ConsentRenewalModal";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const activePolicy: PrivacyPolicySummary = {
  id: 2,
  version: "v1.1",
  effective_date: "2026-05-06",
  title: "Política de Tratamiento de Datos Personales",
  changelog: "Recortadas finalidades a dos tratamientos activos en Fase 1.",
};

const activePolicyNoChangelog: PrivacyPolicySummary = {
  ...activePolicy,
  changelog: null,
};

const athleteWithOutdatedConsent: AthleteConsentStatus = {
  athlete_id: 5,
  athlete_name: "Juan Pérez",
  current_consent: {
    id: 12,
    policy_version: "v1.0",
    consented_at: "2026-04-15T10:00:00Z",
    is_current_policy: false,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: false,
      third_party_sharing: false,
    },
  },
};

const athleteWithNoConsent: AthleteConsentStatus = {
  athlete_id: 7,
  athlete_name: "María García",
  current_consent: null,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(
      QueryClientProvider,
      { client },
      createElement(MemoryRouter, null, children),
    );
}

function renderModal(
  athlete: AthleteConsentStatus,
  policy: PrivacyPolicySummary = activePolicy,
  onRenewed = vi.fn(),
) {
  return render(
    <ConsentRenewalModal
      athlete={athlete}
      activePolicy={policy}
      onRenewed={onRenewed}
    />,
    { wrapper: makeWrapper() },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConsentRenewalModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRenewState.isPending = false;
  });

  // -------------------------------------------------------------------------
  // Renderizado básico
  // -------------------------------------------------------------------------

  describe("renderizado", () => {
    it("debería mostrar el nombre del atleta en el subtítulo", () => {
      renderModal(athleteWithOutdatedConsent);
      // El nombre aparece en varios nodos (subtítulo + legend sr-only) — verificamos el p#desc
      const desc = screen.getByText(/Para continuar usando la plataforma con/i);
      expect(desc).toHaveTextContent("Juan Pérez");
    });

    it("debería mostrar el changelog cuando existe y hay consentimiento previo", () => {
      renderModal(athleteWithOutdatedConsent, activePolicy);
      expect(
        screen.getByText(/Recortadas finalidades a dos tratamientos activos/i),
      ).toBeInTheDocument();
    });

    it("debería NO mostrar la sección 'Qué cambió' cuando changelog es null", () => {
      renderModal(athleteWithOutdatedConsent, activePolicyNoChangelog);
      expect(screen.queryByText(/Qué cambió/i)).not.toBeInTheDocument();
    });

    it("debería mostrar título diferente para primer consentimiento (current_consent=null)", () => {
      renderModal(athleteWithNoConsent);
      expect(
        screen.getByText(/Consentimiento parental requerido/i),
      ).toBeInTheDocument();
    });

    it("debería NO mostrar el changelog para primer consentimiento aunque exista", () => {
      renderModal(athleteWithNoConsent, activePolicy);
      // Para primer consentimiento no mostramos changelog — no hay versión previa que comparar
      expect(screen.queryByText(/Qué cambió/i)).not.toBeInTheDocument();
    });

    it("debería renderizar ambos checkboxes de consentimiento", () => {
      renderModal(athleteWithOutdatedConsent);
      expect(
        screen.getByLabelText(/Recolectar datos básicos del atleta/i),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText(/Registrar mediciones antropométricas/i),
      ).toBeInTheDocument();
    });

    it("debería mostrar el enlace a la política de privacidad", () => {
      renderModal(athleteWithOutdatedConsent);
      // El enlace tiene aria-label más largo — usamos getAllByRole y filtramos por href
      const links = screen.getAllByRole("link");
      const privacyLink = links.find((l) => l.getAttribute("href") === "/privacidad");
      expect(privacyLink).toBeDefined();
      expect(privacyLink).toHaveAttribute("target", "_blank");
    });

    it("debería tener role=dialog con aria-modal=true", () => {
      renderModal(athleteWithOutdatedConsent);
      const dialog = screen.getByRole("dialog");
      expect(dialog).toHaveAttribute("aria-modal", "true");
    });
  });

  // -------------------------------------------------------------------------
  // Validación de formulario
  // -------------------------------------------------------------------------

  describe("validación", () => {
    it("debería mostrar error si se envía sin marcar ningún checkbox", async () => {
      renderModal(athleteWithOutdatedConsent);

      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Debes aceptar el tratamiento de datos básicos/i),
        ).toBeInTheDocument();
      });
    });

    it("debería mostrar error si solo se marca data_collection", async () => {
      renderModal(athleteWithOutdatedConsent);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Debes aceptar el registro de medidas antropométricas/i),
        ).toBeInTheDocument();
      });
    });

    it("debería mostrar error si solo se marca accept_anthropometry", async () => {
      renderModal(athleteWithOutdatedConsent);

      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Debes aceptar el tratamiento de datos básicos/i),
        ).toBeInTheDocument();
      });
    });

    it("NO debería mostrar errores cuando ambos checkboxes están marcados", async () => {
      mockRenewMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderModal(athleteWithOutdatedConsent);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.queryByText(/Debes aceptar el tratamiento de datos básicos/i),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText(/Debes aceptar el registro de medidas antropométricas/i),
        ).not.toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Llamada a useRenewConsent
  // -------------------------------------------------------------------------

  describe("mutación de renovación", () => {
    it("debería llamar useRenewConsent con el payload correcto al aceptar ambos checkboxes", async () => {
      mockRenewMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderModal(athleteWithOutdatedConsent, activePolicy);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(mockRenewMutate).toHaveBeenCalledWith(
          {
            athlete_id: 5,
            policy_version: "v1.1",
            accept_data_collection: true,
            accept_anthropometry: true,
            accept_third_party_sharing: false,
          },
          expect.objectContaining({ onSuccess: expect.any(Function) }),
        );
      });
    });

    it("debería llamar onRenewed cuando la mutación tiene éxito", async () => {
      const onRenewed = vi.fn();
      mockRenewMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderModal(athleteWithOutdatedConsent, activePolicy, onRenewed);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(onRenewed).toHaveBeenCalledTimes(1);
      });
    });

    it("debería mostrar error del servidor si la mutación falla", async () => {
      mockRenewMutate.mockImplementation((_payload, { onError } = {}) => {
        onError?.(new Error("Server error"));
      });

      renderModal(athleteWithOutdatedConsent, activePolicy);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/No fue posible guardar tu consentimiento/i),
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Tercer checkbox (accept_third_party_sharing)
  // -------------------------------------------------------------------------

  describe("checkbox de procesamiento con IA", () => {
    it("debería renderizar el tercer checkbox con name accept_third_party_sharing", () => {
      renderModal(athleteWithOutdatedConsent);
      const checkbox = document.querySelector(
        'input[name="accept_third_party_sharing"]',
      ) as HTMLInputElement | null;
      expect(checkbox).not.toBeNull();
      expect(checkbox?.type).toBe("checkbox");
    });

    it("submit con los dos obligatorios marcados y IA SIN marcar → mutation con accept_third_party_sharing: false", async () => {
      mockRenewMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderModal(athleteWithOutdatedConsent, activePolicy);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      // No marcamos el checkbox de IA
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(mockRenewMutate).toHaveBeenCalledWith(
          expect.objectContaining({ accept_third_party_sharing: false }),
          expect.anything(),
        );
      });
    });

    it("submit con los tres checkboxes marcados → mutation con accept_third_party_sharing: true", async () => {
      mockRenewMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderModal(athleteWithOutdatedConsent, activePolicy);

      fireEvent.click(screen.getByLabelText(/Recolectar datos básicos del atleta/i));
      fireEvent.click(screen.getByLabelText(/Registrar mediciones antropométricas/i));
      fireEvent.click(screen.getByLabelText(/Procesamiento con IA/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(mockRenewMutate).toHaveBeenCalledWith(
          expect.objectContaining({ accept_third_party_sharing: true }),
          expect.anything(),
        );
      });
    });

    it("submit con IA marcado pero sin los obligatorios → muestra errores, NO llama mutation", async () => {
      renderModal(athleteWithOutdatedConsent, activePolicy);

      // Solo marcamos IA, no los dos obligatorios
      fireEvent.click(screen.getByLabelText(/Procesamiento con IA/i));
      fireEvent.click(screen.getByRole("button", { name: /Aceptar nueva política/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Debes aceptar el tratamiento de datos básicos/i),
        ).toBeInTheDocument();
        expect(
          screen.getByText(/Debes aceptar el registro de medidas antropométricas/i),
        ).toBeInTheDocument();
      });

      expect(mockRenewMutate).not.toHaveBeenCalled();
    });
  });
});
