# Strava Activity Sync — Coach Review-Flow Guide

**Audience:** coach and club administrator.
**Goal:** turn raw Strava activities that flow in automatically into training evidence, by linking the ones that matter to the planned session on the calendar — in a few clicks per activity.

Technical detail in [`plan.md`](../../specs/025-strava-activity-sync/plan.md), [`data-model.md`](../../specs/025-strava-activity-sync/data-model.md) and [`contracts/api.md`](../../specs/025-strava-activity-sync/contracts/api.md). Family-facing guide in [`guia-familias.md`](guia-familias.md). Operational/deploy detail in [`runbook-ops.md`](runbook-ops.md).

---

## 1. What arrives automatically, and what you decide

Once a family connects an athlete's Strava account (family-facing guide, section 3), every new ride that athlete syncs to Strava appears in the platform on its own — date, sport type, duration, distance, average/max heart rate. It arrives **unlinked** by default.

Only coach and admin roles can decide what happens next:

- **Link it** to a specific planned training session from the club calendar.
- **Leave it unlinked.** This is a normal, permanent state — free rides, family outings, commutes are expected and do not need any action.

Parents and athlete-scoped accounts can see the link state but have no action to change it — linking is coach-gated by design (the coach explicitly asked for manual, not automatic, matching).

## 2. Review view (`/activities`)

Open **Revisión de actividades** (route `/activities`, coach/admin only). Activities are grouped by day, most recent day first; within a day, newly-arrived unlinked activities render before already-linked ones so the fastest path (link the new ones) stays on top.

Filters available:

- **Estado**: todas / sin enlazar / enlazadas.
- **Atleta**: narrow to one athlete.
- **Desde / Hasta**: date range.

A week's worth of club activity (≈30–60 rides) is designed to be processed in under 10 minutes with these filters plus the "Cargar más" pagination at the bottom.

Each row is an `ActivityCard`: sport type, duration, distance, average/max heart rate, an indoor/trainer flag when applicable, and a link-state badge:

| Badge | Meaning |
|---|---|
| Green | Linked to a session. |
| Amber | Unlinked. |
| Red — "Eliminada en Strava" | The athlete deleted the activity on Strava's side; the platform kept the row (and any session link) instead of hard-deleting it, so review it before deciding whether the link still makes sense. |

## 3. Linking an activity to a session

1. From the review view (or from the activity list on an athlete's profile), open the link action on an unlinked activity.
2. The dialog shows **suggested sessions**: same club, scheduled within ±1 day of the activity's date, same-day sessions and sessions where the athlete was marked present ranked first (badges "Mismo día" / "Asistió"). Pick one — this is the fast path, no typing needed.
3. If the right session isn't in the suggestions (activity uploaded late, or logged against a session further than a day away), use **"¿No encuentras la sesión? Buscar en el calendario"** — a text search over the full club calendar (date, location, technical focus).
4. Confirm with **Vincular**. The badge turns green immediately.

Total: pick a suggestion + confirm = 2 clicks; opening the dialog is the third interaction — matches the ≤3-interactions target for the routine case.

**Re-linking**: open the dialog on an already-linked activity (title changes to "Editar vínculo de sesión", the current session pre-selected) and pick a different one, then **Actualizar vínculo**. The previous association is replaced, not duplicated.

**Unlinking**: same dialog, **Desvincular** button at the bottom. The activity returns to "sin enlazar" — a valid state, use it freely for anything that isn't training evidence (a 5-minute test ride, a family outing, etc.).

## 4. Where linked activities show up

- **Session detail**: the session's linked activities are visible per athlete, alongside attendance and the rubric — this is the training-evidence view for that session.
- **Activity list** (review view or athlete profile): each activity shows which session it's linked to, if any.

The linked session does not need to have the activity's athlete on its attendance list — the coach's call to link overrides that, though attendance is used to rank suggestions higher.

## 5. Delayed and incomplete data — don't wait on it

Two situations are expected, not errors:

- **Late uploads**: an athlete's device may only sync to Strava when they get home, hours or days after the ride. The activity still arrives and can be linked to a past session normally — nothing is time-limited on this side.
- **Incomplete summary on first arrival**: occasionally the first delivery from Strava is missing a field (e.g., heart rate not yet processed). The row still shows up; a later reconcile pass completes it in place — no duplicate is created, and you don't need to re-link it.

## 6. Privacy — what you will never see here

No route map, no precise start/end location, for any activity, of any athlete — this is a data-minimization decision, not a display toggle: the platform never stores those fields from Strava in the first place (Ley 1581/2012, minors' data). If you need the exact route for a legitimate reason (e.g., verifying a race recon), that has to happen outside the platform, directly in Strava, with the family's own account access.

## 7. Consent gate — before you can even connect

The **Conectar con Strava** button on an athlete's profile stays disabled, with the message "Falta el consentimiento del acudiente para sincronizar actividades externas", until an active consent record exists for that athlete. Today this consent is **not** self-service for parents — you (coach) or the admin register it after the family authorizes verbally or in writing, the same pattern used for the psychological-assessment consent (feature 017). See [`runbook-ops.md`](runbook-ops.md) §4 for how to register it.

## 8. Quick reference — states you'll see on an athlete's Strava card

| Status badge | Meaning | Action available |
|---|---|---|
| Sin conectar | Never connected. | "Conectar con Strava" (needs consent first). |
| Conectado | Syncing normally. | "Desconectar" if needed. |
| Conexión rota | Strava revoked or the refresh token failed. | "Reconectar" — same flow as first connection. |
| Desconectado | Intentionally disconnected (family or coach). Past activities remain. | "Reconectar". |
