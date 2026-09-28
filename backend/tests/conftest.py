import os

# Antes de importar la app: un .env local con LANGFUSE_ENABLED=true no debe
# mandar trazas desde la suite.
os.environ["LANGFUSE_ENABLED"] = "false"

# Idem AI_PROVIDER/RACE_AI_PROVIDER: un .env local con un proveedor de costo
# $0 (openai/claude-cli, ver pricing.py) rompe silenciosamente asserts como
# `cost_usd > 0` en tests que no fijan el proveedor explícitamente.
os.environ["AI_PROVIDER"] = "google"
os.environ["RACE_AI_PROVIDER"] = ""
# AI_MODEL es el fallback "legacy" que resolve_app_config() consulta ANTES
# de DEFAULT_MODEL_BY_PROVIDER (app/services/llm/factory.py) — un .env local
# con AI_MODEL="claude-sonnet-5" (para uso diario con AI_PROVIDER=claude-cli)
# se cuela igual bajo el AI_PROVIDER=google forzado arriba y produce un 404
# real contra la API de Google, no un fallback silencioso. Mismo motivo que
# el bloque de arriba, para el modelo en vez del proveedor.
os.environ["AI_MODEL"] = "gemini-3.1-flash-lite"

import importlib.util
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base

# Fixtures de escenarios "comparison groups" (feature 039) — registradas como
# plugin para estar disponibles en toda la suite sin import explícito, igual
# que cualquier fixture de un conftest.py normal.
pytest_plugins = ["tests.fixtures.race_groups", "tests.fixtures.two_coaches"]


# ---------------------------------------------------------------------------
# Hermetic default lane: aiosqlite in-memory DB replacing app.database
# ---------------------------------------------------------------------------
#
# Constitution, Principle II: the default lane is offline. Before this block,
# ``client`` used the real ``get_db`` -> ``app.database.AsyncSessionLocal`` ->
# whatever MySQL ``backend/.env`` pointed to (possibly production). Now:
#
# 1. One aiosqlite in-memory engine (StaticPool: a single shared connection,
#    so every session sees the same data) is built ONCE per pytest session,
#    with the full schema (``create_all``) and the same seed as the dev stack
#    (``scripts.seed.seed`` + the privacy-policy rows inserted by migrations +
#    the growth LMS tables). Session scope mirrors the shared, persistent
#    MySQL the suite used before (timings in the spike report).
# 2. ``app.database.AsyncSessionLocal``/``engine``, the name imported by
#    ``app.dependencies`` and the race-AI ``db_factory`` point to that engine
#    for the whole session: any path opening its own session (background
#    tasks, strava, intervals, race analysis) lands on SQLite, never MySQL.
# 3. Tripwire: the original MySQL engine raises on connect, so a code path
#    that captured it before the patch fails loudly instead of writing to a
#    real database.

_POLICY_MIGRATIONS = (
    (
        "d1e2f3a4b5c6_add_privacy_policies_table_and_consent_fk.py",
        (
            ("v1.0", "2026-04-15", "2026-05-06", "_POLICY_V1_0_HTML", "_HASH_V1_0", None),
            ("v1.1", "2026-05-06", "2026-05-15", "_POLICY_V1_1_HTML", "_HASH_V1_1", "_CHANGELOG_V1_1"),
        ),
    ),
    (
        "a2b3c4d5e6f7_add_policy_v1_2_ai_processing.py",
        (("v1.2", "2026-05-15", None, "_POLICY_V1_2_HTML", "_HASH_V1_2", "_CHANGELOG_V1_2"),),
    ),
)


def _load_migration_module(filename: str) -> Any:
    """Import a migration file only to reuse its constants (policy HTML/hash),
    so the legal text is not duplicated in the conftest."""
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _seed_privacy_policies(session: AsyncSession) -> None:
    """Replicate the rows inserted by migrations d1e2f3a4b5c6 and a2b3c4d5e6f7
    (``create_all`` does not run data migrations)."""
    from app.models.privacy_policy import PrivacyPolicy

    for filename, rows in _POLICY_MIGRATIONS:
        mig = _load_migration_module(filename)
        for version, eff, dep, html_attr, hash_attr, changelog_attr in rows:
            session.add(
                PrivacyPolicy(
                    version=version,
                    effective_date=date.fromisoformat(eff),
                    deprecated_at=date.fromisoformat(dep) if dep else None,
                    title=mig._POLICY_TITLE,
                    content_html=getattr(mig, html_attr),
                    content_hash=getattr(mig, hash_attr),
                    changelog=getattr(mig, changelog_attr) if changelog_attr else None,
                    created_by=None,
                    created_at=datetime.now(UTC),
                )
            )
    await session.flush()


async def _seed_growth_reference(session: AsyncSession) -> None:
    """Same LMS rows as ``python -m app.seed_growth_data`` (``bulk_insert_lms``
    is already dialect-aware), minus the audit row."""
    from app import seed_growth_data as g

    for src in g.CDC_SOURCES:
        rows = g.parse_csv_file(g.DATA_DIR / src["filename"], src["indicator"])
        await g.bulk_insert_lms(session, rows)
    for src in g.WHO_SOURCES:
        rows = g.parse_who_csv_file(g.WHO_DATA_DIR / src["filename"], src["indicator"])
        await g.bulk_insert_lms(session, rows)
    for src in g.FUPRECOL_SOURCES:
        rows = g.parse_fuprecol_csv_file(g.FUPRECOL_DATA_DIR / src["filename"])
        await g.bulk_insert_lms(session, rows)
    await session.flush()


def _new_sqlite_engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _fk_on(dbapi_conn: Any, _record: Any) -> None:
        # MySQL enforces FKs; SQLite only with this PRAGMA (per connection).
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


async def build_seeded_sqlite_engine() -> AsyncEngine:
    """aiosqlite in-memory engine with the full schema + the dev seed."""
    from scripts.seed import seed

    eng = _new_sqlite_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as session:
        await _seed_privacy_policies(session)
        await _seed_growth_reference(session)
        await session.commit()
        await seed(session)  # commits on its own
    return eng


async def clone_sqlite_engine(template: AsyncEngine) -> AsyncEngine:
    """Fresh in-memory copy of ``template`` via SQLite's online backup API
    (~20 ms) — far cheaper than re-running create_all + seed (~1.1 s, mostly
    the four bcrypt hashes of the seed users)."""
    eng = _new_sqlite_engine()
    async with template.connect() as src, eng.connect() as dst:
        src_raw = (await src.get_raw_connection()).driver_connection
        dst_raw = (await dst.get_raw_connection()).driver_connection
        await src_raw.backup(dst_raw)
    return eng


class _AppDbSwap:
    """Point every module-level handle on the app database at ``eng``:
    ``app.database.AsyncSessionLocal``/``engine`` (late ``from app.database
    import AsyncSessionLocal`` in routers/services resolves here), the name
    ``app.dependencies`` imported at load time, and the race-AI db_factory
    (``set_db_factory(AsyncSessionLocal)`` ran in ``app/main.py`` at import)."""

    def __init__(self, eng: AsyncEngine) -> None:
        self.factory = async_sessionmaker(eng, expire_on_commit=False)
        self._eng = eng
        self._saved: tuple[Any, ...] | None = None

    def __enter__(self) -> async_sessionmaker[AsyncSession]:
        import app.database as database_module
        import app.dependencies as dependencies_module
        from app.services.race.ai import db as race_ai_db

        self._saved = (
            database_module.AsyncSessionLocal,
            database_module.engine,
            dependencies_module.AsyncSessionLocal,
            race_ai_db.get_db_factory(),
        )
        database_module.AsyncSessionLocal = self.factory
        database_module.engine = self._eng
        dependencies_module.AsyncSessionLocal = self.factory
        race_ai_db.set_db_factory(self.factory)
        return self.factory

    def __exit__(self, *_exc: object) -> None:
        import app.database as database_module
        import app.dependencies as dependencies_module
        from app.services.race.ai import db as race_ai_db

        assert self._saved is not None
        (
            database_module.AsyncSessionLocal,
            database_module.engine,
            dependencies_module.AsyncSessionLocal,
            previous_race_factory,
        ) = self._saved
        race_ai_db.set_db_factory(previous_race_factory)


def _refuse_real_db_connection(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError(
        "The default pytest lane tried to connect to the MySQL configured in "
        "Settings. Use the hermetic DB (`client` / `hermetic_session_factory`) "
        "or mark the test with @pytest.mark.mysql."
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def hermetic_template_db() -> AsyncIterator[AsyncEngine]:
    """Seeded template DB, built once per session. Also the session-wide
    safety net: every test (with or without ``client``) sees SQLite instead
    of the Settings MySQL, and the real engine refuses to connect."""
    import app.database as database_module

    real_engine = database_module.engine
    event.listen(real_engine.sync_engine, "do_connect", _refuse_real_db_connection)
    template = await build_seeded_sqlite_engine()
    # The safety net points at a scratch copy so stray writes from tests that
    # do not use ``client`` never leak into the template later clones copy.
    scratch = await clone_sqlite_engine(template)
    try:
        with _AppDbSwap(scratch):
            yield template
    finally:
        event.remove(real_engine.sync_engine, "do_connect", _refuse_real_db_connection)
        await scratch.dispose()
        await template.dispose()


@pytest_asyncio.fixture
async def hermetic_session_factory(
    hermetic_template_db: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Fresh, seeded, per-test copy of the template DB, wired into the app.
    Tests may also request it to read/write the same DB the app sees."""
    eng = await clone_sqlite_engine(hermetic_template_db)
    try:
        with _AppDbSwap(eng) as factory:
            yield factory
    finally:
        await eng.dispose()


@pytest.fixture
async def client(
    hermetic_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    from app.dependencies import get_db

    async def _hermetic_get_db() -> AsyncIterator[AsyncSession]:
        # Same semantics as ``app.dependencies.get_db``.
        async with hermetic_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # If a test fixture already overrode get_db (fixture ordering), keep it;
    # only remove what this fixture installed.
    installed = get_db not in app.dependency_overrides
    if installed:
        app.dependency_overrides[get_db] = _hermetic_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        if installed and app.dependency_overrides.get(get_db) is _hermetic_get_db:
            del app.dependency_overrides[get_db]


@pytest.fixture(autouse=True)
def _clear_parsed_rows_caches():
    """Feature 044 (G4 mitigation): ``race_imports`` cachea el parseo crudo
    y las categorías corregidas por ``sha256``/``(sha256, corrections_revision)``
    en dos LRU de proceso (comentario en ``routers/race_imports.py``, antes de
    ``_reload_results_document``).

    Muchos tests de imports reusan placeholders cortos (``sha256="a"``,
    ``"b"``, ...) entre archivos distintos con parseos monkeypatcheados
    diferentes — sin este fixture, un test que corre después de otro con el
    mismo placeholder leería el resultado cacheado del primero en vez de
    llamar a su propio stub. Autouse y global: la caché es un singleton de
    módulo compartido por todo el proceso de pytest, así que se limpia antes
    y después de cada test sin que cada suite tenga que acordarse.
    """
    from app.routers.race_imports import clear_parsed_rows_caches

    clear_parsed_rows_caches()
    yield
    clear_parsed_rows_caches()


# ---------------------------------------------------------------------------
# MySQL opt-in fixtures (marker: mysql)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
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
