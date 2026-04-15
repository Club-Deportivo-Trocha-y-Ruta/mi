import { CheckCircle2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Shared style constants (mirror LoginPage / ParentRegisterPage)
// ---------------------------------------------------------------------------

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface OnboardingSuccessProps {
  userName?: string;
  onGoToLogin: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OnboardingSuccess({ userName, onGoToLogin }: OnboardingSuccessProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="w-full max-w-md rounded-xl bg-white p-8 text-center"
        style={{ boxShadow: CARD_SHADOW }}
      >
        {/* Club header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Club Deportivo
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
          >
            Trocha y Ruta
          </h1>
        </div>

        {/* Success icon — animado al aparecer */}
        <div className="mb-6 flex justify-center">
          <div className="animate-bounce">
            <CheckCircle2
              className="text-green-500"
              size={56}
              strokeWidth={1.5}
            />
          </div>
        </div>

        {/* Mensaje principal */}
        <h2
          className="text-xl text-charcoal"
          style={{
            fontFamily: "'Cal Sans', system-ui, sans-serif",
            fontWeight: 600,
            letterSpacing: "0.2px",
          }}
        >
          ¡Cuenta creada exitosamente!
        </h2>

        <p className="mt-3 text-sm text-mid-gray">
          {userName ? (
            <>
              Bienvenido/a,{" "}
              <span className="font-medium text-charcoal">{userName}</span>.{" "}
            </>
          ) : null}
          Ya puedes seguir el progreso deportivo de tu hijo/a.
        </p>

        {/* CTA */}
        <button
          type="button"
          onClick={onGoToLogin}
          className="mt-8 w-full rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
        >
          Iniciar sesión
        </button>
      </div>
    </div>
  );
}
