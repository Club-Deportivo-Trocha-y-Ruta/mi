// Clases compartidas de las páginas de autenticación (login, recuperar/restablecer
// contraseña, registro de padre). Centralizadas para que el alto mínimo de 48px de
// touch targets (constitución P-III) se mantenga igual en las 4 páginas sin repetir
// el string en cada una.

export const authInputClass =
  "min-h-12 w-full rounded-lg bg-surface-raised px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

export const authButtonClass =
  "flex min-h-12 w-full items-center justify-center rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-surface transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight";

// Enlace de texto inline (p. ej. "¿Olvidaste tu contraseña?"): mantiene el tamaño de
// letra visual pero da un área táctil >=48px de alto con `inline-flex items-center`.
export const authLinkClass =
  "inline-flex min-h-12 items-center font-medium text-link-blue hover:underline";
