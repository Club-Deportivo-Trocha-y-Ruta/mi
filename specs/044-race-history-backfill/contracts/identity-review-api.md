# Contract — Identity review (US4 · FR-016…FR-022)

Router: `app/routers/race_identity.py`, prefix `/api/race-identity`, `require_role([admin, coach])`. Service: `app/services/race/identity_review.py` (candidate building, decisions, reversal) and `app/services/race/identity_resolver.py` (used by the ingestor).

## Endpoints

| Method & path | Purpose | Notes |
|---|---|---|
| `POST /rebuild` | Recompute candidates over all staged (not committed) imports plus existing competitors | Worker thread, 30 s timeout, budget ≤ 10 s. Idempotent through `pair_hash`; never resets a decided candidate. Returns `{created, unchanged, pending}` |
| `GET /candidates?state=&kind=&page=` | Paginated queue, ordered by `score DESC` | Response items: `id`, `kind`, `score`, `signals[]`, `left`, `right`, `state`, `linked_athlete_involved` |
| `GET /summary` | `{pending, same_person, different_people}` | Drives the commit gate banner |
| `POST /candidates/{id}/decide` | body `{answer: "same_person" \| "different_people"}` | 409 if not `pending`. `record_audit` with both record ids/hashes, never names |
| `POST /candidates/{id}/reverse` | Return a decided candidate to `pending` and undo its effect | If results were already committed under the decision, performs the split/merge described below |

`left` / `right` (`IdentityRecordRead`, coach/admin only): `name_printed`, `club`, `city`, `seasons[]`, `category_labels[]`, `competitor_id?`, `athlete_linked`. This is the **only** schema in the platform that serialises `city`.

## Candidate rules

- *same_person_suspect*: `normalized_name` differs; `token_set_ratio ≥ 90`; compatible sex; age path non-decreasing across seasons. Comparison blocked by shared surname token.
- *homonym_suspect*: identical `normalized_name` and any of `same_valida_two_categories`, `sex_conflict`, `age_path_backwards`, `club_and_city_differ` (both fuzzy < 70 after normalisation). A changed club alone raises nothing.
- `linked_athlete_involved = true` when either record's competitor has `athlete_id`.

## Resolver (ingest time)

```
signature exact hit                      → that competitor
name hit, one competitor, no signal      → attach + add signature
decision same_person                     → decided competitor + add signature (source_candidate_id)
decision different_people                → new competitor + signature
name hit, several competitors, no tie-break → impossible after the gate; raise IdentityUnresolved (500-class guard, tested)
```

New results get `athlete_id = competitor.athlete_id` whenever the competitor is linked, whatever the row's club.

## Commit gate

`POST /api/race-imports/{id}/commit` and `/commit-pending` → `409 {"code": "identity_review_pending", "pending": n}` while `pending > 0`.

## Reversal semantics

- Reversing `same_person` after commit: the signature with `source_candidate_id = id` moves to a new competitor together with the results that were ingested under it; if the original competitor is linked, the new one is left unlinked and `athlete_id` is cleared on the moved results; one `RaceCompetitorLinkAudit`-style audit entry plus `record_audit`.
- Reversing `different_people` after commit: the two competitors stay apart until a new `same_person` decision merges them (merge = move signatures and results to the older competitor, delete the emptied one).

## Tests

Extra-surname pair and homonym pair both raised; club-only change raises nothing; decision remembered across `rebuild`; gate 409 then 200; resume after partial review; reversal before and after commit; linked-athlete flag; concurrency (two ingests of the same new rider → one competitor, via the signature unique key); denied paths (parent 403, athlete 403); `city` absent from every other response schema (schema-walk test); `-m mysql` for the unique triple with empty strings.
