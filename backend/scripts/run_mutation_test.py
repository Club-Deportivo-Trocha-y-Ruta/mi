#!/usr/bin/env python3
"""Manual mutation testing runner for critical services.

Applies AST-level mutations to each target module, runs the relevant tests
for each mutant, and reports kill/survive results.
"""
from __future__ import annotations

import ast
import copy
import importlib
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND_DIR = Path("/home/user/mi/backend")
SERVICES_DIR = BACKEND_DIR / "app" / "services"

# Map: module_path -> test_files_to_run
MODULE_TEST_MAP = {
    "app/services/phv.py": [
        "tests/test_phv.py",
        "tests/test_mutation_kills.py",
    ],
    "app/services/category.py": [
        "tests/test_phv.py",
        "tests/test_mutation_kills.py",
    ],
    "app/services/auth.py": [
        "tests/test_security.py",
        "tests/services/test_password_reset_service.py",
    ],
    "app/services/permissions.py": [
        "tests/test_permissions.py",
        "tests/services/test_permissions_scoping.py",
        "tests/test_mutation_kills.py",
    ],
    "app/services/password_reset.py": [
        "tests/services/test_password_reset_service.py",
        "tests/test_password_reset_privacy.py",
        "tests/test_mutation_kills.py",
    ],
    "app/services/privacy.py": [
        "tests/test_privacy.py",
        "tests/test_consent_endpoints.py",
    ],
}


@dataclass
class MutantResult:
    module: str
    mutant_id: int
    description: str
    original_line: str
    mutated_line: str
    status: str  # "killed" | "survived" | "error"
    details: str = ""


def run_tests(test_files: list[str], cwd: Path, timeout: int = 30) -> tuple[bool, str]:
    """Run pytest on the given test files. Returns (killed, output)."""
    cmd = [
        sys.executable, "-m", "pytest", "-x", "-q", "--tb=no",
        "--no-header", "-p", "no:warnings",
    ] + test_files
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        killed = result.returncode != 0
        return killed, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def apply_mutation_to_file(original_path: Path, mutated_source: str) -> None:
    """Overwrite the file with mutated source."""
    original_path.write_text(mutated_source, encoding="utf-8")


def restore_file(original_path: Path, original_source: str) -> None:
    """Restore the original source."""
    original_path.write_text(original_source, encoding="utf-8")


class MutationVisitor(ast.NodeVisitor):
    """Collects potential mutations from an AST."""

    def __init__(self, source: str):
        self.source = source
        self.lines = source.splitlines()
        self.mutations: list[dict] = []

    def _add_mutation(self, lineno: int, col: int, description: str,
                      old_src: str, new_src: str) -> None:
        self.mutations.append({
            "lineno": lineno,
            "col": col,
            "description": description,
            "old_src": old_src,
            "new_src": new_src,
        })


def generate_source_mutations(source: str, module_name: str) -> list[dict]:
    """Generate a focused list of mutations for the given source code.

    Mutations are text-based replacements to keep things simple and fast.
    Focus on the most mutation-testing-relevant patterns:
    - Comparison operator changes (< -> <=, > -> >=, == -> !=, is -> is not)
    - Boolean operator changes (and -> or, or -> and)
    - Arithmetic sign changes
    - Return value changes
    - Boundary constants
    """
    mutations = []
    lines = source.splitlines(keepends=True)

    # Module-specific targeted mutations
    if "phv.py" in module_name:
        mutations.extend(_phv_mutations(source))
    elif "category.py" in module_name:
        mutations.extend(_category_mutations(source))
    elif "auth.py" in module_name:
        mutations.extend(_auth_mutations(source))
    elif "permissions.py" in module_name:
        mutations.extend(_permissions_mutations(source))
    elif "password_reset.py" in module_name:
        mutations.extend(_password_reset_mutations(source))
    elif "privacy.py" in module_name:
        mutations.extend(_privacy_mutations(source))

    return mutations


def _phv_mutations(source: str) -> list[dict]:
    """Mutations for phv.py - focus on boundary conditions and formula signs."""
    mutations = []
    replacements = [
        # Boundary conditions for status classification
        ("mo < -1.0", "mo <= -1.0", "boundary: < to <="),
        ("mo > 1.0", "mo >= 1.0", "boundary: > to >="),
        ("mo < -1.0", "mo > -1.0", "comparison inversion"),
        ("mo > 1.0", "mo < 1.0", "comparison inversion"),
        # Formula constants (critical for correct training prescriptions)
        ("-9.236", "-9.237", "male formula constant"),
        ("-9.376", "-9.377", "female formula constant"),
        ("0.0002708", "0.0002807", "male leg*sitting coefficient"),
        ("-0.001663", "0.001663", "male age*leg sign flip"),
        ("0.007216", "0.007116", "male age*sitting coefficient"),
        ("0.02292", "0.02392", "male weight/height coefficient"),
        ("0.0001882", "0.0001982", "female leg*sitting coefficient"),
        ("0.0022", "0.022", "female age*leg coefficient"),
        ("0.005841", "0.005741", "female age*sitting coefficient"),
        ("-0.002658", "0.002658", "female age*weight sign flip"),
        ("0.07693", "0.07593", "female weight/height coefficient"),
        # age_at_phv formula
        ("age_at_phv = age - mo", "age_at_phv = age + mo", "age_at_phv sign flip"),
        # leg_length formula
        ("standing_height - sitting_height", "standing_height + sitting_height", "leg_length addition"),
        # rounding precision
        ('round(mo, 2)', 'round(mo, 1)', "rounding precision"),
        ('round(age_at_phv, 2)', 'round(age_at_phv, 1)', "rounding precision"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def _category_mutations(source: str) -> list[dict]:
    """Mutations for category.py - boundary years and operators."""
    mutations = []
    replacements = [
        # Birth year boundaries
        ("birth_year <= 1966", "birth_year < 1966", "master_d boundary"),
        ("birth_year <= 1966", "birth_year <= 1967", "master_d boundary off-by-one"),
        ("1967 <= birth_year <= 1971", "1968 <= birth_year <= 1971", "master_c2 start"),
        ("1972 <= birth_year <= 1976", "1973 <= birth_year <= 1976", "master_c1 start"),
        ("1977 <= birth_year <= 1981", "1978 <= birth_year <= 1981", "master_b2 start"),
        ("1982 <= birth_year <= 1986", "1983 <= birth_year <= 1986", "master_b1 start"),
        ("1987 <= birth_year <= 1991", "1988 <= birth_year <= 1991", "master_a start"),
        ("birth_year <= 1991", "birth_year < 1991", "female master boundary"),
        ("birth_year <= 2007", "birth_year < 2007", "elite boundary"),
        ("birth_year <= 2007", "birth_year <= 2008", "elite boundary off-by-one"),
        ("2008 <= birth_year <= 2009", "2009 <= birth_year <= 2009", "junior start"),
        ("2010 <= birth_year <= 2011", "2011 <= birth_year <= 2011", "pre-juve-b start"),
        ("2012 <= birth_year <= 2013", "2013 <= birth_year <= 2013", "pre-juve-a start"),
        ("2014 <= birth_year <= 2015", "2015 <= birth_year <= 2015", "infantil-b start"),
        ("2016 <= birth_year <= 2017", "2017 <= birth_year <= 2017", "infantil-a start"),
        ("2018 <= birth_year <= 2019", "2019 <= birth_year <= 2019", "pre-inf-b start"),
        ("2020 <= birth_year <= 2021", "2021 <= birth_year <= 2021", "pre-inf-a start"),
        # sex checks
        ('sex == "M"', 'sex == "F"', "sex M/F swap in masters"),
        # Age decimal formula
        ("delta.days / 365.25", "delta.days / 365.0", "divisor change"),
        ("delta.days / 365.25", "delta.days * 365.25", "operation change"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def _auth_mutations(source: str) -> list[dict]:
    """Mutations for auth.py - token types, expiry, algorithm."""
    mutations = []
    replacements = [
        # Token type strings
        ('"type": "access"', '"type": "refresh"', "token type swap access->refresh"),
        ('"type": "refresh"', '"type": "access"', "token type swap refresh->access"),
        # JWT algorithm
        ('algorithms=[settings.jwt_algorithm]', 'algorithms=["HS512"]', "algorithm mismatch"),
        # Password operations
        ('bcrypt.checkpw(plain.encode(), hashed.encode())', 'bcrypt.checkpw(hashed.encode(), plain.encode())', "bcrypt arg swap"),
        # Expiry direction
        ('timedelta(minutes=settings.jwt_access_token_expire_minutes)', 'timedelta(minutes=-settings.jwt_access_token_expire_minutes)', "expiry negation"),
        ('timedelta(days=settings.jwt_refresh_token_expire_days)', 'timedelta(days=-settings.jwt_refresh_token_expire_days)', "expiry negation"),
        # Key usage
        ('settings.jwt_secret_key, algorithm=settings.jwt_algorithm', '"wrong-key", algorithm=settings.jwt_algorithm', "wrong key in decode"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def _permissions_mutations(source: str) -> list[dict]:
    """Mutations for permissions.py - role checks, boolean returns."""
    mutations = []
    replacements = [
        # Role checks
        ('user.role == UserRole.admin', 'user.role == UserRole.coach', "admin->coach role check"),
        ('user.role == UserRole.coach', 'user.role == UserRole.admin', "coach->admin role check"),
        ('user.role == UserRole.parent', 'user.role == UserRole.coach', "parent->coach role check"),
        # Set membership
        ('{UserRole.admin, UserRole.coach}', '{UserRole.admin}', "remove coach from allowed set"),
        ('{UserRole.admin, UserRole.coach}', '{UserRole.coach}', "remove admin from allowed set"),
        # Boolean returns
        ('return True', 'return False', "flip return True"),
        ('return False', 'return True', "flip return False"),
        # None vs set
        ('return None', 'return set()', "None -> empty set"),
        # Intersection check
        ('athlete_ids & tagged', 'athlete_ids | tagged', "intersection -> union"),
        # deleted_at check
        ('m.deleted_at is not None', 'm.deleted_at is None', "deleted_at inversion"),
        # Individual report flag
        ('return not individual', 'return individual', "individual flag inversion"),
        # raise HTTPException status codes
        ('HTTP_403_FORBIDDEN', 'HTTP_404_NOT_FOUND', "403 -> 404"),
        # in operator
        ('user_role not in allowed_roles', 'user_role in allowed_roles', "not-in flip"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def _password_reset_mutations(source: str) -> list[dict]:
    """Mutations for password_reset.py - token validation, rate limiting."""
    mutations = []
    replacements = [
        # Token hashing
        ('hashlib.sha256(raw_token.encode()).hexdigest()', 'hashlib.md5(raw_token.encode()).hexdigest()', "sha256 -> md5"),
        # Conditions for returning None
        ('not user.is_active', 'user.is_active', "is_active flip"),
        ('not user.can_login', 'user.can_login', "can_login flip"),
        ('not user.hashed_password', 'user.hashed_password', "hashed_password flip"),
        # Rate limit comparison
        ('recent_count >= settings.password_reset_max_per_window', 'recent_count > settings.password_reset_max_per_window', "rate limit >= to >"),
        ('recent_count >= settings.password_reset_max_per_window', 'recent_count <= settings.password_reset_max_per_window', "rate limit inversion"),
        # Token expiry check
        ('row.used_at is not None', 'row.used_at is None', "used_at inversion"),
        ('_as_utc(row.expires_at) < _now()', '_as_utc(row.expires_at) > _now()', "expires comparison flip"),
        # URL token inclusion
        ('f"{settings.frontend_base_url}/restablecer-contrasena?token={raw_token}"',
         'f"{settings.frontend_base_url}/restablecer-contrasena"',
         "token omitted from URL"),
        # Timezone handling
        ('value.replace(tzinfo=timezone.utc)', 'value', "timezone stripping"),
        # HTTP status codes
        ('HTTP_404_NOT_FOUND', 'HTTP_410_GONE', "404 -> 410"),
        ('HTTP_410_GONE', 'HTTP_404_NOT_FOUND', "410 -> 404"),
        # window calculation
        ('timedelta(minutes=settings.password_reset_window_minutes)', 'timedelta(hours=settings.password_reset_window_minutes)', "minutes -> hours"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def _privacy_mutations(source: str) -> list[dict]:
    """Mutations for privacy.py - consent checks, append-only logic."""
    mutations = []
    replacements = [
        # Policy ordering
        ('.order_by(PrivacyPolicy.effective_date.desc())', '.order_by(PrivacyPolicy.effective_date.asc())', "desc -> asc policy order"),
        # Consent ordering
        ('.order_by(ParentalConsent.consented_at.desc())', '.order_by(ParentalConsent.consented_at.asc())', "desc -> asc consent order"),
        # withdrawn_at check
        ('ParentalConsent.withdrawn_at.is_(None)', 'ParentalConsent.withdrawn_at.is_not(None)', "withdrawn_at inversion"),
        # third_party_sharing check
        ('ParentalConsent.third_party_sharing.is_(True)', 'ParentalConsent.third_party_sharing.is_(False)', "third_party_sharing flip"),
        # Parent check: no parents -> return True
        ('if not parent_ids:', 'if parent_ids:', "parent_ids check inversion"),
        ('return True', 'return False', "flip return True (no parents case)"),
        # Consent existence check
        ('is not None', 'is None', "is not None -> is None"),
        # HTTP status codes
        ('HTTP_503_SERVICE_UNAVAILABLE', 'HTTP_404_NOT_FOUND', "503 -> 404"),
        ('HTTP_400_BAD_REQUEST', 'HTTP_404_NOT_FOUND', "400 -> 404"),
        ('HTTP_403_FORBIDDEN', 'HTTP_404_NOT_FOUND', "403 -> 404"),
        ('HTTP_404_NOT_FOUND', 'HTTP_403_FORBIDDEN', "404 -> 403"),
        ('HTTP_409_CONFLICT', 'HTTP_400_BAD_REQUEST', "409 -> 400"),
        # training_tracking always False
        ('training_tracking=False', 'training_tracking=True', "training_tracking flip"),
        # append-only: superseded marking
        ('previous.withdrawn_at = now_utc', 'pass  # skipping previous.withdrawn_at', "skip withdrawn_at update"),
    ]
    for old, new, desc in replacements:
        if old in source:
            mutations.append({"old": old, "new": new, "description": desc})
    return mutations


def run_module_mutations(module_rel_path: str, test_files: list[str]) -> list[MutantResult]:
    """Run mutations for a single module and return results."""
    module_path = BACKEND_DIR / module_rel_path
    original_source = module_path.read_text(encoding="utf-8")
    mutations = generate_source_mutations(original_source, module_rel_path)

    print(f"\n{'='*70}")
    print(f"Module: {module_rel_path}")
    print(f"Tests:  {', '.join(test_files)}")
    print(f"Total mutants: {len(mutations)}")
    print(f"{'='*70}")

    results = []

    for i, mutation in enumerate(mutations):
        old_text = mutation["old"]
        new_text = mutation["new"]
        description = mutation["description"]

        mutated_source = original_source.replace(old_text, new_text, 1)
        if mutated_source == original_source:
            print(f"  [{i+1}/{len(mutations)}] SKIP (no change): {description}")
            continue

        # Apply mutation
        apply_mutation_to_file(module_path, mutated_source)

        try:
            # Run tests
            killed, output = run_tests(test_files, BACKEND_DIR)
            status = "killed" if killed else "survived"
            symbol = "K" if killed else "S"
            print(f"  [{i+1}/{len(mutations)}] {symbol} {description}")
            if not killed:
                print(f"      OLD: {old_text!r}")
                print(f"      NEW: {new_text!r}")
        except Exception as e:
            status = "error"
            output = str(e)
            print(f"  [{i+1}/{len(mutations)}] ERROR: {description}: {e}")
        finally:
            restore_file(module_path, original_source)

        results.append(MutantResult(
            module=module_rel_path,
            mutant_id=i + 1,
            description=description,
            original_line=old_text,
            mutated_line=new_text,
            status=status,
            details=output[-200:] if output else "",
        ))

    return results


def main():
    all_results: dict[str, list[MutantResult]] = {}

    for module_path, test_files in MODULE_TEST_MAP.items():
        # Check that the module exists
        if not (BACKEND_DIR / module_path).exists():
            print(f"SKIP (not found): {module_path}")
            continue
        results = run_module_mutations(module_path, test_files)
        all_results[module_path] = results

    print("\n" + "="*70)
    print("MUTATION TESTING SUMMARY")
    print("="*70)

    grand_total = 0
    grand_killed = 0
    surviving_mutants = []

    for module, results in all_results.items():
        killed = sum(1 for r in results if r.status == "killed")
        survived = sum(1 for r in results if r.status == "survived")
        errors = sum(1 for r in results if r.status == "error")
        total = len(results)
        score = f"{killed/total*100:.1f}%" if total else "N/A"

        print(f"\n{module}")
        print(f"  Total: {total}, Killed: {killed}, Survived: {survived}, Errors: {errors}")
        print(f"  Mutation score: {score}")

        grand_total += total
        grand_killed += killed

        for r in results:
            if r.status == "survived":
                surviving_mutants.append(r)

    if grand_total:
        print(f"\nOVERALL: {grand_killed}/{grand_total} = {grand_killed/grand_total*100:.1f}%")

    if surviving_mutants:
        print("\n" + "="*70)
        print("SURVIVING MUTANTS (require test strengthening)")
        print("="*70)
        for r in surviving_mutants:
            print(f"\n  Module:  {r.module}")
            print(f"  ID:      {r.mutant_id}")
            print(f"  Desc:    {r.description}")
            print(f"  OLD:     {r.original_line!r}")
            print(f"  NEW:     {r.mutated_line!r}")


if __name__ == "__main__":
    main()
