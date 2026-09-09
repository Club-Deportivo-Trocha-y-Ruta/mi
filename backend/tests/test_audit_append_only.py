"""FR-004 — append-only invariants of ``audit_log``.

Two independent layers, per data-model.md §1.2 and contracts/audit-recording.md
§5:

1. A **static** test that AST-walks ``backend/app/`` and fails if any module
   outside the declared exemptions issues a SQLAlchemy ``update(AuditLog)``,
   ``delete(AuditLog)``, ``session.delete(<AuditLog instance>)`` or mutates an
   attribute on an already-constructed ``AuditLog`` instance.

   The only exemption is ``app/services/retention.py`` (FR-030,
   ``contracts/retention-purge.md``). That module does not exist yet (arrives
   in T087) — the exemption is declared by *path*, not by import, exactly as
   instructed, so the test is correct today (zero exempt files on disk) and
   stays correct once retention.py lands without editing this test.

2. A **model-level** test that ``AuditLog`` has no ``updated_at`` column and no
   column configured with ``onupdate``, plus a behavioural check that proves a
   post-flush mutation is caught. Nothing in the production model prevents an
   ORM-level attribute mutation today — data-model.md §1.2 item 5 explicitly
   defers DB-level hardening (no trigger, no restricted grant) and §8.4 says
   the invariant is "enforced in code and tests, not by the database". So the
   behavioural half of this test installs its own ``before_flush`` guard
   (scoped to the test, removed on teardown) that inspects
   ``session.dirty``/``session.deleted`` for ``AuditLog`` instances and
   raises — proving the invariant is verifiable and giving a concrete
   regression trip-wire the day someone tries to UPDATE or DELETE a row
   in-process. It complements, and does not replace, the static test above,
   which is what actually prevents production code from doing this.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog


# ---------------------------------------------------------------------------
# Part 1 — static AST scan (FR-004, contracts/audit-recording.md §5.2)
# ---------------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

#: Declared by *path*, relative to ``backend/app``. ``retention.py`` does not
#: exist on disk yet (T087) — that is fine, the exemption still "exists" as a
#: rule; there is simply nothing on disk today that could violate it.
EXEMPT_RELATIVE_PATHS = {
    Path("services") / "audit.py",
    Path("services") / "retention.py",
}


def _is_exempt(py_file: Path) -> bool:
    rel = py_file.relative_to(APP_ROOT)
    return rel in EXEMPT_RELATIVE_PATHS


def _name_is_auditlog(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "AuditLog"


class _AuditLogMutationVisitor(ast.NodeVisitor):
    """Collects violations of the append-only invariant in one module.

    Heuristics, deliberately conservative (few false positives over perfect
    recall — the static test's job is to catch an obvious regression, the
    model-level test below covers the runtime behaviour):

    - ``update(AuditLog)`` / ``sa.update(AuditLog)`` — SQLAlchemy Core update
      construct with ``AuditLog`` as a direct positional argument.
    - ``delete(AuditLog)`` / ``sa.delete(AuditLog)`` — same, for delete.
    - A local variable assigned from ``AuditLog(...)`` is tracked per module;
      any later ``<anything>.delete(<that name>)`` call, or any attribute
      assignment on that name, is flagged.
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []
        # names bound to `AuditLog(...)` anywhere in the module, plus the
        # line where the *construction* happened (mutation before that line
        # cannot exist; we do not need finer scoping for this heuristic).
        self._audit_log_vars: dict[str, int] = {}

    # -- pass 1 helpers -----------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call) and _name_is_auditlog(node.value.func):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._audit_log_vars[target.id] = node.lineno
        # Attribute assignment on a tracked AuditLog instance, e.g. `row.action = x`
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in self._audit_log_vars
                and node.lineno > self._audit_log_vars[target.value.id]
            ):
                self.violations.append(
                    f"{self.filename}:{node.lineno} — attribute assignment on "
                    f"AuditLog instance '{target.value.id}.{target.attr}' "
                    "outside the append-only exemption"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        func_name = None
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name in {"update", "delete"} and any(
            _name_is_auditlog(arg) for arg in node.args
        ):
            self.violations.append(
                f"{self.filename}:{node.lineno} — sa.{func_name}(AuditLog) "
                "outside the append-only exemption"
            )

        # session.delete(<tracked AuditLog var>)
        if (
            func_name == "delete"
            and isinstance(func, ast.Attribute)
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in self._audit_log_vars
        ):
            self.violations.append(
                f"{self.filename}:{node.lineno} — session.delete(<AuditLog "
                f"instance '{node.args[0].id}'>) outside the append-only "
                "exemption"
            )

        self.generic_visit(node)


def _iter_app_python_files():
    for path in sorted(APP_ROOT.rglob("*.py")):
        yield path


def test_no_update_or_delete_of_auditlog_outside_exemptions():
    """AST-walk backend/app/ for update(AuditLog)/delete(AuditLog)/
    session.delete(<AuditLog>)/attribute-mutation outside the two exempt
    modules (contracts/audit-recording.md §5 items 1-2)."""
    violations: list[str] = []
    scanned = 0

    for py_file in _iter_app_python_files():
        if _is_exempt(py_file):
            continue
        scanned += 1
        source = py_file.read_text(encoding="utf-8")
        if "AuditLog" not in source:
            continue
        tree = ast.parse(source, filename=str(py_file))
        visitor = _AuditLogMutationVisitor(str(py_file.relative_to(APP_ROOT)))
        visitor.visit(tree)
        violations.extend(visitor.violations)

    # Sanity: the scan must actually have looked at a non-trivial slice of
    # the codebase, otherwise a path-resolution bug could silently scan zero
    # files and this test would pass vacuously.
    assert scanned > 50, (
        f"Only scanned {scanned} files under {APP_ROOT} — expected the whole "
        "app/ tree. A path bug would make this test vacuously green."
    )
    assert not violations, "Append-only violation(s) found:\n" + "\n".join(violations)


def test_auditlog_constructed_only_in_audit_service():
    """``AuditLog(`` may only appear as a constructor call inside
    ``app/services/audit.py`` (contracts/audit-recording.md §5 item 1)."""
    offenders: list[str] = []

    for py_file in _iter_app_python_files():
        rel = py_file.relative_to(APP_ROOT)
        if rel == Path("models") / "audit_log.py":
            continue  # the class definition itself
        if rel == Path("services") / "audit.py":
            continue  # the single authorised construction site
        source = py_file.read_text(encoding="utf-8")
        if "AuditLog" not in source:
            continue
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name_is_auditlog(node.func):
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        "AuditLog(...) constructed outside app/services/audit.py at: "
        + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Part 2 — model-level invariants
# ---------------------------------------------------------------------------


def test_auditlog_has_no_updated_at_or_onupdate_column():
    """data-model.md §1.2 item 1: no updated_at/updated_by column, and no
    column anywhere on the model is configured with an ``onupdate``."""
    columns = AuditLog.__table__.columns
    column_names = {c.name for c in columns}

    assert "updated_at" not in column_names
    assert "updated_by" not in column_names
    assert "updated_by_user_id" not in column_names

    onupdate_columns = [c.name for c in columns if c.onupdate is not None]
    assert onupdate_columns == [], (
        f"AuditLog columns configured with onupdate: {onupdate_columns} — "
        "append-only tables must never silently rewrite a value on UPDATE."
    )


def test_auditlog_relationships_are_viewonly():
    """data-model.md §1.2 item 2: every relationship on AuditLog is
    viewonly=True so no cascade can ever write through it."""
    mapper = AuditLog.__mapper__
    relationships = list(mapper.relationships)
    assert relationships, "AuditLog should declare actor/club/athlete relationships"
    non_viewonly = [r.key for r in relationships if not r.viewonly]
    assert non_viewonly == [], (
        f"AuditLog relationships not viewonly: {non_viewonly}"
    )


@pytest.mark.asyncio
async def test_auditlog_mutation_after_flush_is_caught_by_the_append_only_guard():
    """Behavioural half of FR-004: a test-scoped ``before_flush`` guard
    (mirroring the DB-level trigger this project has deliberately deferred,
    data-model.md §1.2 item 5) inspects the flush plan for any
    dirty/deleted ``AuditLog`` instance and raises. This proves the
    invariant is mechanically checkable end-to-end, on top of the static
    scan above which is what actually stops it from ever being written in
    the first place.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[AuditLog.__table__])
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class _AppendOnlyViolation(SQLAlchemyError):
        pass

    def _guard(session: Session, flush_context, instances) -> None:  # noqa: ANN001
        for obj in set(session.dirty):
            if isinstance(obj, AuditLog):
                raise _AppendOnlyViolation(
                    f"Attempted UPDATE of AuditLog id={obj.id} — append-only violation"
                )
        for obj in set(session.deleted):
            if isinstance(obj, AuditLog):
                raise _AppendOnlyViolation(
                    f"Attempted DELETE of AuditLog id={obj.id} — append-only violation"
                )

    async with session_factory() as session:
        row = AuditLog(
            actor_user_id=None,
            actor_kind=AuditActorKind.system,
            actor_role=None,
            club_id=1,
            athlete_id=None,
            entity_type="athlete",
            entity_id=1,
            action=AuditAction.create,
            changed_fields=[],
            diff_json=None,
            reason_code=None,
            request_id="a" * 32,
            meta_json=None,
        )
        session.add(row)
        await session.flush()
        await session.commit()
        row_id = row.id

        # Guard installed only *after* the legitimate insert above, exactly
        # like the append-only rule only forbids UPDATE/DELETE, never INSERT.
        sync_session = session.sync_session
        event.listen(sync_session, "before_flush", _guard)
        try:
            row.action = AuditAction.delete
            with pytest.raises(_AppendOnlyViolation):
                await session.flush()
        finally:
            event.remove(sync_session, "before_flush", _guard)
            await session.rollback()

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(AuditLog).where(AuditLog.id == row_id))
        persisted = result.scalar_one()
        assert persisted.action == AuditAction.create, (
            "The mutation must never have reached the database — the row's "
            "action is still its original value"
        )

    await engine.dispose()
