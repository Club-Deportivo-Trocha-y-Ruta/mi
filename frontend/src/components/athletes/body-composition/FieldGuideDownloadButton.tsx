/**
 * FieldGuideDownloadButton — descarga el instructivo estático de toma de
 * pliegues cutáneos (feature 046, US5, T058), mismo patrón de descarga de
 * blob que `components/intervals/InstructivoDownloadButton.tsx`.
 *
 * `GET /api/body-composition/field-guide.pdf` no depende de ningún atleta
 * (coach/admin únicamente, sin datos de ningún deportista — spec US5), así
 * que este botón no toma props. Se usa dos veces: en el encabezado de
 * `BodyCompositionCard.tsx` y en el paso de pre-chequeo del asistente de
 * captura (`SkinfoldPrecheckStep.tsx`).
 */
import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";

import { downloadFieldGuide } from "@/api/bodyComposition";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/download";
import { cn } from "@/lib/utils";

export interface FieldGuideDownloadButtonProps {
  className?: string;
}

const FILENAME = "instructivo_pliegues_cutaneos.pdf";

export function FieldGuideDownloadButton({
  className,
}: FieldGuideDownloadButtonProps): React.ReactElement {
  const download = useMutation({
    mutationKey: ["body-composition", "field-guide"],
    mutationFn: downloadFieldGuide,
  });

  const handleDownload = React.useCallback(() => {
    download.mutate(undefined, {
      onSuccess: (blob) => {
        triggerBlobDownload(blob, FILENAME);
      },
    });
  }, [download]);

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={handleDownload}
      disabled={download.isPending}
      className={cn(className)}
    >
      {download.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : (
        <Download className="h-4 w-4" aria-hidden="true" />
      )}
      {download.isPending ? "Generando…" : "Instructivo"}
    </Button>
  );
}

export default FieldGuideDownloadButton;
