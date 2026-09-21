# UX review — Identity review screen (feature 044, US4, T054)

Audience: coach, tablet (~768 px viewport), touch, variable light/connectivity.
Version analyzed: branch `feat/044-race-history-backfill`, working tree at review time (`frontend/src/routes/competitions/history/IdentityReviewPage.tsx`, `frontend/src/hooks/race/useIdentityReview.ts`, `frontend/src/types/raceIdentity.types.ts`, tests in `frontend/src/routes/competitions/history/__tests__/IdentityReviewPage.test.tsx`).
Method: code-level review against `specs/044-race-history-backfill/contracts/ui-history.md` §4 and spec SC-009. No live render; a KLM-style walkthrough estimates timing. `npm run dev` was not used.

## Findings

### [MAJOR] Consistency and standards / Visibility of system status — decide buttons give no in-flight feedback
`IdentityReviewPage.tsx:206-229` — `decide-same-person` / `decide-different-people` only get `disabled={isDeciding}`; no spinner or label change while `decideMutation.isPending`. The undo confirmation button two hundred lines below (`IdentityReviewPage.tsx:602-611`) does the opposite: it swaps its own label to `"Deshaciendo..."` while pending. On the coach's variable-connectivity tablet, a click on "Es la misma persona" that takes a second or two to round-trip looks identical to a click that silently failed to register — nothing distinguishes "the app is thinking" from "nothing happened," which invites a repeat tap.
Fix: mirror the existing `"Deshaciendo..."` pattern — swap in a `Loader2` (already imported) and change the label to something like `"Guardando..."` while `isDeciding`, on both decide buttons.

### [MAJOR] Error prevention — no guard against a second decision landing on the wrong candidate
`IdentityReviewPage.tsx:319-340` (`handleDecide`) and `319-340`/`210`/`222` (`disabled={isDeciding}`). `isDeciding` tracks only `decideMutation.isPending`, which resolves as soon as the mutation's HTTP response lands — before `candidatesQuery`'s invalidated refetch (`useIdentityReview.ts:87-89`) has actually swapped in the next candidate. TanStack Query v5 keeps showing the previous `items[0]` while that refetch is in flight (`isFetching`, not `isLoading`), so there is a real window where the buttons are re-enabled but the screen still shows the just-decided pair. A coach using the keyboard shortcuts to move fast (`"1"`, `"1"`, `"1"`...) can have the second keypress land after the refetch resolves — which silently decides the *next* candidate rather than erroring. This is a correctness/trust risk specific to the speed this screen was designed to reward: SC-009 optimizes for rapid, low-friction decisions, and the one place a rapid double-input can go wrong is exactly the place today's `disabled` check doesn't cover.
Fix: extend the disabled condition to also cover `candidatesQuery.isFetching` (or track "settled" via the mutation's own `onSettled` plus a short guard until the invalidated query resolves), so a second keystroke/click can't apply before the new candidate is confirmed on screen.

### [MAJOR] Accessibility (WCAG AA 1.4.3 contrast) — keyboard-shortcut hint unreadable on the primary button
`IdentityReviewPage.tsx:215` — `<span className="ml-1.5 text-xs opacity-70">(1)</span>` sits inside the filled `default`-variant button (`Button` renders white text on `--color-primary` `#20b7c9`, see `frontend/src/components/ui/button.tsx:33`). White text at 70% opacity over that teal blends to roughly `rgb(188,233,239)` on `rgb(32,183,201)` — a contrast ratio of about **1.85:1**, far under the 4.5:1 AA floor for 12 px text (`text-xs`). The outline button's `(2)` hint (`IdentityReviewPage.tsx:227`, charcoal at 70% opacity on white) is fine at ≈5.2:1 — only the filled button's hint fails, and it fails badly. In direct sunlight, which this coach persona explicitly works under, it will read as blank space, defeating the point of surfacing the shortcut.
Fix: drop the opacity modifier on the `(1)` hint and use a token with guaranteed contrast against `--color-primary` (e.g. plain white, `text-white/90` only if verified, or move the hint to a small badge with its own background) — same treatment the `(2)` hint already gets for free by living on a white button.

### [MINOR] Flexibility and efficiency of use — touch targets in the "decided" list drop to 36 px
`IdentityReviewPage.tsx:267-277` (`Deshacer` row button, `size="sm"` → `h-9`/36 px per `button.tsx:44`) and `IdentityReviewPage.tsx:552-568` (`Anterior`/`Siguiente` pagination, same `size="sm"`). The project's own tablet criterion is ≥44×44 px touch targets; the pending-mode decide buttons meet it (`min-h-12`/48 px), but the moment a coach switches to a "Decididos" filter to fix a misclick, every actionable control on that screen shrinks below the floor. This is exactly the recovery path for the double-decision risk above, so it's worth the same care.
Fix: bump these three buttons to `size="default"` (44 px) — there's no density constraint on this page that requires the compact variant.

### [MINOR] Recognition rather than recall — linked-athlete warning names the risk but not the stakes
`IdentityReviewPage.tsx:183-188` (decision card chip) and `258-263` (row chip) both show `"Incluye un deportista enlazado"` with no explanation of what the coach should do differently. Given this is the one candidate type where a wrong call touches a real athlete's history (not just a print artifact), a bare warning label asks the coach to already know why it matters.
Fix: add one line under the chip, e.g. `"Revisa con cuidado: uno de los dos registros ya está vinculado a un deportista del club."` — reuses copy already close to the undo dialog's tone.

### [MINOR] Match between system and the real world — undo copy for "personas distintas" is ambiguous
`IdentityReviewPage.tsx:592-593` — `"Esto no une resultados ya cargados hasta que decidas de nuevo."` reads as a double negative under time pressure ("this doesn't merge already-loaded results until you decide again") and doesn't actually describe what *does* happen on undo (the candidate just returns to pending; nothing changes about the data). Contrast with the `same_person` branch two lines above, which plainly states the consequence ("se separan de nuevo en dos competidores").
Fix: state the no-op plainly, e.g. `"No hay resultados unidos que separar: el candidato solo vuelve a quedar pendiente."`

### [MINOR] Toast + undo could close the loop for the double-decision risk above
`IdentityReviewPage.tsx:319-340` — `toast.success(message)` on decide is a plain notification (`sonner`, already imported). Since the realistic failure mode on this screen is a fast, confident coach deciding the wrong pair, adding sonner's own `action: { label: "Deshacer", onClick: ... }` to that same toast would let a misclick be corrected in one tap, without navigating to a different state filter first (today's only path: switch the `Select` to "Decididos: ...", find the row, click `Deshacer`, confirm — four actions to recover from one accidental keystroke).
Fix: wire the toast's `action` to call the same `reverseMutation.mutate` used by `handleConfirmUndo` (`IdentityReviewPage.tsx:342-365`), skipping the confirmation dialog only for this "I just did this, undo it" path — the deliberate-undo path elsewhere can keep the dialog.

## SC-009 timing estimate (KLM-style, steady state after the first candidate)

| Step | Operator | Est. time |
|---|---|---|
| Perceive new candidate has loaded | M | 1.35 s |
| Read kind badge + similarity score | — | 0.8 s |
| Read signal(s) in words (1–2 typical) | — | 1.5 s |
| Read left card (name, club, city, seasons, categories) | — | 2.0 s |
| Read right card | — | 2.0 s |
| Decide | M | 1.35 s |
| Press `1`/`2` | K | 0.2 s |
| **Total (keyboard)** | | **≈ 9.2 s** |
| Mouse instead of keyboard (home + point + click) | H+P+K | +1.5 s → **≈ 10.7 s** |

Both paths clear the 15 s target with margin under typical conditions (1–2 signals, short season/category lists). The budget tightens for a candidate with 3+ signals or a competitor with five seasons × multiple categories per side — plausibly 3–5 s of extra reading, landing at 12–15 s, plus first-exposure unfamiliarity with the Spanish signal phrasing before the coach has seen a few examples. Not a blocker: the copy is already in plain words (no jargon, no raw signal codes), which is the main lever available; the remaining lever is visual — currently nothing highlights *which* fields differ between the two cards (e.g. differing club/city), so the coach re-derives that from the signal sentence rather than seeing it at a glance. Consider bolding a field that differs between `left`/`right` when the corresponding signal is present (`club_and_city_differ` → bold `Club`/`Ciudad` on both cards) as a later, non-blocking polish — would shave the two multi-second "read left/right card" steps closer to 1 s each.

## What's already right (no finding needed)
- Two ≥48 px decide buttons (`min-h-12`, `button.tsx:44`), natural-language signals (no raw codes, `signalLabel()` fallback for unknown codes), visible `"N de M decididos"` progress with `aria-live="polite"`, keyboard shortcuts `1`/`2` correctly suppressed while focus is in a form control or the undo dialog is open, non-destructive idempotent rebuild (never resets a decided candidate, per `identity-review-api.md`), consistent `"Sin dato"` fallback for missing club/city/seasons/categories, `prefers-reduced-motion` handled globally (`frontend/src/style.css:424`) so the `Loader2` spins are already neutralized for users who need that, full diacritics throughout, and existing jest-axe coverage at zero violations for both the page and the undo dialog (`IdentityReviewPage.test.tsx:250-282`).

## Executive summary
Critical: 0 · Major: 3 · Minor: 4
Top 3 priorities: (1) the `(1)` keyboard-hint contrast failure on the filled button — quick CSS fix, real accessibility bug; (2) close the disabled-state gap between mutation-pending and query-refetching so a fast double-input can't silently decide the wrong candidate — the one real risk in a screen designed for speed; (3) give the decide buttons the same in-flight feedback the undo button already has.

## Next steps
Findings are recommendations only — implementation belongs to `react-ui-engineer` via `engineering-lead`, not this review.
