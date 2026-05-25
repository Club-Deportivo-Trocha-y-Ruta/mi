/**
 * Helpers compartidos para extraer mensajes legibles de errores axios.
 *
 * Consolida `getErrMsg` (ImportWizard) y `getCompetitorErrorMessage`
 * (useUnlinkedCompetitors) en un único módulo. Cada helper conserva su
 * mapeo de status codes específico, pero comparten la lógica de parseo
 * de `detail` (string | Pydantic array).
 */
export interface PydanticDetailItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/**
 * Type-guard estructural: acepta cualquier error con shape `response.data`
 * compatible — tanto AxiosError reales como plain-objects de tests
 * pueden pasar por aquí.
 */
function isErrorLike(
  err: unknown,
): err is { response?: { data?: { detail?: unknown }; status?: number }; message?: string } {
  return typeof err === "object" && err !== null;
}

/**
 * Extrae `detail` del payload del error si es un string. Soporta:
 *  - `detail: "msg"` → "msg"
 *  - `detail: [{msg: "..."}]` → "msg" del primer item
 *  - otros casos → null
 */
export function getDetailString(err: unknown): string | null {
  if (!isErrorLike(err)) return null;
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return first.msg;
  }
  return null;
}

/**
 * Mensaje genérico para errores axios — fallback con copy en español.
 * Útil cuando no hay un mapeo de status code específico.
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  const detail = getDetailString(err);
  if (detail) return detail;
  if (isErrorLike(err) && err.message && !/status code \d+/i.test(err.message)) {
    return err.message;
  }
  return fallback;
}

/**
 * Mensaje específico para uploads/imports (mapea 413).
 * Migrado desde ImportWizard.tsx::getErrMsg.
 *
 * Prioriza `detail` del payload (string o Pydantic array) sobre el mapeo
 * 413 estándar — los tests confían en que un `detail: "Demasiado grande"`
 * gana al copy genérico.
 */
export function getImportErrorMessage(err: unknown, fallback: string): string {
  const detail = getDetailString(err);
  if (detail) return detail;
  if (isErrorLike(err) && err.response?.status === 413) {
    return "El archivo excede el tamaño permitido (máx 8 MB).";
  }
  return getApiErrorMessage(err, fallback);
}

/**
 * Mensaje específico para vinculación de competidores (mapea 403/404/409/422).
 * Migrado desde useUnlinkedCompetitors.ts::getCompetitorErrorMessage.
 */
export function getCompetitorErrorMessage(
  err: unknown,
  fallback = "Error inesperado. Intenta de nuevo.",
): string {
  if (isErrorLike(err)) {
    const status = err.response?.status;
    if (status === 409) {
      return "Este competidor ya está enlazado a otro atleta. Desvincúlalo primero.";
    }
    if (status === 403) {
      return "Sin permiso: el atleta no pertenece a tu club.";
    }
    if (status === 404) {
      return "Competidor o atleta no encontrado.";
    }
    if (status === 422) {
      return "Datos inválidos. Verifica el atleta seleccionado.";
    }
  }
  return getApiErrorMessage(err, fallback);
}
