/**
 * Helper para mapear errores Pydantic 422 de FastAPI a react-hook-form.
 *
 * FastAPI emite un payload de validación con shape:
 *   {
 *     detail: [
 *       { loc: ["body", "first_name"], msg: "Field required", type: "missing" },
 *       ...
 *     ]
 *   }
 *
 * `applyPydanticErrors` extrae cada item, descarta el prefijo "body"
 * y registra el error en el field correspondiente con
 * `setError(path, { type: "server", message })`.
 *
 * Devuelve `true` si era un 422 con detail iterable (y se aplicaron los
 * errores), `false` si no — el llamador puede entonces caer en un toast
 * genérico.
 */
import axios from "axios";
import type { Path, UseFormSetError } from "react-hook-form";

import type { PydanticDetailItem } from "@/lib/api/errorMessages";

export function applyPydanticErrors<T extends Record<string, unknown>>(
  err: unknown,
  setError: UseFormSetError<T>,
): boolean {
  if (!axios.isAxiosError(err)) return false;
  if (err.response?.status !== 422) return false;
  const detail = err.response.data?.detail;
  if (!Array.isArray(detail) || detail.length === 0) return false;

  let applied = false;
  for (const raw of detail as PydanticDetailItem[]) {
    if (!raw || !Array.isArray(raw.loc) || typeof raw.msg !== "string") {
      continue;
    }
    // Saltamos el prefijo "body"/"query"/"path" si está presente.
    const loc = raw.loc[0] === "body" || raw.loc[0] === "query" || raw.loc[0] === "path"
      ? raw.loc.slice(1)
      : raw.loc;
    if (loc.length === 0) continue;
    const fieldPath = loc
      .map((segment) =>
        typeof segment === "number" ? `[${segment}]` : segment,
      )
      .join(".")
      .replace(/\.\[/g, "[");
    setError(fieldPath as Path<T>, {
      type: "server",
      message: raw.msg,
    });
    applied = true;
  }
  return applied;
}
