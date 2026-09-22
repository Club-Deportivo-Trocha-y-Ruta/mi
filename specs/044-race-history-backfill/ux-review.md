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

---

# UX audit — T083, family view of the cross-season history

Audience: parent, Android mobile 360 px, intermittent 3G/4G, variable digital literacy.
Version analyzed: branch `feat/044-race-history-backfill`, working tree at review time (`frontend/src/routes/parents/MyAthleteDetailPage.tsx`, `frontend/src/components/race/history/{HistoryProgressionCard,HistoryChart,HistoryTable,CaveatsNote,SeasonCompletionChips}.tsx` with `audience="family"`, `frontend/src/lib/raceHistoryFormat.ts`, `frontend/src/routes/parents/__tests__/MyAthleteDetailPage.history.test.tsx`, `docs/10-race-results/history-family-notice.md`). Checked against spec FR-042, FR-038, FR-040/041, and constitution Principle V (youth psychological safeguards — no shaming comparison, no deterministic claims about a minor). Code-level review, no live render.

## Findings

### [BLOCKER] Responsive / mobile-first — `HistoryTable` has no viewport accommodation at all; 7 columns will overflow a 360 px screen
`HistoryTable.tsx:88-92` renders a bare `<table>` with seven columns (Fecha, Válida, Puesto, Percentil, Parrilla, Brecha, Velocidad) with no wrapping container, and `HistoryProgressionCard.tsx:163` mounts it directly inside the card's `section` with no `overflow-x-auto`. This breaks a convention the project has already established for exactly this problem: `TableScrollContainer` in `components/ui/table.tsx:168-213` ("criterio C5 de la auditoría responsive: overflow-x-auto CON indicador"), and `AnthropometryHistory.tsx:171-173` goes further — it hides the desktop `<table>` below `md:` and shows a dedicated `<ul>` of stacked cards for narrow viewports. `HistoryTable` does neither. At 360 px, seven columns of dates, places, percentiles and speeds will either force the whole page into horizontal scroll or squeeze into unreadable multi-line cells — this is the family view's non-negotiable "no horizontal scroll on mobile" criterion failing on the one data-dense block of the tab, right below the text-first summary this feature otherwise gets right.
Fix: wrap `HistoryTable`'s `<table>` in `TableScrollContainer` (cheapest, consistent with `CategoryMappingTable.tsx:195` and `MonthlyMetricsTable.tsx`), or — better for a parent audience that isn't scanning for precision, closer to `AnthropometryHistory`'s pattern — collapse each row to a stacked mobile card (date + válida as the heading line, puesto/percentil/brecha/velocidad as label:value pairs) below `md:` and keep the full table for the coach's tablet width. Either fix stays inside `HistoryTable.tsx`; `audience` already threads through this component so the mobile layout could ship for both audiences without a new prop.

### [MAJOR] FR-042 — the category-change copy no longer explains *why* the placing looks different, only that it shouldn't be compared
`HistoryTable.tsx:122-141` — current text: *"Cambió de categoría (de {prev} a {curr}). En la nueva categoría compite con otro grupo, así que el puesto no se compara directamente con el anterior."* This is the fix from the prior review (T077's MAJOR finding on the discarded "Subió de categoría… deportistas mayores… el puesto baje" copy, confirmed by the pinned test at `MyAthleteDetailPage.history.test.tsx:190-192`), and it correctly avoids overclaiming — but FR-042 requires two things, not one: *(a)* "avoid comparative or discouraging language about a minor" (met) **and** *(b)* "explain in plain language that moving up means racing older riders and that a lower placing right after the change is expected" (not met — the current copy states only the bare fact of a category change and that comparison is invalid, never the reason or the expectation).
This isn't a simple copy restore, though: checked `contracts/history-progression-api.md:32` and `research.md:114` — `category_changed` is `true` for any `category_id` difference *except* a pure rename; it does **not** distinguish a genuine age-band promotion (Infantil → Prejuvenil) from a season-specific catalogue restructuring (e.g. spec.md:36's master B splitting into B1/B2, or pre-infantile girls splitting into A/B between 2024 and 2025) — cases where the athlete's own age band didn't necessarily move up at all. `RaceHistoryPoint` (`raceHistory.types.ts:84-88`) carries no field that lets the frontend tell these apart. So literally restoring "subió de categoría, compite con mayores" for every `category_changed=true` would reintroduce the exact risk T077 flagged: asserting something about a minor's competitive trajectory that the data doesn't actually support.
Fix: this needs a backend change, not a frontend copy change — expose a tri-state on `RaceHistoryPoint` (e.g. `category_change_kind: "promotion" | "restructure" | null`) derived by comparing the catalogue's stored age ranges of the previous vs. new category (available per spec.md:36's frozen age-range data), and gate the FR-042 explanation on `"promotion"` only:
> "Cambió de categoría (de {prev} a {curr}). Al subir de categoría se corre contra ciclistas mayores, así que es normal que el puesto de las primeras carreras se vea distinto al de la categoría anterior — no significa que haya bajado su nivel, por eso no se compara directamente con lo anterior."
— falling back to the current neutral sentence for `"restructure"` or unknown, since that's the honest floor. Flag this to `product-manager`/`engineering-lead` as a follow-up task against `history.py::build_history_points`; it's out of scope for this file alone.

### [MAJOR] Microcopy — "Percentil" and "Brecha a la mediana" are never explained in plain words anywhere in the family view
Directive for this audit explicitly calls for "percent/percentile explained in plain words," and it isn't happening. `HistoryTable.tsx:101,103` ships raw column headers "Percentil" / "Brecha" with values like `formatPercentile` → `"P65"` and `formatGapPct` → `"-4.2 %"` (`raceHistoryFormat.ts:16-30`) and no legend. `HistoryChart.tsx:363-371`'s only in-chart cue is the axis hint "Más rápido que la mediana ↑ · Más lento ↓" (already gated to `metric === "gap"`, `HistoryChart.tsx:381-385`) — useful for the chart, absent from the table. `CaveatsNote`'s own catalogue (`raceHistory.types.ts`, `small_fields`/`non_finishers_excluded` entries) *uses* the terms "percentil" and "brecha a la mediana" as if the reader already knows them ("el percentil y la brecha a la mediana pueden no ser representativos"), compounding the gap instead of resolving it. For a parent with variable digital literacy reading "P65" or "+11.8 %" cold, this is opaque statistical jargon with no anchor — exactly the audience this card is least text-first for once the reader moves past the "text-first" summary block into the table.
Fix: add one short, audience-gated (`audience === "family"`) explainer, either as a `role="note"` line above `HistoryTable` or folded into `CaveatsNote` for the family variant, e.g.: *"Percentil: de cada 100 corredores de su categoría en esa válida, cuántos terminaron detrás. Brecha: qué tan lejos, en porcentaje, estuvo del tiempo típico (mediana) del grupo — negativo es más rápido, positivo es más lento."* Coach audience can keep the bare terms; a coach already works with this vocabulary daily.

### [MINOR] Microcopy tone — "el atleta" reads clinical in a parent-facing card that otherwise says "tu hijo/a"
`HistoryProgressionCard.tsx:102-104` — *"Cómo ha cambiado el atleta entre temporadas de Copa Valle."* This subtitle is shared verbatim across `audience="coach"` and `audience="family"` (the file's own comment at `HistoryProgressionCard.tsx:5-9` confirms only `HistoryTable`'s copy is audience-gated). Third-person "el atleta" matches the coach's professional register (tracking one of several athletes) but is a step colder than the tone the rest of the family surface uses — the privacy notice draft (`history-family-notice.md:44`) and other parent screens consistently say "tu hijo o hija." The component doesn't currently receive the athlete's first name, so this is a small, low-cost warmth gap rather than a functional one.
Fix: thread the athlete's first name (already available to `MyAthleteDetailPage` via `useAthlete`) into an optional `athleteFirstName` prop, and render *"Cómo ha cambiado {firstName} entre temporadas de Copa Valle."* for `audience="family"` only, keeping "el atleta" for coach. Low priority — bundle with the FR-042 copy fix above rather than shipping alone.

## What's already right (no finding needed)
- FR-041's gate is genuinely invisible from the frontend: `HistoryProgressionCard` has no knowledge of `club_join_date` or the policy gate at all — the empty state ("Todavía no hay carreras históricas para comparar entre temporadas.") is the same generic message regardless of why a point is missing, so there is no way for a parent to infer a result is being withheld.
- No third-party data reaches the family DOM — confirmed by both the code (no `competitor_id`/name field on `RaceHistoryPoint`) and the dedicated regression test (`MyAthleteDetailPage.history.test.tsx:208-223`).
- `history-family-notice.md`'s draft policy paragraph is plain, honest, non-alarming, states the legal basis and a correction channel, and doesn't overclaim the erasure/retention work deferred to FR-043 — no dark pattern, no buried opt-out.
- The `CaveatsNote` and non-finisher status labels ("No terminó", "No salió", "Descalificado") are kind, factual, and never phrase a DNF/DNS/DSQ as a failure.
- Chart metric toggle already meets the ≥44 px touch-target floor (`HistoryChart.tsx:371`, `min-h-12`, fixed in the T077 review).
- `"sin dato"` is applied consistently everywhere a derived metric is null — never a dash, never a zero, never silently blank.

## Executive summary
Critical (blocker): 1 · Major: 2 · Minor: 1
Top 3 priorities: (1) `HistoryTable` has zero mobile accommodation — a 360 px parent hits an unreadable/overflowing 7-column table with no established project pattern applied; (2) FR-042's explanatory half is still unmet, and a safe fix needs a backend `category_change_kind` distinction (promotion vs. restructure), not just new frontend copy; (3) percentile/brecha are never explained in plain language for the family audience, despite being the two headline metrics of both the table and the chart.

## Next steps
Findings are recommendations only — implementation belongs to `react-ui-engineer` via `engineering-lead`; the FR-042 backend gap should go to `product-manager`/`engineering-lead` as a follow-up task, not be patched with copy alone.
