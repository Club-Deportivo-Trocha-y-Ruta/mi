# Contract — Shared Component Kit (consumed by features 029–033)

UI contracts for the shared components introduced by 028. These interfaces are the **stable API the rest of the redesign program builds against** — later features may extend props additively but must not repurpose them. All components: presentational (no data fetching), es-CO copy via props, WCAG 2.1 AA, ≥48 px interactive targets, jest-axe-clean.

## shadcn/ui primitives added (canonical registry names)

`input`, `label`, `select`, `form`, `checkbox`, `radio-group`, `switch`, `alert`, `alert-dialog`, `separator`, `sonner` — installed unmodified into `frontend/src/components/ui/` per `components.json` (new-york, `cssVariables: false`). Registry names re-verified at install (see research.md R1 environment caveat).

## `PageHeader`

```ts
interface PageHeaderProps {
  title: string;                      // renders <h1> in font-display (Cal Sans)
  subtitle?: string;
  backTo?: { to: string; label: string };  // single-level back link (breadcrumbs deliberately not supported)
  actions?: ReactNode;                // right-aligned action slot
}
```

Replaces the 59 hand-rolled `<h1>` blocks + 16 back-links. The display-font decision (D3) lives here and in the `ui` primitives — never inline styles.

## `EmptyState`

```ts
interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;                 // e.g. "+ Planificar" button
}
```

## `ErrorState`

```ts
interface ErrorStateProps {
  message?: string;                   // friendly es-CO copy; raw errors never rendered
  onRetry?: () => void;              // renders "Reintentar" with spinner while retrying
  isColdStart?: boolean;             // renders the "server waking" variant instead of an error tone
}
```

One centralized cold-start detector helper (`isColdStartError(err)`) ships with it, replacing per-module `resolveErrorMessage`/`mapTechniqueError`/`mapStrengthError` clones.

## `StatCard`

```ts
interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  isLoading?: boolean;               // skeleton state
  href?: string;                     // whole-card link when present (48px target)
}
```

Thin wrapper over `ui/card` (`shadow` via token, never inline). Used by the dashboard now; 031's home tiles extend it (delta/urgency slots) additively.

## `ConfirmDialog`

```ts
interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;             // default "Confirmar"
  cancelLabel?: string;              // default "Cancelar"
  tone?: "default" | "danger";      // danger → initial focus on Cancel
  isPending?: boolean;               // confirm shows spinner, both buttons disabled
  errorMessage?: string;             // inline failure without closing
  onConfirm: () => void;
  onCancel: () => void;
}
```

Built on `ui/alert-dialog` (focus trap, Escape, focus return by construction). Replaces `ConfirmModal` (9 sites), `ConfirmDeleteDialog` (5 sites), both `window.confirm()` calls, and the confirm-chrome of consent/notify dialogs (their form bodies stay in `ui/dialog`).

## `StatusBadge`

```ts
type Status = "success" | "warning" | "danger" | "neutral";

interface StatusBadgeProps {
  status: Status;                    // maps to --color-success / -warning / -danger / grays
  label: string;                     // ALWAYS present — color never the only carrier
  icon?: LucideIcon;                 // defaulted per status
}
```

Domain adapters (e.g. `sessionStatus(s): {status, label}`) live beside their domains; 033 sweeps all six legacy badge implementations onto this.

## `Stepper`

```ts
interface StepperProps {
  steps: { label: string }[];
  active: number;                    // 0-based
  onStepClick?: (index: number) => void;  // only completed steps clickable
  variant?: "compact" | "detailed";  // detailed = onboarding-style with connectors
}
```

On `active` change the host wizard moves focus to the new step heading (`tabIndex={-1}`); the shell exposes `stepHeadingRef` to standardize it. Replaces `SessionStepper`, `ImportWizard`'s inline stepper, and (as `detailed`) `OnboardingStepper`.

## `AthleteLink`

```ts
interface AthleteLinkProps {
  athleteId: number;
  children: ReactNode;               // usually the athlete's display name
  tab?: string;                      // optional ?tab= deep link
}
```

Renders a router link when the current role may open `/athletes/:id`; otherwise a plain `<span>` with identical typography. Single source of truth for the role gate (fixes the 4 admin dead-click sites).

## `Toaster` (sonner)

Mounted once in `App.tsx`. Usage convention: `toast.success(msg)` / `toast.error(msg)` on mutation settle; no page-local toast state anywhere after migration.

## Consumption map (for later features)

| Feature | Consumes |
|---|---|
| 029 subtraction | `ErrorState`/`EmptyState` on surviving screens; `ConfirmDialog` for removals' affected flows; folder moves finalized |
| 030 navigation | `PageHeader` everywhere; user menu + quick-create built on existing `dropdown-menu`; bottom bar targets ≥48px |
| 031 home | `StatCard` (+ additive slots), `EmptyState`, `StatusBadge`, `ErrorState` cold-start variant |
| 032 sessions | `Stepper` focus behavior, `ConfirmDialog`, `EmptyState` in plan section, toasts on attach |
| 033 visual | `StatusBadge` sweep, status tokens in charts, `font-display` everywhere, dark-mode readiness of tokens |
