/**
 * ReferralNoteButton — descarga la nota de remisión PDF (feature 046, US3,
 * T047), mismo patrón de descarga de blob que
 * `components/intervals/InstructivoDownloadButton.tsx`.
 *
 * `BodyCompositionCard` sólo la renderiza cuando `reading.band === "rojo"`
 * (contrato `contracts/body-composition-reading.md` §3/§4 — el rojo nunca
 * llega a una familia, y la nota es exclusivamente para coordinar la
 * remisión con un profesional de salud). El PDF nunca trae cifras ni el
 * nombre del atleta (sólo iniciales) — ver
 * `contracts/skinfolds-api.md` §6.
 *
 * 409 `no_skinfold_data` (el atleta se quedó sin sets entre que se pintó la
 * banda y el clic) se traduce a copy en español, sin exponer el código.
 */
import * as React from "react";
import axios from "axios";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Download, Loader2 } from "lucide-react";

import { downloadReferralNote } from "@/api/bodyComposition";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/download";
import { cn } from "@/lib/utils";

export interface ReferralNoteButtonProps {
  athleteId: number;
  className?: string;
}

function buildFilename(): string {
  const date = new Date().toISOString().slice(0, 10);
  return `nota_remision_${date}.pdf`;
}

function referralNoteErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 409) {
    return "No hay pliegues registrados para generar la nota de remisión.";
  }
  if (axios.isAxiosError(error) && error.response?.status === 403) {
    return "No tienes permiso para generar esta nota.";
  }
  return "No se pudo generar la nota de remisión. Intenta de nuevo.";
}

export function ReferralNoteButton({
  athleteId,
  className,
}: ReferralNoteButtonProps): React.ReactElement {
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const errorId = React.useId();

  const download = useMutation({
    mutationKey: ["body-composition", "referral-note", athleteId],
    mutationFn: () => downloadReferralNote(athleteId),
  });

  const handleDownload = React.useCallback(() => {
    setErrorMessage(null);
    download.mutate(undefined, {
      onSuccess: (blob) => {
        triggerBlobDownload(blob, buildFilename());
      },
      onError: (error) => {
        setErrorMessage(referralNoteErrorMessage(error));
      },
    });
  }, [download]);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleDownload}
        disabled={download.isPending}
        aria-describedby={errorMessage ? errorId : undefined}
      >
        {download.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Download className="h-4 w-4" aria-hidden="true" />
        )}
        {download.isPending ? "Generando…" : "Generar nota de remisión"}
      </Button>

      {errorMessage ? (
        <p id={errorId} role="alert" className="flex items-center gap-1.5 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

export default ReferralNoteButton;
