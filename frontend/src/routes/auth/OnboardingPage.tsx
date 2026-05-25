import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { XCircle, Clock } from "lucide-react";

import { useValidateToken } from "@/hooks/onboarding";
import { useOnboardingStore } from "@/store/onboarding.store";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { OnboardingSuccess } from "@/components/onboarding/OnboardingSuccess";

// ---------------------------------------------------------------------------
// Shared style constants (mirror LoginPage / ParentRegisterPage)
// ---------------------------------------------------------------------------

/* shadow-card utility */
// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PageState = "loading" | "invalid" | "expired" | "wizard" | "success";

// Role type aceptado por OnboardingWizard — atletas no tienen flujo de onboarding
type OnboardingRole = "parent" | "coach";

// ---------------------------------------------------------------------------
// AuthCard — wrapper de branding reutilizable para los estados de error
// ---------------------------------------------------------------------------

function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="w-full max-w-md rounded-xl bg-white p-8"
      >
        {/* Club header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Club Deportivo
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal font-heading tracking-[0.2px]"
          >
            Trocha y Ruta
          </h1>
        </div>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function OnboardingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  // Empezamos en "invalid" si no hay token, "loading" si lo hay
  const [pageState, setPageState] = useState<PageState>(
    token ? "loading" : "invalid",
  );
  const [successName, setSuccessName] = useState<string>("");

  const setTokenData = useOnboardingStore((s) => s.setTokenData);
  const reset = useOnboardingStore((s) => s.reset);

  // -------------------------------------------------------------------------
  // Validación del token via TanStack Query
  // La query no corre si `token` es null (enabled: !!token en el hook)
  // -------------------------------------------------------------------------

  const { data, isError, error, isSuccess } = useValidateToken(token);

  // -------------------------------------------------------------------------
  // Efecto: transicionar pageState cuando la query resuelve
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (isSuccess && data) {
      if (data.valid) {
        // Guardar datos del token en el store para el wizard
        setTokenData({
          role: data.role as string,
          token: token!,
          email: data.email,
          athleteName: data.athlete_name,
          clubName: data.club_name ?? "",
          prefill: {
            parentUserId: data.parent_user_id ?? null,
            firstName: data.first_name ?? null,
            lastName: data.last_name ?? null,
            phone: data.phone ?? null,
            relationshipType: data.relationship_type ?? null,
          },
        });
        setPageState("wizard");
      } else {
        // valid === false sin error HTTP — token inválido/cancelado
        setPageState("invalid");
      }
    }
  }, [isSuccess, data, token, setTokenData]);

  useEffect(() => {
    if (isError) {
      // Discriminamos entre token expirado/usado y token inexistente
      const isExpired =
        error && "code" in error && error.code === "TOKEN_EXPIRED";
      setPageState(isExpired ? "expired" : "invalid");
    }
  }, [isError, error]);

  // -------------------------------------------------------------------------
  // Estado: success (controlado localmente, ignoramos la query)
  // -------------------------------------------------------------------------

  if (pageState === "success") {
    return (
      <OnboardingSuccess
        userName={successName}
        onGoToLogin={() => {
          reset();
          navigate("/login", { replace: true });
        }}
      />
    );
  }

  // -------------------------------------------------------------------------
  // Estado: loading
  // -------------------------------------------------------------------------

  if (pageState === "loading") {
    return (
      <AuthCard>
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <div
            className="h-10 w-10 animate-spin rounded-full border-4 border-surface border-t-charcoal"
            role="status"
            aria-label="Verificando invitación"
          />
          <p className="text-sm text-mid-gray">Verificando invitación...</p>
        </div>
      </AuthCard>
    );
  }

  // -------------------------------------------------------------------------
  // Estado: expired (token vencido o ya utilizado)
  // -------------------------------------------------------------------------

  if (pageState === "expired") {
    return (
      <AuthCard>
        <div className="flex flex-col items-center gap-4 text-center">
          <Clock className="text-amber-500" size={48} strokeWidth={1.5} />
          <div>
            <p className="text-base font-semibold text-charcoal">
              Enlace expirado
            </p>
            <p className="mt-2 text-sm text-mid-gray">
              Este enlace de invitación ya fue utilizado o ha vencido.
            </p>
            <p className="mt-1 text-sm text-mid-gray">
              Solicita al entrenador que genere un nuevo enlace.
            </p>
          </div>
        </div>
      </AuthCard>
    );
  }

  // -------------------------------------------------------------------------
  // Estado: invalid (token inexistente, malformado o cancelado)
  // Incluye el caso en que no llegó ningún token en la URL
  // -------------------------------------------------------------------------

  if (pageState === "invalid") {
    return (
      <AuthCard>
        <div className="flex flex-col items-center gap-4 text-center">
          <XCircle className="text-red-500" size={48} strokeWidth={1.5} />
          <div>
            <p className="text-base font-semibold text-charcoal">
              Enlace inválido
            </p>
            <p className="mt-2 text-sm text-mid-gray">
              Este enlace de invitación no existe o ha sido cancelado.
            </p>
            <p className="mt-1 text-sm text-mid-gray">
              Si crees que esto es un error, contacta a tu entrenador.
            </p>
          </div>
        </div>
      </AuthCard>
    );
  }

  // -------------------------------------------------------------------------
  // Estado: wizard (data.valid === true, store actualizado)
  // -------------------------------------------------------------------------

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <OnboardingWizard
        role={data!.role as OnboardingRole}
        tokenData={{
          token: token!,
          email: data!.email,
          athleteName: data!.athlete_name,
          clubName: data!.club_name,
        }}
        onSuccess={(name: string) => {
          setSuccessName(name);
          setPageState("success");
        }}
      />
    </div>
  );
}
