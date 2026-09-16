/**
 * courseErrors — mapeo código→mensaje para los errores del módulo
 * race-course (feature 043), tabla `specs/043-race-course-profile/contracts/course-api.md`
 * §6. Nunca se muestra al usuario el texto crudo de un error HTTP.
 *
 * `duplicate_recording` y `variant_in_use` traen el detalle (label de la
 * variante / nombres de categorías) ya interpolado por el backend en
 * `detail.message` — para esos dos códigos se usa ese mensaje tal cual (sigue
 * siendo texto en español curado por el backend, ver `course-api.md` §4 y
 * §2). Para el resto de códigos se usa el texto fijo de la tabla del
 * contrato, ignorando cualquier `message` que el backend haya incluido
 * (defensa en profundidad: el texto mostrado siempre pasa por este mapa).
 *
 * Nota: `unknown_category`, `duplicate_category`, `variant_not_found` y
 * `race_event_not_found` no tienen fila explícita en la tabla del contrato
 * (§6 solo cubre los flujos de subida/borrado de variante); los mensajes de
 * abajo para esos cuatro códigos son una elección razonable de este autor,
 * no texto verbatim del contrato — a revisar si §6 se amplía.
 */
import { extractErrorDetail } from "@/lib/apiError";
import type { CourseErrorCode } from "@/types/raceCourse.types";

const STATIC_MESSAGES: Partial<Record<CourseErrorCode, string>> = {
  unsupported_media_type: "El archivo debe ser un GPX.",
  not_gpx: "El archivo no es un GPX válido.",
  compressed_not_allowed:
    "No se aceptan archivos comprimidos; sube el GPX sin comprimir.",
  file_too_large: "El archivo supera los 5 MB permitidos.",
  xml_unsafe: "El archivo contiene estructuras XML no permitidas.",
  malformed: "No pudimos leer el archivo; verifica que sea un GPX completo.",
  no_track_points: "El GPX no contiene puntos de recorrido.",
  no_position: "El GPX no contiene coordenadas válidas.",
  too_short:
    "El recorrido es demasiado corto para ser una vuelta (menos de 300 m).",
  too_long:
    "La vuelta supera los 15 km; indica cuántas vueltas contiene la grabación.",
  too_few_points:
    "La grabación tiene muy pocos puntos para dibujar el circuito.",
  variant_label_taken: "Ya existe una variante con ese nombre en esta válida.",
  variant_not_in_event: "La variante no pertenece a esta válida.",
  // No verbatim en el contrato §6 — ver nota de archivo.
  unknown_category: "La categoría indicada no existe o no está activa.",
  duplicate_category: "Hay una categoría repetida en la tabla de vueltas.",
  variant_not_found: "Esta variante ya no existe.",
  race_event_not_found: "Esta válida ya no existe.",
};

/** Códigos cuyo `detail.message` viene interpolado por el backend con datos
 * que no podemos reconstruir en el cliente (label de variante, nombres de
 * categorías) — se muestra tal cual en vez del texto fijo de la tabla. */
const USES_BACKEND_MESSAGE = new Set<CourseErrorCode>([
  "duplicate_recording",
  "variant_in_use",
]);

const DEFAULT_FALLBACK = "Ocurrió un error. Intenta de nuevo.";

export function getCourseErrorMessage(
  err: unknown,
  fallback: string = DEFAULT_FALLBACK,
): string {
  if (err && typeof err === "object") {
    const detail = (
      err as {
        response?: { data?: { detail?: { code?: string; message?: string } } };
      }
    ).response?.data?.detail;
    const code = detail?.code as CourseErrorCode | undefined;
    if (code) {
      if (USES_BACKEND_MESSAGE.has(code)) {
        if (typeof detail?.message === "string" && detail.message.trim() !== "") {
          return detail.message;
        }
      }
      const staticMsg = STATIC_MESSAGES[code];
      if (staticMsg) return staticMsg;
    }
  }
  // Cold start / errores de red / fallback genérico (mismo helper que el
  // resto de la app usa para esto).
  return extractErrorDetail(err, fallback);
}
