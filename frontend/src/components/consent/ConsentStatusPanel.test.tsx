/**
 * Tests de ConsentStatusPanel.
 *
 * Cubre:
 *   - Renderizado del estado de consentimiento por atleta
 *   - Fila de estado IA: badge "IA: activa" / texto "IA: no autorizada"
 *   - Botones "Activar IA" / "Revocar IA" y su llamada a useRenewConsent
 *   - Preservación de grants existentes al activar/revocar IA
 *   - Accesibilidad (jest-axe): 0 violaciones
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mock de hooks de consentimiento
// ---------------------------------------------------------------------------

const mockRenewMutate = vi.fn();
const mockRenewState = { isPending: false, isError: false };

vi.mock("@/hooks/consent", () => ({
  useRenewConsent: () => ({
    mutate: mockRenewMutate,
    isPending: mockRenewState.isPending,
    isError: mockRenewState.isError,
  }),
  useWithdrawConsent: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

// Mock de sonner para espiar las llamadas a toast.success sin renderizar toasts reales
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock de sub-componentes que abren modales sobre el panel (evitan renders complejos).
// Cada uno expone un botón que invoca su callback de éxito, para poder probar que
// ConsentStatusPanel dispara el toast en el punto correcto.
vi.mock("./ConsentRenewalModal", () => ({
  ConsentRenewalModal: ({ onRenewed }: { onRenewed: () => void }) => (
    <button type="button" onClick={onRenewed}>
      mock-renewal-success
    </button>
  ),
}));

vi.mock("./RevokeConsentDialog", () => ({
  RevokeConsentDialog: ({ onSuccess }: { onSuccess?: () => void }) => (
    <button type="button" onClick={() => onSuccess?.()}>
      mock-revoke-success
    </button>
  ),
}));

import { toast } from "sonner";
import { ConsentStatusPanel, consentStatus, aiConsentStatus } from "./ConsentStatusPanel";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const activePolicy: PrivacyPolicySummary = {
  id: 2,
  version: "v1.2",
  effective_date: "2026-05-15",
  title: "Política de Tratamiento de Datos Personales",
  changelog: null,
};

const athleteAiActive: AthleteConsentStatus = {
  athlete_id: 1,
  athlete_name: "Carlos López",
  current_consent: {
    id: 10,
    policy_version: "v1.2",
    consented_at: "2026-05-15T09:00:00Z",
    is_current_policy: true,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: false,
      third_party_sharing: true,
    },
  },
};

const athleteAiInactive: AthleteConsentStatus = {
  athlete_id: 2,
  athlete_name: "Ana Martínez",
  current_consent: {
    id: 11,
    policy_version: "v1.2",
    consented_at: "2026-05-15T09:00:00Z",
    is_current_policy: true,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: false,
      third_party_sharing: false,
    },
  },
};

const athleteRevoked: AthleteConsentStatus = {
  athlete_id: 3,
  athlete_name: "Pedro Gómez",
  current_consent: {
    id: 12,
    policy_version: "v1.2",
    consented_at: "2026-05-10T09:00:00Z",
    is_current_policy: true,
    withdrawn_at: "2026-05-14T10:00:00Z",
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: false,
      third_party_sharing: false,
    },
  },
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

function renderPanel(
  consentsPerAthlete: AthleteConsentStatus[],
  policy: PrivacyPolicySummary = activePolicy,
) {
  return render(
    <ConsentStatusPanel
      consentsPerAthlete={consentsPerAthlete}
      activePolicy={policy}
    />,
    { wrapper: makeWrapper() },
  );
}

/** Expande el panel (hace click en el toggle) y retorna el container. */
async function renderAndExpand(
  consentsPerAthlete: AthleteConsentStatus[],
  policy?: PrivacyPolicySummary,
) {
  const result = renderPanel(consentsPerAthlete, policy);
  fireEvent.click(screen.getByRole("button", { name: /Gestionar consentimiento/i }));
  return result;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConsentStatusPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRenewState.isPending = false;
    mockRenewState.isError = false;
  });

  // -------------------------------------------------------------------------
  // Estado IA activa
  // -------------------------------------------------------------------------

  describe("consentimiento con third_party_sharing=true", () => {
    it("debería mostrar el badge 'IA: activa' cuando third_party_sharing es true", async () => {
      await renderAndExpand([athleteAiActive]);

      expect(screen.getByText(/IA: activa/i)).toBeInTheDocument();
    });

    it("debería mostrar el botón 'Revocar IA' cuando third_party_sharing es true", async () => {
      await renderAndExpand([athleteAiActive]);

      expect(
        screen.getByRole("button", { name: /Revocar autorización de IA para Carlos López/i }),
      ).toBeInTheDocument();
    });

    it("click 'Revocar IA' llama renew con accept_third_party_sharing: false preservando grants", async () => {
      mockRenewMutate.mockImplementation(() => {});

      await renderAndExpand([athleteAiActive]);

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar autorización de IA para Carlos López/i }),
      );

      await waitFor(() => {
        expect(mockRenewMutate).toHaveBeenCalledWith({
          athlete_id: 1,
          policy_version: "v1.2",
          accept_data_collection: true,
          accept_anthropometry: true,
          accept_third_party_sharing: false,
        });
      });
    });
  });

  // -------------------------------------------------------------------------
  // Estado IA inactiva
  // -------------------------------------------------------------------------

  describe("consentimiento con third_party_sharing=false", () => {
    it("debería mostrar 'IA: no autorizada' cuando third_party_sharing es false", async () => {
      await renderAndExpand([athleteAiInactive]);

      expect(screen.getByText(/IA: no autorizada/i)).toBeInTheDocument();
    });

    it("debería mostrar el botón 'Activar IA' cuando third_party_sharing es false", async () => {
      await renderAndExpand([athleteAiInactive]);

      expect(
        screen.getByRole("button", { name: /Activar autorización de IA para Ana Martínez/i }),
      ).toBeInTheDocument();
    });

    it("click 'Activar IA' llama renew con accept_third_party_sharing: true preservando grants", async () => {
      mockRenewMutate.mockImplementation(() => {});

      await renderAndExpand([athleteAiInactive]);

      fireEvent.click(
        screen.getByRole("button", { name: /Activar autorización de IA para Ana Martínez/i }),
      );

      await waitFor(() => {
        expect(mockRenewMutate).toHaveBeenCalledWith({
          athlete_id: 2,
          policy_version: "v1.2",
          accept_data_collection: true,
          accept_anthropometry: true,
          accept_third_party_sharing: true,
        });
      });
    });
  });

  // -------------------------------------------------------------------------
  // Consentimiento revocado: NO muestra fila IA
  // -------------------------------------------------------------------------

  describe("consentimiento revocado", () => {
    it("NO debería mostrar fila de IA cuando el consentimiento está revocado", async () => {
      await renderAndExpand([athleteRevoked]);

      expect(screen.queryByText(/IA: activa/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/IA: no autorizada/i)).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Toast de éxito (sonner) — migrado desde el banner hand-rolled
  // -------------------------------------------------------------------------

  describe("toast de éxito (sonner)", () => {
    it("llama a toast.success al completar la renovación desde el panel manual", async () => {
      await renderAndExpand([athleteRevoked]);

      fireEvent.click(screen.getByRole("button", { name: "Dar consentimiento" }));
      fireEvent.click(screen.getByRole("button", { name: "mock-renewal-success" }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          "Consentimiento actualizado correctamente.",
        );
      });
      // El banner hand-rolled ya no existe: no debe quedar ningún nodo con role="status".
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("llama a toast.success al completar la revocación desde el panel manual", async () => {
      await renderAndExpand([athleteAiInactive]);

      fireEvent.click(screen.getByRole("button", { name: "Revocar" }));
      fireEvent.click(screen.getByRole("button", { name: "mock-revoke-success" }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          "Consentimiento revocado correctamente.",
        );
      });
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad
  // -------------------------------------------------------------------------

  describe("accesibilidad", () => {
    it("debe pasar jest-axe con 0 violaciones (panel expandido, IA activa e inactiva)", async () => {
      const { container } = await renderAndExpand([athleteAiActive, athleteAiInactive]);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Adaptadores puros (T012)
  // -------------------------------------------------------------------------

  describe("consentStatus (adaptador puro)", () => {
    it("mapea 'never' a neutral/'Sin consentimiento'", () => {
      expect(consentStatus("never")).toEqual({ status: "neutral", label: "Sin consentimiento" });
    });

    it("mapea 'outdated' a warning/'Desactualizado'", () => {
      expect(consentStatus("outdated")).toEqual({ status: "warning", label: "Desactualizado" });
    });

    it("mapea 'revoked' a danger/'Revocado'", () => {
      expect(consentStatus("revoked")).toEqual({ status: "danger", label: "Revocado" });
    });

    it("mapea 'current' a success/'Vigente'", () => {
      expect(consentStatus("current")).toEqual({ status: "success", label: "Vigente" });
    });
  });

  describe("aiConsentStatus (adaptador puro)", () => {
    it("mapea isActive=true a success/'IA: activa'", () => {
      expect(aiConsentStatus(true)).toEqual({ status: "success", label: "IA: activa" });
    });

    it("mapea isActive=false a neutral/'IA: no autorizada'", () => {
      expect(aiConsentStatus(false)).toEqual({ status: "neutral", label: "IA: no autorizada" });
    });
  });

  // -------------------------------------------------------------------------
  // Regresión: STATE_CONFIG hand-rolled reemplazado por StatusBadge (T021)
  // -------------------------------------------------------------------------

  describe("regresión — migración a StatusBadge", () => {
    it("el badge de estado de consentimiento y la fila IA usan StatusBadge (ícono presente, sin clases hand-rolled)", async () => {
      const { container } = await renderAndExpand([athleteAiActive, athleteAiInactive]);

      // StatusBadge siempre renderiza un ícono junto al label. Ambos atletas
      // están "current" ("Vigente" aparece dos veces).
      const vigenteBadges = screen.getAllByText("Vigente");
      expect(vigenteBadges.length).toBeGreaterThan(0);
      for (const el of vigenteBadges) {
        expect(el.closest("span")?.querySelector("svg")).toBeInTheDocument();
      }
      expect(screen.getByText("IA: activa").closest("span")?.querySelector("svg")).toBeInTheDocument();
      expect(screen.getByText("IA: no autorizada").closest("span")?.querySelector("svg")).toBeInTheDocument();

      // Las clases utility hand-rolled de STATE_CONFIG legado ya no aparecen
      // (distintas de otras clases legítimas no relacionadas con el badge,
      // como "text-red-600" del botón Revocar o "text-amber-600" de la nota
      // de política desactualizada).
      const legacyClassPattern = /bg-green-50|text-green-700|bg-amber-50|text-amber-700|bg-red-50|text-red-700/;
      expect(container.innerHTML).not.toMatch(legacyClassPattern);
    });
  });
});
