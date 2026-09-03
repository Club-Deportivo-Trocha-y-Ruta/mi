/**
 * SummitCard — "Cima del mes": el hito destacado del mes, sea un
 * resultado de carrera o un hito de entrenamiento (feature 038, T301).
 *
 * El chip "Cima del mes" usa `--color-trail-earth` como color de TEXTO
 * (nunca como fondo con texto encima) — es una de las dos únicas
 * superficies autorizadas para ese token (ver style.css). El texto es
 * grande y en negrita (>=18px bold) para cumplir el piso AA de texto
 * grande (contraste 4.0:1 sobre blanco, no alcanza el piso de 4.5:1 de
 * texto normal).
 */
import { Mountain, Trophy } from "lucide-react";

import { formatDayMonth } from "@/lib/datetime";
import type { Summit } from "@/types/stageLog.types";

export interface SummitCardProps {
  summit: Summit;
}

export function SummitCard({ summit }: SummitCardProps) {
  const Icon = summit.kind === "race" ? Trophy : Mountain;

  return (
    <div
      className="rounded-xl bg-white p-4 shadow-card"
      data-testid="summit-card"
    >
      <p className="text-lg font-bold text-trail-earth sm:text-xl">
        Cima del mes
      </p>
      <div className="mt-2 flex items-start gap-3">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-light-gray text-charcoal"
          aria-hidden="true"
        >
          <Icon size={18} />
        </span>
        <div className="min-w-0">
          <p className="font-display text-base font-semibold text-charcoal">
            {summit.title}
          </p>
          {summit.detail && (
            <p className="mt-0.5 text-sm text-mid-gray">{summit.detail}</p>
          )}
          {summit.date && (
            <p className="mt-0.5 text-xs text-mid-gray">
              {formatDayMonth(summit.date)}
            </p>
          )}
          {summit.caption && (
            <p className="mt-2 text-sm italic leading-relaxed text-charcoal">
              {summit.caption}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
