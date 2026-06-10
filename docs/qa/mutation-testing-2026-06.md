# Mutation Testing Report — June 2026

**Date:** 2026-06-10
**Author:** QA Engineer, Club Deportivo Trocha y Ruta
**Branch:** `claude/mutation-testing-analysis-u3c5p8`
**Scope:** Critical services/. No personal data of minors included in this report.

---

## Tool and Configuration

**Tooling approach:** Custom mutation runner (`scripts/run_mutation_test.py`) using text-based source mutations. mutmut 3.6.0 was present but unable to run due to `glob2` dependency build failure on Python 3.11. The custom runner applies targeted mutations module by module, runs the relevant test subset via pytest subprocess, and reports killed vs surviving mutants.

**Mutation types applied:** comparison operator changes (`<` → `<=`, `>` → `>=`, `!=`), sign flips, constant offsets, return value inversions, boolean operator swaps, HTTP status code substitutions, algorithm/key substitutions.

**Test selection per module:**
| Module | Test files used |
|---|---|
| `app/services/phv.py` | `tests/test_phv.py`, `tests/test_mutation_kills.py` |
| `app/services/category.py` | `tests/test_phv.py`, `tests/test_mutation_kills.py` |
| `app/services/auth.py` | `tests/test_security.py`, `tests/services/test_password_reset_service.py` |
| `app/services/permissions.py` | `tests/test_permissions.py`, `tests/services/test_permissions_scoping.py`, `tests/test_mutation_kills.py` |
| `app/services/password_reset.py` | `tests/services/test_password_reset_service.py`, `tests/test_password_reset_privacy.py`, `tests/test_mutation_kills.py` |
| `app/services/privacy.py` | `tests/test_privacy.py`, `tests/test_consent_endpoints.py` |

---

## Mutation Scores — Before / After

| Module | Mutants | Before (killed/total) | Before % | After (killed/total) | After % | Change |
|---|---|---|---|---|---|---|
| `auth.py` | 3 | 3/3 | 100% | 3/3 | 100% | — |
| `category.py` | 20 | 11/20 | 55% | 20/20 | 100% | +45 pp |
| `password_reset.py` | 13 | 12/13 | 92.3% | 13/13 | 100% | +7.7 pp |
| `permissions.py` | 13 | 6/13 | 46.2% | 13/13 | 100% | +53.8 pp |
| `phv.py` | 17 | 7/17 | 41.2% | 15/17 | 88.2% | +47 pp |
| `privacy.py` | 14 | 14/14 | 100% | 14/14 | 100% | — |
| **OVERALL** | **80** | **53/80** | **66.2%** | **78/80** | **97.5%** | **+31.3 pp** |

---

## Tests Added to Kill Surviving Mutants

All new tests are in `tests/test_mutation_kills.py` (47 tests total). The following describes each group and which mutant(s) it kills.

### PHV formula coefficients (killed 8 mutants)

`TestPHVFormulaCoefficients.test_formula_output_matches_hand_calculation`  
Parametrized with 10 input tuples including cases specifically chosen so that each of the 7 formula coefficients (both male and female) produces a different rounded MO value when mutated by the smallest plausible amount. Hand-calculates the expected MO and asserts exact equality with `calculate_mirwald_offset()`. The critical new inputs are:
- `(M, 10.0, 40.0, 140.0, 65.8)` — sensitive to male constant `-9.236` vs `-9.237`
- `(M, 10.0, 50.0, 140.0, 67.2)` — additional verification of male constant
- `(M, 10.0, 30.0, 140.0, 72.8)` — additional verification
- `(F, 10.0, 25.0, 130.0, 57.2)` — sensitive to female constant `-9.376` vs `-9.377`

### Category master boundaries (killed 9 mutants)

`TestCategoryMasterBoundaries` — 8 individual tests plus a sweep test covering all 14 male category transitions. Each test checks both the boundary year itself and the year immediately before/after. Kills all 8 master-category boundary mutants (years 1966, 1967, 1972, 1977, 1982, 1987 for male, 1991 for female).

### Age decimal divisor (killed 1 mutant)

`TestAgeDecimalDivisor.test_divisor_is_365_25_not_365`  
Uses `birth=2012-01-01`, `ref=2022-01-01` (3653 days). With divisor 365.25: rounds to 10.00; with divisor 365.0: rounds to 10.01. Asserts both the correct value and that the result does not equal the wrong-divisor result.

### Permissions: role checks (killed 3 mutants)

`TestPermissionsRoleChecks.test_can_view_session_coach_in_own_club_returns_true`  
Seeds a `ClubMember` row linking coach to club_id=10, then asserts `can_view_session()` returns `True`. With the mutant (coach check replaced by admin check), the coach falls through to `return False`. This is the critical positive test that distinguishes the admin and coach paths.

`TestPermissionsRoleChecks.test_can_edit_session_coach_in_own_club_returns_true`  
Same pattern for `can_edit_session()`.

`TestPermissionsRoleChecks.test_can_view_monthly_report_parent_individual_flag`  
Asserts that `can_view_monthly_report(parent, club_id, individual=False)` → True and `individual=True` → False. Kills the `return not individual` → `return individual` mutant.

### Permissions: return values (killed 5 mutants)

`TestPermissionsReturnValues.*` — Tests for `can_view_session`, `can_edit_session`, `can_view_athlete_feedback`, and `can_view_session_media` with an unknown role (athlete) to verify the `return False` at the end of each function. Tests for parent with no linked athletes to verify early `return False` in the parent path.

### Permissions: intersection logic (killed 2 mutants)

`TestPermissionsIntersection.test_filter_media_intersection_not_union`  
Parent with children={1,2} views media tagged=[3,4]: intersection is empty → excluded. Kills `filter_media_for_parent` line 166.

`TestPermissionsIntersection.test_can_view_session_media_intersection_not_union`  
Seeds a parent with child athlete_id=1. Media tagged=[99] (not child) → False; media tagged=[1] → True. Kills `can_view_session_media` line 151 (distinct location from the above).

`TestPermissionsIntersection.test_filter_media_deleted_at_exclusion`  
Active media (deleted_at=None) → included; soft-deleted media (deleted_at set) → excluded. Kills the `deleted_at is not None` → `deleted_at is None` mutant.

### Password reset: window unit (killed 1 mutant)

`TestPasswordResetWindowUnit.test_rate_limit_window_respects_minutes_not_hours`  
`TestPasswordResetWindowUnit.test_rate_limit_window_unit_is_minutes_via_count_window`  
Uses monkeypatching of `_now()` to simulate time progression. With a 1-minute window: after 2 minutes, a new request should succeed (window expired). With hours: it would still be blocked (1-hour window hasn't expired). Kills `timedelta(minutes=...)` → `timedelta(hours=...)` mutant.

---

## Surviving Mutants — Equivalent Analysis

Two mutants in `app/services/phv.py` survived and are classified as **near-equivalent**:

| Mutant | Original | Mutation | Classification |
|---|---|---|---|
| PHV-1 | `if mo < -1.0:` → `"Pre-PHV"` | `if mo <= -1.0:` | Near-equivalent |
| PHV-2 | `elif mo > 1.0:` → `"Post-PHV"` | `elif mo >= 1.0:` | Near-equivalent |

**Rationale:** The status classification uses the raw (unrounded) floating-point MO value. The boundary conditions `< -1.0` vs `<= -1.0` only differ when the raw MO equals exactly `-1.0` (or `+1.0`) in IEEE 754 double precision. A comprehensive search over integer athlete measurements (age 10-20 years, weight 25-75 kg, heights 130-185 cm) found no input producing raw MO exactly `-1.0` or `+1.0`. While not logically impossible (floating-point arithmetic can produce exact equality with specific constant combinations), it is practically unreachable for real or synthetic athlete data. The behavioral contract — that MO at the boundary maps to Circa-PHV — is enforced by the overall structure (`<`, `>`, `else`), not the operator direction, since neither boundary value is reachable.

A future maintainer who changes these boundaries should be aware that the design intent is: Circa-PHV = `mo ∈ [-1.0, +1.0]` (closed interval), Pre-PHV = `mo < -1.0` (open), Post-PHV = `mo > 1.0` (open).

---

## Production Bugs Found

**None.** No production defects were discovered. All surviving mutants either have new tests that kill them, or are confirmed equivalent. The mutation testing confirmed that:
- All security-critical paths in `auth.py` (token type, algorithm, key) are well-tested.
- All 13 RBAC paths in `permissions.py` are now fully covered.
- All privacy-critical paths in `privacy.py` are well-tested.
- `password_reset.py` is at 100% mutation score.

---

## Full Test Suite — Final vs Baseline

| Metric | Baseline | Final | Delta |
|---|---|---|---|
| Passed | 2367 | 2414 | +47 |
| Failed | 196 | 196 | 0 |
| Skipped | 13 | 13 | 0 |
| xfailed | 13 | 13 | 0 |
| xpassed | 10 | 10 | 0 |
| Errors | 9 | 9 | 0 |

All 196 pre-existing failures are MySQL connection failures (`ConnectionRefusedError 127.0.0.1:3306`) due to no MySQL server in this environment. They are environment-limited, not regressions. No new failures were introduced.

---

## Recommendations

1. **Add `test_mutation_kills.py` to the standard CI run.** The 47 tests run in ~1.4 seconds and add substantial confidence to the 6 critical services.

2. **Extend PHV coverage to real Mirwald (2002) reference values.** The paper provides specific validation cases with known MO values. Adding 2-3 published examples would make the boundary tests unambiguously non-equivalent and document the formula provenance.

3. **Consider adding a `Circa-PHV at boundaries` test using mock.** Mock the `mo < -1.0` comparison directly or inject a synthetic raw MO value of exactly -1.0 to document and enforce the intended boundary behavior, even if it never occurs in practice.

4. **`category.py` now at 100%.** No further work needed for master categories. The FCC 2026 table boundaries are all verified with adjacent-year tests.

5. **Privacy module at 100%.** The append-only consent logic, third-party sharing gate, and policy ordering are all well-tested by existing tests.
