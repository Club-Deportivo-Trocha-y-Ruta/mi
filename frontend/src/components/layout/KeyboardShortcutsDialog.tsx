/**
 * KeyboardShortcutsDialog — "Atajos de teclado" help dialog (feature 033,
 * US5, T063).
 *
 * Presentational read-only reference for the bindings `useKeyboardShortcuts`
 * (T062, `frontend/src/hooks/layout/useKeyboardShortcuts.ts`) registers.
 * Built on the shared `ui/dialog.tsx` primitive per `research.md` R8 — no
 * new dependency, no new UI chrome.
 *
 * The area-jump rows are derived from `AREA_ID_BY_SHORTCUT_KEY` (the hook's
 * own key -> NavArea.id map) joined against `NAV_AREAS` labels, so this
 * table can never drift out of sync with the actual bindings — there is a
 * single source of truth for "which key jumps where".
 */
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AREA_ID_BY_SHORTCUT_KEY } from "@/hooks/layout/useKeyboardShortcuts";
import { NAV_AREAS } from "@/lib/navigation";

export interface KeyboardShortcutsDialogProps {
  /** Controls visibility — the parent (`UserMenu`) owns open/close state. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ShortcutRow {
  /** Keys pressed in sequence, e.g. `["g", "i"]` for a chord. */
  keys: string[];
  description: string;
}

const AREA_SHORTCUT_ROWS: ShortcutRow[] = Object.entries(
  AREA_ID_BY_SHORTCUT_KEY,
).map(([key, areaId]) => {
  const area = NAV_AREAS.find((candidate) => candidate.id === areaId);
  return {
    keys: ["g", key],
    description: `Ir a ${area?.label ?? areaId}`,
  };
});

const OTHER_SHORTCUT_ROWS: ShortcutRow[] = [
  { keys: ["n"], description: "Crear nuevo (sesión, competencia, evento o atleta)" },
  { keys: ["?"], description: "Mostrar esta ayuda de atajos" },
];

const SHORTCUT_ROWS: ShortcutRow[] = [...AREA_SHORTCUT_ROWS, ...OTHER_SHORTCUT_ROWS];

export function KeyboardShortcutsDialog({
  open,
  onOpenChange,
}: KeyboardShortcutsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="w-full max-w-md"
        aria-label="Atajos de teclado"
        data-testid="keyboard-shortcuts-dialog"
      >
        <DialogHeader>
          <DialogTitle>Atajos de teclado</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <p className="mb-3 text-sm text-mid-gray">
            Se desactivan mientras escribís en un campo o hay un diálogo
            abierto.
          </p>
          <table className="w-full border-collapse text-sm">
            <tbody>
              {SHORTCUT_ROWS.map((row) => (
                <tr
                  key={row.description}
                  className="border-b border-border-gray last:border-0"
                >
                  <td className="w-28 py-2 pr-4 align-top">
                    <span className="inline-flex flex-wrap items-center gap-1">
                      {row.keys.map((key, index) => (
                        <span key={key} className="inline-flex items-center gap-1">
                          {index > 0 && (
                            <span className="text-xs text-mid-gray">luego</span>
                          )}
                          <kbd className="rounded border border-border-gray bg-light-gray px-1.5 py-0.5 font-mono text-xs text-charcoal">
                            {key}
                          </kbd>
                        </span>
                      ))}
                    </span>
                  </td>
                  <td className="py-2 text-charcoal">{row.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default KeyboardShortcutsDialog;
