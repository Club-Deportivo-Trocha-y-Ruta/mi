"""T011 — Backfill idempotency: layout_json column (feature 019 Phase A).

Asserts:
  1. After applying the backfill data step once, every slug present in
     GYMKHANA_LAYOUT_BACKFILL has a non-NULL layout_json.
  2. Applying the backfill a *second time* yields byte-identical layout_json
     values (idempotent — WHERE layout_json IS NULL guard works).
  3. Rows that already have a hand-set layout_json are NOT overwritten by the
     backfill (only-where-NULL semantics).
  4. layout_ascii and layout_alt columns are untouched by both passes (the
     backfill only touches layout_json).

Uses aiosqlite in-memory (project convention) — no MySQL, no live network.
The backfill SQL is replicated directly here (same WHERE slug=:slug AND
layout_json IS NULL pattern) so we test the logic, not Alembic internals.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.data.technique_catalog import GYMKHANA_LAYOUT_BACKFILL
from app.models import Base

# ---------------------------------------------------------------------------
# Engine / session fixtures (scoped to this module — no dependency on the
# technique conftest so this test file is self-contained)
# ---------------------------------------------------------------------------

# Only create the tables this test touches.
_TABLES = ("technique_exercises",)


@pytest_asyncio.fixture
async def engine():
    """In-memory aiosqlite engine with only the technique_exercises table."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_rows(db: AsyncSession, rows: list[dict]) -> None:
    """Insert minimal technique_exercises rows (only columns needed for the test)."""
    for row in rows:
        await db.execute(
            text(
                "INSERT INTO technique_exercises "
                "(slug, name, summary, how_to, difficulty, is_game, is_gymkhana, "
                " is_seeded, is_hidden, created_at, updated_at, "
                " layout_ascii, layout_alt, layout_json) "
                "VALUES "
                "(:slug, :name, :summary, :how_to, :difficulty, :is_game, :is_gymkhana, "
                " :is_seeded, :is_hidden, :created_at, :updated_at, "
                " :layout_ascii, :layout_alt, :layout_json)"
            ),
            row,
        )
    await db.commit()


def _base_row(slug: str, **overrides) -> dict:
    """Return a minimal row dict for ``technique_exercises``."""
    return {
        "slug": slug,
        "name": f"Ejercicio ficticio {slug}",
        "summary": "Resumen ficticio para prueba.",
        "how_to": "Dilo / Muéstralo / Háganlo / Revísenlo (ficticio).",
        "difficulty": "facil",
        "is_game": 0,
        "is_gymkhana": 1,
        "is_seeded": 1,
        "is_hidden": 0,
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:00:00",
        "layout_ascii": "ASCII ficticio",
        "layout_alt": "Descripción accesible ficticia.",
        "layout_json": None,  # starts NULL — simulates a pre-migration row
        **overrides,
    }


async def _apply_backfill(db: AsyncSession) -> None:
    """Run the same UPDATE logic as the Alembic migration's data step."""
    for slug, layout in GYMKHANA_LAYOUT_BACKFILL.items():
        await db.execute(
            text(
                "UPDATE technique_exercises"
                " SET layout_json = :layout_json"
                " WHERE slug = :slug AND layout_json IS NULL"
            ),
            {
                "layout_json": json.dumps(layout),
                "slug": slug,
            },
        )
    await db.commit()


async def _fetch_layout_json(db: AsyncSession, slug: str) -> str | None:
    """Return the raw layout_json text stored for *slug* (or None)."""
    result = await db.execute(
        text("SELECT layout_json FROM technique_exercises WHERE slug = :slug"),
        {"slug": slug},
    )
    row = result.fetchone()
    return row[0] if row else None


async def _fetch_layout_ascii(db: AsyncSession, slug: str) -> str | None:
    result = await db.execute(
        text("SELECT layout_ascii FROM technique_exercises WHERE slug = :slug"),
        {"slug": slug},
    )
    row = result.fetchone()
    return row[0] if row else None


async def _fetch_layout_alt(db: AsyncSession, slug: str) -> str | None:
    result = await db.execute(
        text("SELECT layout_alt FROM technique_exercises WHERE slug = :slug"),
        {"slug": slug},
    )
    row = result.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_populates_all_slugs(db: AsyncSession) -> None:
    """After one backfill pass every slug in GYMKHANA_LAYOUT_BACKFILL has a
    non-NULL layout_json."""
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())
    assert slugs, "GYMKHANA_LAYOUT_BACKFILL must not be empty"

    rows = [_base_row(slug) for slug in slugs]
    await _insert_rows(db, rows)

    await _apply_backfill(db)

    for slug in slugs:
        raw = await _fetch_layout_json(db, slug)
        assert raw is not None, f"layout_json should be non-NULL after backfill (slug={slug!r})"


@pytest.mark.asyncio
async def test_backfill_idempotent(db: AsyncSession) -> None:
    """Applying the backfill twice yields byte-identical layout_json values.

    The WHERE layout_json IS NULL guard means the second pass is a no-op for
    rows already populated; the stored value must be identical to what was
    written in the first pass.
    """
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())
    rows = [_base_row(slug) for slug in slugs]
    await _insert_rows(db, rows)

    # First pass
    await _apply_backfill(db)
    after_first = {slug: await _fetch_layout_json(db, slug) for slug in slugs}

    # Second pass (idempotency check)
    await _apply_backfill(db)
    after_second = {slug: await _fetch_layout_json(db, slug) for slug in slugs}

    for slug in slugs:
        assert after_first[slug] is not None, f"First pass must set layout_json (slug={slug!r})"
        assert after_first[slug] == after_second[slug], (
            f"Second backfill pass must not change layout_json (slug={slug!r}). "
            f"First=\n{after_first[slug]}\nSecond=\n{after_second[slug]}"
        )


@pytest.mark.asyncio
async def test_backfill_does_not_overwrite_existing_layout_json(db: AsyncSession) -> None:
    """Rows that already have layout_json set are NOT overwritten by the backfill.

    Simulates a row that was manually curated before the migration ran (or
    re-running the migration after partial success).  The hand-set value must
    survive both backfill passes unchanged.
    """
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())
    assert slugs, "Need at least one slug for this test"

    sentinel_slug = slugs[0]
    sentinel_layout = json.dumps({"width": 999, "height": 999, "elements": []})

    rows = []
    for slug in slugs:
        if slug == sentinel_slug:
            # Pre-set layout_json — simulates an already-curated row
            rows.append(_base_row(slug, layout_json=sentinel_layout))
        else:
            rows.append(_base_row(slug))
    await _insert_rows(db, rows)

    # Apply backfill (once is enough — idempotency already tested above)
    await _apply_backfill(db)

    # The sentinel row must retain its original hand-set value
    stored = await _fetch_layout_json(db, sentinel_slug)
    assert stored == sentinel_layout, (
        f"Backfill must NOT overwrite an existing layout_json (slug={sentinel_slug!r}). "
        f"Expected sentinel value, got: {stored!r}"
    )

    # Other rows (with NULL before backfill) must now have the correct backfill value
    for slug in slugs[1:]:
        raw = await _fetch_layout_json(db, slug)
        expected = json.dumps(GYMKHANA_LAYOUT_BACKFILL[slug])
        assert raw == expected, (
            f"Non-sentinel row must be populated by backfill (slug={slug!r}). "
            f"Expected: {expected!r}  Got: {raw!r}"
        )


@pytest.mark.asyncio
async def test_backfill_does_not_touch_layout_ascii_or_layout_alt(db: AsyncSession) -> None:
    """The backfill UPDATE touches only layout_json; layout_ascii and layout_alt
    must remain exactly as inserted (their fallback role must be preserved)."""
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())

    sentinel_ascii = "SENTINEL_ASCII_VALUE"
    sentinel_alt = "SENTINEL_ALT_VALUE"

    rows = [
        _base_row(slug, layout_ascii=sentinel_ascii, layout_alt=sentinel_alt)
        for slug in slugs
    ]
    await _insert_rows(db, rows)

    # Two backfill passes (belt-and-suspenders)
    await _apply_backfill(db)
    await _apply_backfill(db)

    for slug in slugs:
        ascii_val = await _fetch_layout_ascii(db, slug)
        alt_val = await _fetch_layout_alt(db, slug)
        assert ascii_val == sentinel_ascii, (
            f"layout_ascii must not be changed by backfill (slug={slug!r}). "
            f"Got: {ascii_val!r}"
        )
        assert alt_val == sentinel_alt, (
            f"layout_alt must not be changed by backfill (slug={slug!r}). "
            f"Got: {alt_val!r}"
        )


@pytest.mark.asyncio
async def test_backfill_skips_slugs_not_in_db(db: AsyncSession) -> None:
    """The backfill is a no-op for slugs that do not exist in the DB (e.g. a
    partially seeded environment).  It must not raise and must leave the table
    in a consistent state for the rows that *do* exist."""
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())
    # Insert only the first two slugs — the rest are absent from the DB
    subset = slugs[:2]
    rows = [_base_row(slug) for slug in subset]
    await _insert_rows(db, rows)

    # Must not raise even though most slugs won't match any row
    await _apply_backfill(db)

    for slug in subset:
        raw = await _fetch_layout_json(db, slug)
        assert raw is not None, (
            f"Present slug must be populated even when other slugs are absent "
            f"(slug={slug!r})"
        )


@pytest.mark.asyncio
async def test_backfill_json_round_trips_correctly(db: AsyncSession) -> None:
    """Each backfill value is valid JSON that round-trips through parse/dump
    without mutation.  Verifies the stored text is the canonical serialisation
    of the expected GymkhanaLayout dict."""
    slugs = list(GYMKHANA_LAYOUT_BACKFILL.keys())
    rows = [_base_row(slug) for slug in slugs]
    await _insert_rows(db, rows)

    await _apply_backfill(db)

    for slug, expected_layout in GYMKHANA_LAYOUT_BACKFILL.items():
        raw = await _fetch_layout_json(db, slug)
        assert raw is not None, f"Expected non-NULL after backfill (slug={slug!r})"

        # Parse the stored JSON and compare structurally (not string-equality,
        # because SQLite may preserve the exact bytes or not)
        parsed = json.loads(raw)
        assert parsed == expected_layout, (
            f"Round-trip mismatch for slug={slug!r}:\n"
            f"  expected: {expected_layout}\n"
            f"  got:      {parsed}"
        )

        # Required top-level fields present and valid
        assert parsed["width"] > 0, f"width must be >0 (slug={slug!r})"
        assert parsed["height"] > 0, f"height must be >0 (slug={slug!r})"
        assert isinstance(parsed["elements"], list), (
            f"elements must be a list (slug={slug!r})"
        )
