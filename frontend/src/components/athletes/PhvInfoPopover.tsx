/**
 * PhvInfoPopover — popover nativo (sin Radix) que muestra una nota
 * explicativa sobre el marcador PHV/PWV del chart.
 *
 * Mantiene el comportamiento original (click toggle + blur close).
 */
import { useRef, useState } from "react";
import { Info } from "lucide-react";

export interface PhvInfoPopoverProps {
  note: string;
}

export function PhvInfoPopover({ note }: PhvInfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  return (
    <span className="relative inline-flex items-center">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label="Información sobre el marcador de maduración"
        aria-expanded={open}
        className="ml-1 flex h-4 w-4 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus:outline-none focus-visible:ring-2 focus-visible:ring-charcoal"
      >
        <Info size={12} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute left-5 top-0 z-50 w-56 rounded-md bg-white p-2.5 text-[11px] leading-relaxed text-mid-gray shadow-card"
        >
          {note}
        </div>
      )}
    </span>
  );
}
