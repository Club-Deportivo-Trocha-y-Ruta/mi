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

---

# UX review — Progression card (feature 044, US6/US7, T077)

Audience: coach, tablet (~768 px viewport), touch, direct sunlight, variable connectivity. Family variant (`audience="family"`) is noted where it diverges but is out of scope for the SC-008 timing question.
Version analyzed: branch `feat/044-race-history-backfill`, working tree at review time (`frontend/src/components/race/history/{HistoryProgressionCard,HistoryChart,HistoryTable,CaveatsNote,SeasonCompletionChips}.tsx`, `frontend/src/lib/raceHistoryFormat.ts`, mount in `frontend/src/routes/athletes/AthleteDetailPage.tsx`).
Method: code-level review against `specs/044-race-history-backfill/contracts/ui-history.md` §1, `contracts/history-progression-api.md`, and spec SC-008. No live render; a KLM-style walkthrough estimates timing. `npm run dev` was not used.

## Findings

### [BLOCKER] Match between system and the real world / Recognition rather than recall — the card lives under "Insights IA", while a tab literally named "Historial" shows something else
`AthleteDetailPage.tsx:693-696` renders a tab labelled **"Historial"** (History icon) that mounts `AthleteHistoryPanel` — the feature‑041 audit log of edits to the athlete's record (`components/athletes/AthleteHistoryPanel.tsx:1-16`: "Muestra... `GET /athletes/{id}/audit-log`"). Meanwhile `HistoryProgressionCard` — the cross-season race progression this task is reviewing — is mounted above `AthleteAIAnalysisTab` inside the **"Insights IA"** tab (`AthleteDetailPage.tsx:876-878`), whose own icon is `Sparkles`, not `History`. A coach who wants "¿cómo le ha ido entre 2024 y 2026?" has a tab in front of them named exactly for that intent and it is the wrong one — it opens an edit audit trail, not race results. This is the single biggest risk to SC-008: the one-minute budget is spent finding the card before any reading of it can start, and a coach who doesn't already know the workaround (or forgets between seasons) can plausibly fail the task outright, not just run over budget.
Fix: either rename the audit-log tab (e.g. "Actividad" / "Cambios") to free up "Historial" for the race progression card, or move `HistoryProgressionCard` to its own tab/section named "Historial de carreras" distinct from both "Insights IA" and the audit-log "Historial". Either fix should be a product decision (`product-manager`/`engineering-lead`), not a silent rename — the audit-log tab's label may have other stakeholders (feature 041 governance).

### [MAJOR] Honest encoding — the non-finisher marker sits exactly on the "Mediana de su categoría" reference line in the default (gap) view
`HistoryChart.tsx:197-199` places every DNF/DNS/DSQ point at `value: 0`; `HistoryChart.tsx:360-372` draws the median reference line at `y={0}` only when `metric === "gap"` — the default metric (`HistoryChart.tsx:302`, `useState<HistoryMetric>("gap")`). The result: a hollow non-finisher marker (`renderHollowDot`, `HistoryChart.tsx:225-240`) renders directly on top of the dashed "Mediana de su categoría" line. At a glance — exactly the reading mode SC-008 asks for — this looks like "finished at the median," the opposite of "did not finish." The tooltip does disambiguate (`HistoryChart.tsx:280-284`), but a coach scanning the shape of the line across seasons, not hovering every point, gets a false read.
Fix: give the non-finisher line its own fixed y-position independent of the data axis (e.g. a small negative offset below the plotted `domain` floor, or a separate row rendered outside the `ComposedChart`'s value axis, e.g. as icons along a thin strip under the x-axis) so it never coincides with a meaningful reference value.

### [MAJOR] Honest encoding / axis scale integrity — the same `value: 0` for non-finishers can drag the y-domain in "Velocidad media" view
`HistoryChart.tsx:301-429`: no explicit `domain` is set on `<YAxis>`, and the non-finisher `<Line>` (`HistoryChart.tsx:417-427`) shares the default y-axis with the main line via the same `dataKey="value"`. Recharts computes a shared axis' domain from every series that plots on it, so a single DNF forces `0` into the visible range even in "Velocidad media", where real values plausibly cluster tightly (e.g. 18–22 km/h). One non-finisher season would compress the entire meaningful speed range into a sliver of the chart height, undermining the very "did they improve" reading SC-008 asks for. (Flagged with high but not absolute confidence in Recharts' exact domain-sharing behaviour for this configuration — verify with a live render using a fixture that mixes a DNF and a narrow speed range before treating as confirmed.)
Fix: pin the y-axis `domain` from only the real (non-phantom, non-marker) values, or render the non-finisher marker via `yAxisId` on a second, hidden/synced axis so it never participates in the visible axis' domain calculation.

### [MAJOR] Match between system and the real world — the family "subió de categoría" copy assumes every category change is an age promotion, which the data model doesn't guarantee
`HistoryTable.tsx:122-134` hard-codes "**Subió de categoría**: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo." for every group where `categoryChanged` is true. But `category_changed` is defined purely as "`category_id` differs from the athlete's previous point" (`contracts/history-progression-api.md:32`), with no direction guarantee — and the import contract's own category-mapping taxonomy (`ui-history.md` §2: "categoría · tipo (exacta / **renombrada** / propia de esa temporada / sin reconocer)") confirms that a category can be renamed or remapped year to year without representing an actual age-bracket promotion. If a renamed-but-equivalent category (or, rarer, a corrected miscategorization) trips `category_changed`, a parent reading the family variant is told their child "moved up to race against older athletes" and that a drop in placing is "normal" — which may simply be false, and is exactly the kind of unverifiable, deterministic-sounding claim about a minor's competitive standing the club's own criteria ask reviewers to reject.
Fix: derive actual promotion direction (e.g. compare category age-order, not just id/label difference) before choosing this copy, or fall back to neutral wording ("Cambió de categoría a partir de esta fecha") when direction can't be confirmed, reserving the reassurance sentence for confirmed promotions.

### [MAJOR] Tablet touch targets — the chart's metric toggle renders at 36 px, under the club's own ≥44×44 px floor
`HistoryChart.tsx:312-330` renders `ToggleGroup`/`ToggleGroupItem` without a `size` prop, so both default to `size="default"` → `h-9` (36 px, `components/ui/toggle.tsx:16`). This is the one interactive control inside the chart a coach touches — switching "Brecha a la mediana" ↔ "Velocidad media" — and it falls short of the tablet/gloved-hands criterion the rest of this feature (and the identity-review screen reviewed under T054) already meets for its primary actions.
Fix: pass `size="lg"` (44 px, `toggle.tsx:18`) to `ToggleGroup`/`ToggleGroupItem` here.

### [MINOR] Recognition rather than recall — the inverted gap axis has no on-screen cue for its direction beyond the zero line's label
`HistoryChart.tsx:345-350` (`<YAxis reversed={metric === "gap"} .../>`) has no axis title; the only in-chart text anchoring the inversion is the zero reference line's "Mediana de su categoría" (`HistoryChart.tsx:363-371`), which says what zero means but not which direction is "better." A coach who hasn't internalized the convention (or a new coach) can misread a line trending visually upward as "falling behind" or vice versa — a real risk given SC-008 is specifically about reading trend direction fast.
Fix: add a small explicit cue near the axis or chart header when `metric === "gap"`, e.g. "↑ más rápido que la mediana" — cheap, and removes the one ambiguity a quick scan can't resolve on its own.

### [MINOR] Consistency and standards — the two "text-first" blocks read in opposite chronological order
`SeasonCompletionChips.tsx:22-24` explicitly sorts ascending ("la narrativa de la tarjeta es 'cómo progresó de una temporada a la siguiente'"), rendered first in the card. Immediately below it, `HistoryProgressionCard.tsx:143-146` sorts "Últimos resultados" descending (most recent first). Two blocks the coach reads within the same few seconds, stacked vertically, run in opposite time directions — a small but real orientation cost precisely when SC-008 rewards a fast, uninterrupted scan.
Fix: pick one direction for the whole "text-first" block, or add a one-word cue ("más recientes primero") to the "Últimos resultados" heading so the reversal is intentional rather than implicit.

### [MINOR] Accessibility — the chart's SVG text isn't suppressed for assistive tech even though the table is the documented alternative
`HistoryProgressionCard.tsx:157-161` wraps the lazy chart only with `aria-describedby={CAVEATS_NOTE_ID}`; nothing marks the chart's own SVG (axis ticks, `ReferenceLine` labels) as decorative relative to `HistoryTable` below it, which the contract designates as the chart's text alternative (`ui-history.md` §1: "Chart has a text alternative (the table below)"). A screen-reader user tabbing through will likely encounter fragments of axis-tick and reference-line text nodes ahead of the table, duplicating it out of order. This is a verbosity/redundancy issue, not necessarily an `axe` violation on its own.
Fix: wrap the chart's outer container in `aria-hidden="true"` (safe, since `HistoryTable` already carries the same information as accessible markup) or give the `ComposedChart`'s container `role="img"` with a short summary `aria-label`.

## SC-008 timing estimate (KLM-style)

| Path | Steps | Est. time |
|---|---|---|
| **Already knows the card is under "Insights IA"** | click tab (K+M ≈1.5s) → text-first block renders instantly, read chips + last-3 + category-changes (≈10-15s) → chart chunk arrives on 3G (≈2-4s) → read chart incl. re-deriving axis direction (≈8-12s) → optional table cross-check for exact 2024 vs 2026 figures (≈8-10s) | **≈30-45 s** |
| **First-time / natural guess (tries "Historial" tab first)** | click "Historial" (K+M ≈1.5s) → perceive it's an audit log, not race history (≈3-5s) → backtrack, click "Insights IA" (≈1.5s) → same as above | **≈55-75 s** |

The trained-user path clears the one-minute budget, but with little margin once the inverted-axis ambiguity (finding above) costs a second look, and it depends entirely on the coach already having learned the workaround around the "Historial" tab collision. The untrained/occasional-user path — plausible for a part-time or new coach, or after a season's gap — blows the budget on wayfinding alone, before any of the chart's own content is read. The BLOCKER finding above is the dominant lever on this estimate, ahead of any chart-legibility polish.

## What's already right (no finding needed)
- Real "text-first" design: season chips, last-three results and category-changes render as plain DOM immediately, independent of the lazy `recharts` chunk (`HistoryProgressionCard.tsx:130-161`) — the 3G budget concern is genuinely addressed.
- Category changes are hard breaks, never bridged by a solid or dashed connector (`HistoryChart.tsx:183-187`), and get their own vertical `ReferenceLine` with an "A → B" label — matches the "different pelotón, don't imply a trend" intent exactly.
- `HistoryTable` groups by season → category with a true `<tbody>` break per group and no shared border/line across groups (`HistoryTable.tsx:50-70`, `107-148`).
- `"sin dato"` (never a dash or zero) is applied consistently across every derived metric in both the table and the chart tooltip (`raceHistoryFormat.ts:16-40`; percentile/gap already come back `null` from the backend below field size 5, per `types/raceHistory.types.ts:95-99`).
- `CaveatsNote` is unconditional whenever the card has data, degrades to a generic sentence instead of disappearing for an unrecognized code, and is wired via `aria-describedby` (`CaveatsNote.tsx`, `HistoryProgressionCard.tsx:157,165`).
- Colour is never the only channel: category changes are a dashed vertical line + text label, dashed vs. solid vs. no-stroke lines encode gap type, and the non-finisher marker is a distinct hollow shape, not just a colour swap.
- Family copy avoids comparative language about the child in the table's category-change note and instead states an expectation ("es normal que el puesto baje al comienzo") — right instinct, see the MAJOR finding above about when that copy actually applies.
- The chart mechanically avoids per-segment `<Line>` fragility for the tooltip (single line + phantom nulls + `connectNulls={false}`, documented in `HistoryChart.tsx:20-28`) — a deliberate, sound choice already covered by its own test (`__tests__/HistoryChart.test.tsx`).

## Executive summary
Critical (blocker): 1 · Major: 4 · Minor: 3
Top 3 priorities: (1) the "Historial" tab naming collision — fix before shipping, it undermines SC-008 more than every chart-legibility issue combined; (2) the non-finisher marker sitting on the median reference line in the default metric view — a genuine honest-encoding bug; (3) the hard-coded "subió de categoría" family copy, which can assert something false about a minor's competitive trajectory when a category change is really just a rename.

## Next steps
Findings are recommendations only — implementation belongs to `react-ui-engineer` via `engineering-lead`, not this review.
