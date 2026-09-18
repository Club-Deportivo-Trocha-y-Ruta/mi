# Contract — Third-party progression lock (US3 · FR-012…FR-015)

## Guard

`app/services/race/third_party_guard.py`

```python
class ThirdPartyProgressionForbidden(PermissionError): ...

async def require_club_competitor(db, competitor_id: int) -> int:
    """Return the linked athlete_id or raise. Reads current state, so an unlink takes effect immediately."""

def club_competitor_only(fn):   # marker decorator: calls the guard on the `competitor_id` argument
```

Applied to every public callable under `app/services/race/` that accepts `competitor_id` and returns data spanning more than one válida — at minimum `analytics.athlete_progression`, `analytics.podium_gap`, `analytics.projection`, and the loaders that feed `compute_field_metrics` for the AI node and the newsletter builder. Router edge maps the exception to `403 {"code": "third_party_progression_forbidden"}`.

## Structural test

`tests/privacy/test_third_party_lock.py` imports the package, collects public callables with a `competitor_id` parameter, and fails unless each carries the marker or appears in `ALLOWED_SINGLE_EVENT` (a short reviewed tuple, each entry with a one-line justification). A new unguarded function therefore breaks CI.

## Behavioural tests

Unlinked competitor with results in three seasons → refused for admin, coach, parent, athlete; linked competitor → served; unlink → refused on the next call; a sweep of log records, fake-LLM `last_request` prompts, newsletter context and family responses produced in the test contains none of the synthetic third-party names.

## Ordering rule

This contract ships, with its tests green, before any historical import is committed against real data. The runbook's pre-load checklist has a line for it, and `tasks.md` orders it before the load phase.

## Legal basis (to be reproduced in `docs/10-race-results/history-backfill-design.md` and the privacy audit)

Legitimate interest in a sporting context, limited to situating the club's own athletes; third-party results are used as field-level aggregates only. Publication on the organiser's blog does not make the data "public data" under Ley 1581 Art. 3(g). Erasure of unlinked competitors and retention of stored source files are required by the audit and deferred to the next feature (FR-043).
