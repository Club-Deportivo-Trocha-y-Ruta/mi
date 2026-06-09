/**
 * ConfirmEmailChangePage — página pública para confirmar un cambio de correo.
 *
 * Flujo:
 *  1. Lee el token del query string (?token=...).
 *  2. Llama al endpoint POST /api/profile/change-email/confirm en el mount.
 *  3. Muestra estado: checking → success | not-found (404) | expired (410) | conflict (409) | error.
 *
 * Esta página es PÚBLICA (sin autenticación requerida). El token es el secreto.
 * Diseño idéntico al de ResetPasswordPage (misma estructura de estados).
 *
 * Path: /confirmar-correo
 */

import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isAxiosError } from "axios";

import { confirmEmailChange } from "@/api/profile";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

type Status = "checking" | "success" | "not-found" | "expired" | "conflict" | "error";

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function ConfirmEmailChangePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let active = true;

    if (!token) {
      setStatus("not-found");
      return;
    }

    confirmEmailChange({ token })
      .then(() => {
        if (active) setStatus("success");
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (isAxiosError(error)) {
          const httpStatus = error.response?.status;
          if (httpStatus === 404) {
            setStatus("not-found");
          } else if (httpStatus === 410) {
            setStatus("expired");
          } else if (httpStatus === 409) {
            setStatus("conflict");
          } else {
            setStatus("error");
          }
        } else {
          setStatus("error");
        }
      });

    return () => {
      active = false;
    };
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="w-full max-w-md rounded-xl bg-white p-8"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
      >
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Confirmar cambio
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
          >
            Actualizar correo
          </h1>
        </div>

        {/* Checking */}
        {status === "checking" && (
          <p className="text-center text-sm text-mid-gray" role="status">
            Verificando enlace...
          </p>
        )}

        {/* Success */}
        {status === "success" && (
          <div>
            <p
              className="rounded-lg bg-green-50 px-3 py-3 text-sm text-green-800"
              role="status"
            >
              Tu correo fue actualizado. Inicia sesión con tu nueva dirección.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Ir a iniciar sesión
              </Link>
            </div>
          </div>
        )}

        {/* Not found */}
        {status === "not-found" && (
          <div>
            <p
              className="rounded-lg bg-amber-50 px-3 py-3 text-sm text-amber-800"
              role="alert"
            >
              Enlace no válido. Verifica que hayas copiado el enlace completo
              del correo.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/perfil"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Volver a mi perfil
              </Link>
            </div>
          </div>
        )}

        {/* Expired / already used */}
        {status === "expired" && (
          <div>
            <p
              className="rounded-lg bg-amber-50 px-3 py-3 text-sm text-amber-800"
              role="alert"
            >
              El enlace ha expirado o ya fue utilizado. Solicita el cambio
              nuevamente desde tu perfil.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/perfil"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Solicitar nuevamente
              </Link>
            </div>
          </div>
        )}

        {/* Conflict: target email taken between request and confirm */}
        {status === "conflict" && (
          <div>
            <p
              className="rounded-lg bg-amber-50 px-3 py-3 text-sm text-amber-800"
              role="alert"
            >
              No se pudo aplicar el cambio. Solicita el cambio nuevamente desde
              tu perfil.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/perfil"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Volver a mi perfil
              </Link>
            </div>
          </div>
        )}

        {/* Generic error */}
        {status === "error" && (
          <div>
            <p
              className="rounded-lg bg-red-50 px-3 py-3 text-sm text-red-700"
              role="alert"
            >
              No fue posible procesar la solicitud. Intenta de nuevo en unos
              minutos.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/perfil"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Volver a mi perfil
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
