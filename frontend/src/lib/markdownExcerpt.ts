/**
 * markdownExcerpt — limpia un fragmento markdown (recortado por el backend,
 * ver `_EXCERPT_LEN` en `routers/club_race_insights.py`) para mostrarlo como
 * texto plano en una card. El recorte puede cortar un marcador a la mitad
 * (ej. `**táctico` sin cierre), así que además del par abierto/cerrado se
 * limpian marcadores sueltos.
 */

const HEADING_LINE = /^#{1,6}\s+/;
const LIST_MARKER = /^\s*(?:[-*+]|\d+\.)\s+/;
const BLOCKQUOTE_MARKER = /^\s*>\s?/;

/** Convierte markdown a texto plano: sin headers, énfasis, código ni links. */
export function toPlainExcerpt(markdown: string): string {
  const lines = markdown
    .split("\n")
    .filter((line) => !HEADING_LINE.test(line.trim()))
    .map((line) => line.replace(LIST_MARKER, "").replace(BLOCKQUOTE_MARKER, ""));

  let text = lines.join(" ");

  // Links [texto](url) → texto.
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  // Énfasis con cierre: **negrita**, __negrita__, *cursiva*, _cursiva_.
  text = text.replace(/(\*\*|__)(.*?)\1/g, "$2");
  text = text.replace(/(\*|_)(.*?)\1/g, "$2");
  // Marcadores sueltos (código en línea, o énfasis sin cierre por el recorte).
  text = text.replace(/[*_`]+/g, "");

  return text.replace(/\s+/g, " ").trim();
}
