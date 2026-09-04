import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base

# Fixtures de escenarios "comparison groups" (feature 039) — registradas como
# plugin para estar disponibles en toda la suite sin import explícito, igual
# que cualquier fixture de un conftest.py normal.
pytest_plugins = ["tests.fixtures.race_groups"]


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# MySQL opt-in fixtures (marker: mysql)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def mysql_engine():
    """Session-scoped async engine for the real MySQL 8.4 test database.

    Reads TEST_DATABASE_URL from the environment.  Skips the entire session
    if the variable is absent or does not use the ``mysql+aiomysql://`` driver.
    Refuses (hard fail) to run against a database whose name does not end with
    ``_test`` — safety guard against accidentally wiping dev/prod data.

    Usage::

        TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
            pytest -m mysql -q
    """
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url or not url.startswith("mysql+aiomysql://"):
        pytest.skip("TEST_DATABASE_URL (mysql+aiomysql://) no configurada — saltando lane mysql")

    # Safety: database name must end with _test
    db_name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not db_name.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL apunta a la base '{db_name}', que no termina en '_test'. "
            "Abortando para proteger datos de dev/prod."
        )

    engine = create_async_engine(url, future=True, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Drop all tables by fetching their names from MySQL and dropping each one
    # with FK checks disabled.  Base.metadata.drop_all has a Python-level
    # topological sort that raises on self-referential FKs (e.g.
    # athlete_ai_insights.superseded_by_insight_id → itself), so we bypass it.
    async with engine.begin() as conn:
        await conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 0"))
        result = await conn.execute(sa_text("SHOW TABLES"))
        table_names = [row[0] for row in result.fetchall()]
        for tbl in table_names:
            await conn.execute(sa_text(f"DROP TABLE IF EXISTS `{tbl}`"))
        await conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 1"))
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def mysql_session(mysql_engine):
    """Session-scoped AsyncSession backed by the real MySQL engine.

    All mysql-marked tests share the same session within a pytest session.
    Tests must use unique IDs to avoid constraint collisions.  The session
    is NOT rolled back between tests; data persists within the test run but
    is wiped when the engine fixture drops all tables at teardown.

    Note: function-scope with rollback is NOT used here because the async
    engine is session-scoped (single event loop) and a per-function teardown
    rollback would attempt to use the session loop from a different context,
    causing 'Task attached to a different loop' errors with aiomysql.
    """
    factory = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
