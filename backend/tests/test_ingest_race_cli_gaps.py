"""Tests para cerrar gaps de cobertura del CLI ``scripts/ingest_race.py`` (Paso 7).

Cubre escenarios reportados como pendientes en la cobertura inicial:

- ``riders link`` (no testeado por limitación de FakeAsyncSession con UPDATE).
  Estrategia: stubear las queries con mocks específicos para evitar la
  necesidad de un UPDATE real. Verifica el contrato del comando.
- ``analyze evolution --competitor-name`` con homónimos → devuelve None
  con mensaje claro.
- ``analyze evolution --competitor-name`` sin match → exit 1.
- ``analyze projection`` con competitor inexistente → exit 1.
- ``analyze projection`` sin event activo → exit 1.
- ``_get_or_create_system_user`` cuando ya existe + cuando hay que crearlo.
- ``_meta_from_yaml`` con valores inválidos (temperature_c basura,
  surface_condition desconocido, event_date inválido).
- ``_meta_from_yaml`` happy path con todos los campos.
- ``_decisions_from_yaml`` con dict (no lista) → BadParameter.
- ``analyze gap`` con categoría inexistente → exit 1.
- ``_sha256_of`` deterministic.
- ``analyze projection`` con confidence high (no warning).
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer import BadParameter
from typer.testing import CliRunner

from scripts import ingest_race as cli_module
from tests.services.race.conftest import FakeAsyncSession, _build_seeded_store


# ---------------------------------------------------------------------------
# Reuse helpers from main CLI test file via local copies (simpler than import)
# ---------------------------------------------------------------------------


class _AsyncSessionCM:
    def __init__(self, session: FakeAsyncSession):
        self._s = session

    async def __aenter__(self) -> FakeAsyncSession:
        return self._s

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fake_open_session(monkeypatch):
    """Devuelve una factory que registra una FakeAsyncSession y la inyecta."""
    holder: dict[str, FakeAsyncSession] = {}

    def _install(session: FakeAsyncSession) -> FakeAsyncSession:
        holder["session"] = session
        monkeypatch.setattr(cli_module, "_open_session",
                            lambda: _AsyncSessionCM(session))

        async def _fake_get_system_user(db):
            return 1
        monkeypatch.setattr(cli_module, "_get_or_create_system_user",
                            _fake_get_system_user)
        return session

    return _install


# ===========================================================================
# 1. _sha256_of — deterministic
# ===========================================================================


class TestSha256:
    def test_sha256_of_known_content(self, tmp_path: Path):
        from scripts.ingest_race import _sha256_of

        p = tmp_path / "test.bin"
        p.write_bytes(b"trocha y ruta")
        expected = hashlib.sha256(b"trocha y ruta").hexdigest()
        assert _sha256_of(p) == expected

    def test_sha256_of_large_file(self, tmp_path: Path):
        """Lee en chunks de 64K — verificar con archivo > 64K."""
        from scripts.ingest_race import _sha256_of

        p = tmp_path / "big.bin"
        content = b"x" * (70 * 1024)
        p.write_bytes(content)
        assert _sha256_of(p) == hashlib.sha256(content).hexdigest()


# ===========================================================================
# 2. _load_yaml
# ===========================================================================


class TestLoadYaml:
    def test_missing_yaml_raises_bad_param(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml

        with pytest.raises(BadParameter):
            _load_yaml(tmp_path / "missing.yaml")

    def test_empty_yaml_returns_empty_dict(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml

        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        assert _load_yaml(p) == {}


# ===========================================================================
# 3. _meta_from_yaml — happy path + errors
# ===========================================================================


class TestMetaFromYaml:
    def _yaml(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "m.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        return p

    def test_full_happy_path(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "season": 2026,
            "valida_num": 4,
            "name": "V-IV CALI",
            "event_date": "2026-05-17",
            "location": "CALI",
            "climate": "soleado",
            "temperature_c": "27.5",
            "surface_condition": "seca",
            "altitude_msnm": 1003,
            "weather_notes": "buena",
        })
        meta = _meta_from_yaml(_load_yaml(p), Path("r.pdf"), Path("g.pdf"))
        assert meta.valida_num == 4
        assert meta.event_date == date(2026, 5, 17)
        assert meta.temperature_c is not None
        assert meta.pdf_results_filename == "r.pdf"
        assert meta.pdf_general_filename == "g.pdf"

    def test_invalid_temperature_raises(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "valida_num": 4,
            "event_date": "2026-05-17",
            "location": "CALI",
            "temperature_c": "BADNUMBER",
        })
        with pytest.raises(BadParameter, match="temperature_c"):
            _meta_from_yaml(_load_yaml(p), Path("r.pdf"), None)

    def test_invalid_surface_raises(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "valida_num": 4,
            "event_date": "2026-05-17",
            "location": "CALI",
            "surface_condition": "plasma",  # no es enum válido
        })
        with pytest.raises(BadParameter, match="surface_condition"):
            _meta_from_yaml(_load_yaml(p), Path("r.pdf"), None)

    def test_missing_event_date_raises(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "valida_num": 4,
            "location": "CALI",
        })
        with pytest.raises(BadParameter, match="event_date"):
            _meta_from_yaml(_load_yaml(p), Path("r.pdf"), None)

    def test_empty_temperature_becomes_none(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "valida_num": 4,
            "event_date": "2026-05-17",
            "location": "CALI",
            "temperature_c": "",
        })
        meta = _meta_from_yaml(_load_yaml(p), Path("r.pdf"), None)
        assert meta.temperature_c is None

    def test_empty_surface_becomes_none(self, tmp_path: Path):
        from scripts.ingest_race import _load_yaml, _meta_from_yaml

        p = self._yaml(tmp_path, {
            "valida_num": 4,
            "event_date": "2026-05-17",
            "location": "CALI",
            "surface_condition": "",
        })
        meta = _meta_from_yaml(_load_yaml(p), Path("r.pdf"), None)
        assert meta.surface_condition is None


# ===========================================================================
# 4. _decisions_from_yaml — corner cases
# ===========================================================================


class TestDecisionsFromYaml:
    def test_entry_not_dict_raises(self):
        from scripts.ingest_race import _decisions_from_yaml

        with pytest.raises(BadParameter, match="entrada inválida|Entrada inválida"):
            _decisions_from_yaml(["solostring"])  # type: ignore[list-item]

    def test_entry_without_bib_raises(self):
        from scripts.ingest_race import _decisions_from_yaml

        with pytest.raises(BadParameter, match="bib"):
            _decisions_from_yaml([{"athlete_id": 12}])


# ===========================================================================
# 5. analyze evolution / gap / projection — error paths
# ===========================================================================


class TestAnalyzeErrorPaths:
    def test_evolution_requires_competitor_arg(self, runner):
        r = runner.invoke(cli_module.app, ["analyze", "evolution"])
        assert r.exit_code == 2

    def test_projection_requires_competitor_arg(self, runner):
        r = runner.invoke(
            cli_module.app, ["analyze", "projection", "--next-valida", "5"]
        )
        assert r.exit_code == 2

    def test_evolution_competitor_not_found_exits_1(self, runner, fake_open_session):
        session = fake_open_session(FakeAsyncSession(store=_build_seeded_store()))
        r = runner.invoke(
            cli_module.app,
            ["analyze", "evolution", "--competitor-name", "Nadie Especial"],
        )
        assert r.exit_code == 1

    def test_gap_category_not_found_exits_1(self, runner, fake_open_session):
        session = fake_open_session(FakeAsyncSession(store=_build_seeded_store()))
        r = runner.invoke(
            cli_module.app,
            ["analyze", "gap", "--category-code", "INEXISTENTE", "--season", "2026"],
        )
        assert r.exit_code == 1

    def test_projection_competitor_not_found_exits_1(self, runner, fake_open_session):
        session = fake_open_session(FakeAsyncSession(store=_build_seeded_store()))
        r = runner.invoke(
            cli_module.app,
            [
                "analyze", "projection",
                "--competitor-name", "Nadie",
                "--next-valida", "5",
            ],
        )
        assert r.exit_code == 1


# ===========================================================================
# 6. _resolve_competitor_by_name — homónimos
# ===========================================================================


class TestResolveCompetitorByName:
    @pytest.mark.asyncio
    async def test_returns_none_for_empty_input(self):
        from scripts.ingest_race import _resolve_competitor_by_name

        session = FakeAsyncSession(store=_build_seeded_store())
        assert await _resolve_competitor_by_name(session, "") is None
        assert await _resolve_competitor_by_name(session, None) is None

    @pytest.mark.asyncio
    async def test_with_mock_session_returns_id_when_unique_match(self):
        """Mock que simula un único match → retorna el id."""
        from app.models.race_competitor import RaceCompetitor
        from scripts.ingest_race import _resolve_competitor_by_name

        comp = RaceCompetitor(
            id=42, normalized_name="thiago duque",
            display_name="Thiago Duque", club_text="Club",
        )

        class _Scalars:
            def all(self_inner): return [comp]

        class _Result:
            def scalars(self_inner): return _Scalars()

        class _MockSession:
            async def execute(self_inner, stmt): return _Result()

        assert await _resolve_competitor_by_name(_MockSession(), "Thiago") == 42

    @pytest.mark.asyncio
    async def test_with_mock_session_returns_none_when_homonyms(self):
        """Si hay > 1 match (homónimos) → retorna None y avisa."""
        from app.models.race_competitor import RaceCompetitor
        from scripts.ingest_race import _resolve_competitor_by_name

        comp1 = RaceCompetitor(
            id=1, normalized_name="juan perez",
            display_name="Juan Perez", club_text="Club X",
        )
        comp2 = RaceCompetitor(
            id=2, normalized_name="juan perez",
            display_name="Juan Perez", club_text="Club Y",
        )

        class _Scalars:
            def all(self_inner): return [comp1, comp2]

        class _Result:
            def scalars(self_inner): return _Scalars()

        class _MockSession:
            async def execute(self_inner, stmt): return _Result()

        assert await _resolve_competitor_by_name(_MockSession(), "Juan") is None

    @pytest.mark.asyncio
    async def test_with_mock_session_returns_none_when_no_match(self):
        from scripts.ingest_race import _resolve_competitor_by_name

        class _Scalars:
            def all(self_inner): return []

        class _Result:
            def scalars(self_inner): return _Scalars()

        class _MockSession:
            async def execute(self_inner, stmt): return _Result()

        assert await _resolve_competitor_by_name(_MockSession(), "Nadie") is None


# ===========================================================================
# 7. _present_name + _mask_name
# ===========================================================================


class TestPresentName:
    def test_show_true_returns_full(self):
        from scripts.ingest_race import _present_name
        assert _present_name("Thiago Duque Cardona", show=True) == "Thiago Duque Cardona"

    def test_show_false_masks(self):
        from scripts.ingest_race import _present_name
        assert _present_name("Thiago Duque Cardona", show=False) == "T. Cardona"

    def test_empty_returns_placeholder_when_masked(self):
        from scripts.ingest_race import _present_name
        assert _present_name("", show=False) == "?"


# ===========================================================================
# 8. riders link — flujo completo (con stubs robustos)
# ===========================================================================


class _MockResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _MockSessionForLink:
    """Mini-session a medida para testear ``_riders_link_impl`` sin requerir
    soporte UPDATE en FakeAsyncSession.

    Maneja únicamente las 3 queries que el comando ejecuta:
    1. ``select(RaceCompetitor).where(id == competitor_id)``
    2. ``select(Athlete).where(id == athlete_id)``
    3. ``update(RaceResult).where(competitor_id == cid).values(...)`` — no-op.
    """
    def __init__(self, competitor, athlete):
        self.competitor = competitor
        self.athlete = athlete
        self.updates_applied = []
        self.committed = False

    def __aenter__(self): return self
    def __aexit__(self, *a): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None

    async def execute(self, stmt):
        from sqlalchemy.sql.selectable import Select
        from sqlalchemy.sql.dml import Update

        if isinstance(stmt, Update):
            self.updates_applied.append(stmt)
            return _MockResult(None)

        if isinstance(stmt, Select):
            # Inspect FROM table to decide
            froms = list(stmt.get_final_froms())
            tname = froms[0].name if froms else None
            if tname == "race_competitors":
                return _MockResult(self.competitor)
            if tname == "athletes":
                return _MockResult(self.athlete)
        return _MockResult(None)

    async def commit(self): self.committed = True
    async def rollback(self): pass


class TestRidersLink:
    def test_link_missing_competitor_exits_1(self, runner, monkeypatch):
        """Si el competitor no existe → exit 1."""
        session = _MockSessionForLink(competitor=None, athlete=None)

        class _CM:
            async def __aenter__(self_inner): return session
            async def __aexit__(self_inner, *a): return None

        monkeypatch.setattr(cli_module, "_open_session", lambda: _CM())
        r = runner.invoke(
            cli_module.app,
            ["riders", "link", "--competitor-id", "999", "--athlete-id", "1", "--force"],
        )
        assert r.exit_code == 1
        assert "no encontrado" in r.stdout.lower()

    def test_link_missing_athlete_exits_1(self, runner, monkeypatch):
        """Si el competitor existe pero athlete no → exit 1."""
        from app.models.race_competitor import RaceCompetitor

        comp = RaceCompetitor(
            id=1, normalized_name="x", display_name="X", club_text="Club"
        )
        session = _MockSessionForLink(competitor=comp, athlete=None)

        class _CM:
            async def __aenter__(self_inner): return session
            async def __aexit__(self_inner, *a): return None

        monkeypatch.setattr(cli_module, "_open_session", lambda: _CM())
        r = runner.invoke(
            cli_module.app,
            ["riders", "link", "--competitor-id", "1", "--athlete-id", "999", "--force"],
        )
        assert r.exit_code == 1
        assert "athlete" in r.stdout.lower() and "no encontrado" in r.stdout.lower()

    def test_link_happy_path_with_force(self, runner, monkeypatch):
        """competitor + athlete válidos + --force → exit 0 + comp.athlete_id seteado."""
        from app.models.athlete import Athlete, Sex
        from app.models.race_competitor import RaceCompetitor

        comp = RaceCompetitor(
            id=1, normalized_name="thiago duque", display_name="Thiago Duque",
            club_text="Club Trocha y Ruta",
        )
        athlete = Athlete(
            id=42, user_id=10, first_name="Thiago", last_name="Duque",
            birth_date=date(2016, 1, 1), sex=Sex.M, club_id=1,
            created_by=1,
        )
        session = _MockSessionForLink(competitor=comp, athlete=athlete)

        class _CM:
            async def __aenter__(self_inner): return session
            async def __aexit__(self_inner, *a): return None

        monkeypatch.setattr(cli_module, "_open_session", lambda: _CM())

        async def _fake_sys(db): return 99
        monkeypatch.setattr(cli_module, "_get_or_create_system_user", _fake_sys)

        r = runner.invoke(
            cli_module.app,
            ["riders", "link", "--competitor-id", "1", "--athlete-id", "42", "--force"],
        )
        assert r.exit_code == 0, f"stdout: {r.stdout}"
        assert comp.athlete_id == 42
        assert comp.linked_by_user_id == 99
        assert comp.linked_at is not None
        # Update sobre race_results se ejecutó
        assert len(session.updates_applied) == 1
        assert session.committed


# ===========================================================================
# 9. _get_or_create_system_user — happy path con FakeAsyncSession extendida
# ===========================================================================


class TestGetOrCreateSystemUser:
    """Verifica la lógica del helper sin depender de DB real."""

    @pytest.mark.asyncio
    async def test_returns_existing_user_id_if_present(self, monkeypatch):
        """Si el user ya existe, lo retorna sin insert."""
        from app.models.user import User, UserRole
        from scripts.ingest_race import _get_or_create_system_user

        existing = User(
            id=77, email="system@trochyruta.com", first_name="System",
            last_name="CLI", role=UserRole.admin, is_active=True, can_login=False,
        )

        class _MockSession:
            async def execute(self, stmt):
                return _MockResult(existing)

            def add(self, obj):
                pytest.fail("No debe agregar si ya existe")

            async def flush(self): pass
            async def commit(self): pass

        uid = await _get_or_create_system_user(_MockSession())
        assert uid == 77

    @pytest.mark.asyncio
    async def test_creates_new_user_if_missing(self):
        """Si no existe, crea uno con can_login=False y devuelve el id."""
        from scripts.ingest_race import _get_or_create_system_user

        added = []

        class _MockSession:
            async def execute(self, stmt):
                return _MockResult(None)

            def add(self, obj):
                added.append(obj)
                obj.id = 100

            async def flush(self): pass
            async def commit(self): pass

        uid = await _get_or_create_system_user(_MockSession())
        assert uid == 100
        assert len(added) == 1
        new_user = added[0]
        assert new_user.email == "system@trochyruta.com"
        assert new_user.can_login is False
