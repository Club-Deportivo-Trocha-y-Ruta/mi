/**
 * Tests de RevokeConsentDialog.
 *
 * Cubre:
 *   - Renderizado de nombre del atleta y advertencia
 *   - Llamada a useWithdrawConsent con athlete_id correcto
 *   - reason opcional: se envía cuando se ingresa, se omite cuando está vacío
 *   - Callback onClose al cancelar
 *   - Callback onSuccess tras revocar exitosamente
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

const mockWithdrawMutate = vi.fn();
const mockWithdrawState = { isPending: false };

vi.mock("@/hooks/consent", () => ({
  useWithdrawConsent: () => ({
    mutate: mockWithdrawMutate,
    isPending: mockWithdrawState.isPending,
  }),
  useRenewConsent: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

import { RevokeConsentDialog } from "./RevokeConsentDialog";
import type { AthleteConsentStatus } from "@/types/consent";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const athlete: AthleteConsentStatus = {
  athlete_id: 5,
  athlete_name: "Juan Pérez",
  current_consent: {
    id: 12,
    policy_version: "v1.1",
    consented_at: "2026-05-01T10:00:00Z",
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

function renderDialog(
  overrides: {
    onClose?: () => void;
    onSuccess?: () => void;
  } = {},
) {
  const onClose = overrides.onClose ?? vi.fn();
  const onSuccess = overrides.onSuccess ?? vi.fn();

  const result = render(
    <RevokeConsentDialog
      athlete={athlete}
      onClose={onClose}
      onSuccess={onSuccess}
    />,
    { wrapper: makeWrapper() },
  );

  return { ...result, onClose, onSuccess };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RevokeConsentDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWithdrawState.isPending = false;
  });

  // -------------------------------------------------------------------------
  // Renderizado
  // -------------------------------------------------------------------------

  describe("renderizado", () => {
    it("debería mostrar el nombre del atleta en el encabezado", () => {
      renderDialog();
      // El nombre aparece en el subtítulo del header (p.text-mid-gray) y en la advertencia (strong)
      const allMatches = screen.getAllByText("Juan Pérez");
      expect(allMatches.length).toBeGreaterThanOrEqual(1);
    });

    it("debería mostrar la advertencia de consecuencias con el nombre del atleta", () => {
      renderDialog();
      expect(
        screen.getByText(/Estás a punto de revocar tu consentimiento para/i),
      ).toBeInTheDocument();
      // Buscamos el nombre del atleta dentro de la advertencia
      const warning = screen.getByRole("note");
      expect(warning).toHaveTextContent("Juan Pérez");
    });

    it("debería mostrar el textarea de motivo opcional", () => {
      renderDialog();
      expect(
        screen.getByLabelText(/Motivo/i),
      ).toBeInTheDocument();
    });

    it("debería tener role=alertdialog con aria-modal=true", () => {
      renderDialog();
      const dialog = screen.getByRole("alertdialog");
      expect(dialog).toHaveAttribute("aria-modal", "true");
    });
  });

  // -------------------------------------------------------------------------
  // Cancelar
  // -------------------------------------------------------------------------

  describe("cancelar", () => {
    it("debería llamar onClose al hacer clic en Cancelar", () => {
      const { onClose } = renderDialog();

      // Hay dos botones que contienen "Cancelar": el texto del footer y el aria-label del X.
      // Usamos el botón de texto exacto "Cancelar" del footer.
      const cancelBtn = screen.getByRole("button", { name: "Cancelar" });
      fireEvent.click(cancelBtn);

      expect(onClose).toHaveBeenCalledTimes(1);
      expect(mockWithdrawMutate).not.toHaveBeenCalled();
    });

    it("debería llamar onClose al hacer clic en el botón X", () => {
      const { onClose } = renderDialog();

      fireEvent.click(screen.getByRole("button", { name: /Cancelar revocación/i }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Mutación de revocación
  // -------------------------------------------------------------------------

  describe("mutación de revocación", () => {
    it("debería llamar useWithdrawConsent con athlete_id correcto y sin reason cuando textarea está vacío", async () => {
      mockWithdrawMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderDialog();

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar consentimiento/i }),
      );

      await waitFor(() => {
        expect(mockWithdrawMutate).toHaveBeenCalledWith(
          { athlete_id: 5, reason: undefined },
          expect.objectContaining({ onSuccess: expect.any(Function) }),
        );
      });
    });

    it("debería incluir reason cuando el padre ingresa un motivo", async () => {
      mockWithdrawMutate.mockImplementation((_payload, { onSuccess } = {}) => {
        onSuccess?.({});
      });

      renderDialog();

      const textarea = screen.getByLabelText(/Motivo/i);
      fireEvent.change(textarea, {
        target: { value: "El atleta se retiró del club." },
      });

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar consentimiento/i }),
      );

      await waitFor(() => {
        expect(mockWithdrawMutate).toHaveBeenCalledWith(
          { athlete_id: 5, reason: "El atleta se retiró del club." },
          expect.objectContaining({ onSuccess: expect.any(Function) }),
        );
      });
    });

    it("debería llamar onSuccess y onClose tras revocar exitosamente", async () => {
      const onClose = vi.fn();
      const onSuccess = vi.fn();

      mockWithdrawMutate.mockImplementation((_payload, { onSuccess: s } = {}) => {
        s?.({});
      });

      render(
        <RevokeConsentDialog
          athlete={athlete}
          onClose={onClose}
          onSuccess={onSuccess}
        />,
        { wrapper: makeWrapper() },
      );

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar consentimiento/i }),
      );

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
      });
    });

    it("debería mostrar error del servidor cuando la mutación falla", async () => {
      mockWithdrawMutate.mockImplementation((_payload, { onError } = {}) => {
        onError?.(new Error("Network error"));
      });

      renderDialog();

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar consentimiento/i }),
      );

      await waitFor(() => {
        expect(
          screen.getByText(/No fue posible revocar el consentimiento/i),
        ).toBeInTheDocument();
      });
    });

    it("debería NO llamar onClose si la mutación falla", async () => {
      const { onClose } = renderDialog();

      mockWithdrawMutate.mockImplementation((_payload, { onError } = {}) => {
        onError?.(new Error("Network error"));
      });

      fireEvent.click(
        screen.getByRole("button", { name: /Revocar consentimiento/i }),
      );

      await waitFor(() => {
        expect(
          screen.getByText(/No fue posible revocar el consentimiento/i),
        ).toBeInTheDocument();
      });

      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
