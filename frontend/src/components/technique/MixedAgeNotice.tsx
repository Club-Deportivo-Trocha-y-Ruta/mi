/**
 * MixedAgeNotice — aviso visible (ámbar) cuando la sesión mezcla franjas
 * de edad distintas (mixes_age_bands = true, FR-014).
 *
 * Diseño: banner ámbar no bloqueante. El entrenador ya guardó la sesión;
 * el aviso solo recuerda adaptar las instrucciones a cada franja presente.
 *
 * WCAG: role="alert" para que lectores de pantalla lo anuncien de inmediato;
 * contraste > 4.5:1 sobre amber-50.
 */

interface MixedAgeNoticeProps {
  /** Cuando false/undefined el componente no renderiza nada. */
  mixes_age_bands?: boolean;
}

export function MixedAgeNotice({ mixes_age_bands }: MixedAgeNoticeProps) {
  if (!mixes_age_bands) return null;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4"
    >
      {/* Icono decorativo */}
      <span
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-amber-500"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </span>

      <div>
        <p className="text-sm font-semibold text-amber-900">
          Sesión con franjas de edad mixtas
        </p>
        <p className="mt-0.5 text-sm text-amber-800">
          Esta sesión incluye ejercicios diseñados para diferentes franjas de
          edad. Recuerda adaptar las instrucciones, el nivel de exigencia y los
          tiempos de trabajo para cada grupo de deportistas.
        </p>
      </div>
    </div>
  );
}

export default MixedAgeNotice;
