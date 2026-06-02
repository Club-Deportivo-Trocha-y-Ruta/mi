/**
 * Dispara la descarga de un Blob en el navegador como un archivo con nombre.
 *
 * Crea un object URL temporal, lo asocia a un ancla invisible, simula el clic
 * y libera el URL. Usado por las descargas de PDF (reportes mensuales, boletines).
 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
