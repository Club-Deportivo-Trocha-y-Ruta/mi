"""Pruebas de privacidad transversales de la feature 047 (Ley 1581).

T011 (specs/047-imderty-attendance-sheet/tasks.md): tres garantías estáticas
y dinámicas que no dependen de que una historia de usuario esté implementada
todavía —viven en este archivo desde la fase de fundamentos y se extienden en
fases posteriores con aserciones de logs y auditoría.

1. Barrera de importación: ningún módulo de las pilas de IA, LLM, carreras,
   notificaciones o el boletín mensual puede importar ``app.models.imderty``
   ni ``app.services.imderty`` — los datos sensibles de IMDERTY nunca deben
   poder llegar a un prompt, un log o un correo por una ruta de importación
   directa.
2. Vista de padre: ``GET /api/athletes/{id}`` para un padre no debe traer
   ninguna de las claves nuevas del perfil IMDERTY.
3. Sin orientación sexual: la feature no define, en ningún modelo, esquema o
   columna, un campo de orientación sexual (la categoría que FR-009 excluye
   deliberadamente).
"""
from __future__ import annotations

import ast
import pathlib

import pytest
import pytest_asyncio

from app.models import Base

# Módulos (por su ruta relativa a app/) cuyo código no debe importar nada de
# IMDERTY — datos sensibles de menores nunca deben alcanzar un prompt de IA,
# una llamada LLM, el análisis de carreras, una notificación o el boletín.
_FORBIDDEN_IMPORT_PREFIXES = (
    "app/services/ai/",
    "app/services/llm/",
    "app/services/race/",
    "app/services/notification/",
    "app/services/training/newsletter",
)

_FORBIDDEN_MODULES = {"app.models.imderty", "app.services.imderty"}


def _app_root() -> pathlib.Path:
    # backend/tests/imderty/test_imderty_privacy.py -> backend/app
    return pathlib.Path(__file__).resolve().parents[2] / "app"


def _relative_posix(path: pathlib.Path, app_root: pathlib.Path) -> str:
    return "app/" + path.relative_to(app_root).as_posix()


def _imported_module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                # También registra el "prefijo" completo módulo.submódulo en
                # caso de `from app.models import imderty` (module="app.models",
                # name="imderty").
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
    return names


def _iter_python_files(app_root: pathlib.Path):
    for path in sorted(app_root.rglob("*.py")):
        rel = _relative_posix(path, app_root)
        if rel.startswith(_FORBIDDEN_IMPORT_PREFIXES):
            yield path, rel


class TestNoForbiddenImports:
    """1. Barrido AST/grep: ninguna de las pilas prohibidas importa IMDERTY."""

    def test_ast_sweep_finds_no_imderty_import(self) -> None:
        app_root = _app_root()
        offenders: list[str] = []

        for path, rel in _iter_python_files(app_root):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensivo
                continue
            imported = _imported_module_names(tree)
            if imported & _FORBIDDEN_MODULES:
                offenders.append(rel)

        assert offenders == [], (
            "Módulos de IA/LLM/carreras/notificaciones/boletín que importan "
            f"IMDERTY (prohibido, Ley 1581): {offenders}"
        )

    def test_grep_sweep_finds_no_imderty_reference(self) -> None:
        """Refuerzo textual: ni siquiera un import dinámico/string debería
        mencionar los módulos de IMDERTY en estas pilas."""
        app_root = _app_root()
        offenders: list[str] = []

        for path, rel in _iter_python_files(app_root):
            text = path.read_text(encoding="utf-8")
            if "app.models.imderty" in text or "app.services.imderty" in text:
                offenders.append(rel)

        assert offenders == [], (
            f"Referencias textuales a IMDERTY en pilas prohibidas: {offenders}"
        )

    def test_forbidden_prefixes_actually_exist(self) -> None:
        """Guarda contra un barrido que pasa en falso porque las carpetas no
        existen (p.ej. un typo en el prefijo)."""
        app_root = _app_root()
        found_any = {prefix: False for prefix in _FORBIDDEN_IMPORT_PREFIXES}
        for path in app_root.rglob("*.py"):
            rel = _relative_posix(path, app_root)
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                if rel.startswith(prefix):
                    found_any[prefix] = True
        missing = [prefix for prefix, seen in found_any.items() if not seen]
        assert missing == [], f"Prefijos sin ningún archivo real: {missing}"


@pytest.mark.asyncio
class TestParentAthleteViewExcludesImderty:
    """2. La vista de padre de /api/athletes/{id} no expone campos IMDERTY."""

    _FORBIDDEN_KEYS = (
        "document_number",
        "document_type",
        "eps",
        "barrio",
        "barrio_id",
        "ethnicity",
        "disability",
        "conflict_victim",
        "first_surname",
        "second_surname",
        "address",
        "school",
        "grade",
        "phone",
        "other_municipality",
    )

    @pytest_asyncio.fixture(autouse=True)
    async def _with_anthropometry_table(self, imderty_engine):
        """El escenario de ``conftest.py`` solo crea las tablas que las
        rutas IMDERTY necesitan (T010); ``GET /api/athletes/{id}`` también
        consulta ``anthropometric_records`` para armar la vista de padre.
        Este archivo no puede tocar ``conftest.py`` (propiedad de T010), así
        que agrega la tabla que le falta sobre el mismo engine compartido."""
        async with imderty_engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c, tables=[Base.metadata.tables["anthropometric_records"]]
                )
            )

    async def test_parent_view_has_no_imderty_keys(
        self, imderty_client_factory, imderty_scenario
    ) -> None:
        async with imderty_client_factory(
            imderty_scenario.parent_user_id
        ) as client:
            response = await client.get(
                f"/api/athletes/{imderty_scenario.parent_athlete_one_id}"
            )

        assert response.status_code == 200
        body = response.json()

        present = [key for key in self._FORBIDDEN_KEYS if key in body]
        assert present == [], (
            f"La vista de padre expone claves de IMDERTY: {present} — body={body}"
        )


class TestNoSexualOrientationField:
    """3. La categoría excluida por FR-009 no tiene enum, columna ni etiqueta."""

    def test_no_orientation_string_in_imderty_model(self) -> None:
        model_path = _app_root() / "models" / "imderty.py"
        text = model_path.read_text(encoding="utf-8").lower()
        assert "orientation" not in text
        assert "orientacion" not in text
        assert "orientación" not in text

    def test_no_orientation_string_in_imderty_schema(self) -> None:
        schema_path = _app_root() / "schemas" / "imderty.py"
        if not schema_path.exists():
            pytest.skip("app/schemas/imderty.py aún no existe en esta fase")
        text = schema_path.read_text(encoding="utf-8").lower()
        assert "orientation" not in text
        assert "orientacion" not in text
        assert "orientación" not in text

    def test_no_orientation_column_anywhere_under_models_imderty_dir(self) -> None:
        """Cobertura amplia: cualquier módulo bajo app/models cuyo nombre
        empiece por imderty, más cualquier migración cuyo nombre lo indique."""
        app_root = _app_root()
        offenders: list[str] = []
        for path in app_root.rglob("*imderty*.py"):
            rel = _relative_posix(path, app_root)
            text = path.read_text(encoding="utf-8").lower()
            if "orientation" in text or "orientacion" in text or "orientación" in text:
                offenders.append(rel)
        assert offenders == [], f"Mención de orientación sexual en: {offenders}"


# ---------------------------------------------------------------------------
# 4. T038 (US2 gate) — log and audit_log scans over the whole feature flow
# ---------------------------------------------------------------------------

#: Distinctive fictitious values, one per new field, easy to spot if any of
#: them leaked into a log line or an ``audit_log`` column. None of them
#: corresponds to a real person (CLAUDE.md, Ley 1581).
_FLOW_DOCUMENT_NUMBER = "9990047123"
_FLOW_BAD_DOCUMENT_NUMBER = "99X0047ZZQ"
_FLOW_ADDRESS = "CALLE FICTICIA 47 ZETA"
_FLOW_SCHOOL = "COLEGIO FICTICIO OMEGA"
_FLOW_EPS = "EPS FICTICIA KAPPA"
_FLOW_PHONE = "3009990047"
_FLOW_ETHNICITY = "PALENQUERO"
_FLOW_DISABILITY = "OLFATIVA Y TACTO"
_FLOW_SURNAME = "Ficticio"

_FLOW_LEAK_MARKERS = (
    _FLOW_DOCUMENT_NUMBER,
    _FLOW_BAD_DOCUMENT_NUMBER,
    _FLOW_ADDRESS,
    _FLOW_SCHOOL,
    _FLOW_EPS,
    _FLOW_PHONE,
    _FLOW_ETHNICITY,
    _FLOW_DISABILITY,
    "Atleta Ficticio Uno",
)

#: Every table the flow touches beyond ``conftest.py``'s shared subset.
_FLOW_TABLES = (
    "imderty_barrios",
    "athlete_imderty_profiles",
    "athlete_sensitive_authorizations",
    "athlete_sensitive_data",
    "club_imderty_settings",
    "training_sessions",
    "session_attendance",
    "calendar_events",
    "event_audiences",
    "event_attendances",
    "race_events",
    "race_results",
)

#: Driver debug output (aiosqlite/SQLAlchemy echo bound parameters in the
#: test lane only) is not an application log; everything else is scanned,
#: message and ``extra`` attributes alike.
_DRIVER_LOGGERS = ("aiosqlite", "sqlalchemy")


def _app_log_text(records) -> str:  # noqa: ANN001
    return "\n".join(
        f"{record.getMessage()} {record.__dict__}"
        for record in records
        if not record.name.startswith(_DRIVER_LOGGERS)
    ).lower()


@pytest.mark.asyncio
class TestFeatureFlowNeverLeaksValues:
    """T038: the full admin/coach flow — barrio, profile, primary contact,
    sensitive authorization and values, settings, sheet download, a rejected
    PUT and the withdrawal — never writes a value of the new fields (or the
    athlete's name) into an application log line or into any ``audit_log``
    column, while the downloaded sheet does carry them (so the markers are
    real, not a scan that passes because nothing was written)."""

    @pytest_asyncio.fixture(autouse=True)
    async def _with_flow_tables(self, imderty_engine):
        async with imderty_engine.begin() as conn:
            for name in _FLOW_TABLES:
                await conn.run_sync(
                    lambda c, name=name: Base.metadata.tables[name].create(
                        c, checkfirst=True
                    )
                )

    async def test_flow_logs_and_audit_carry_no_values(
        self, imderty_client_factory, imderty_scenario, caplog
    ) -> None:
        import json
        import logging
        from io import BytesIO

        from openpyxl import load_workbook
        from sqlalchemy import select

        from app.models.audit_log import AuditLog

        caplog.set_level(logging.DEBUG)
        s = imderty_scenario
        athlete_id = s.two_guardians_athlete_id
        athlete_one = s.parent_athlete_one_id

        async with imderty_client_factory(s.admin_user_id) as admin:
            barrio = await admin.post(
                "/api/imderty/barrios",
                json={"name": "BARRIO FICTICIO CUARENTA Y SIETE", "zone": "ZONA NORTE"},
            )
            assert barrio.status_code == 201
            barrio_id = barrio.json()["id"]

        async with imderty_client_factory(s.coach_user_id) as coach:
            rejected = await coach.put(
                f"/api/athletes/{athlete_one}/imderty-profile",
                json={"document_type": "ti", "document_number": _FLOW_BAD_DOCUMENT_NUMBER},
            )
            assert rejected.status_code == 422
            assert _FLOW_BAD_DOCUMENT_NUMBER not in rejected.text

            profile = await coach.put(
                f"/api/athletes/{athlete_one}/imderty-profile",
                json={
                    "document_type": "ti",
                    "document_number": _FLOW_DOCUMENT_NUMBER,
                    "address": _FLOW_ADDRESS,
                    "barrio_id": barrio_id,
                    "school": _FLOW_SCHOOL,
                    "grade": "g6",
                    "eps": _FLOW_EPS,
                    "phone": _FLOW_PHONE,
                    "first_surname": _FLOW_SURNAME,
                    "confirm_surname_split": True,
                },
            )
            assert profile.status_code == 200, profile.text

            primary = await coach.put(
                f"/api/athletes/{athlete_id}/primary-contact",
                json={"guardian_user_id": s.second_guardian_user_id},
            )
            assert primary.status_code == 200, primary.text

            authorization = await coach.post(
                f"/api/athletes/{athlete_one}/sensitive-authorizations",
                json={"guardian_user_id": s.parent_user_id, "authorized_on": "2026-08-01"},
            )
            assert authorization.status_code == 201
            values = await coach.put(
                f"/api/athletes/{athlete_one}/sensitive-data",
                json={
                    "ethnicity": _FLOW_ETHNICITY,
                    "disability": _FLOW_DISABILITY,
                    "conflict_victim": "si",
                },
            )
            assert values.status_code == 200

            settings = await coach.put(
                f"/api/clubs/{s.club_id}/imderty-settings",
                json={"contractor_name": "CONTRATISTA FICTICIO", "programs": ["individual"]},
            )
            assert settings.status_code == 200

            sheet = await coach.post(
                f"/api/clubs/{s.club_id}/imderty-sheet",
                json={"from": "2026-08", "to": "2026-08"},
            )
            assert sheet.status_code == 200

            withdrawn = await coach.post(
                f"/api/athletes/{athlete_one}/sensitive-authorizations/withdraw"
            )
            assert withdrawn.status_code == 200

        # The markers are real: the downloaded sheet carries them.
        ws = load_workbook(BytesIO(sheet.content))["AGOSTO"]
        sheet_text = " ".join(
            str(cell.value) for row in ws.iter_rows(min_row=24, max_row=30) for cell in row
            if cell.value is not None
        )
        for marker in (_FLOW_DOCUMENT_NUMBER, _FLOW_ADDRESS, _FLOW_SCHOOL, _FLOW_EPS,
                       _FLOW_PHONE, _FLOW_ETHNICITY, _FLOW_DISABILITY):
            assert marker in sheet_text, marker

        # Log scan (application loggers, message + extra attributes).
        log_text = _app_log_text(caplog.records)
        for marker in _FLOW_LEAK_MARKERS:
            assert marker.lower() not in log_text, marker

        # audit_log scan: every column that could carry data, every row.
        rows = (
            await s.session.execute(
                select(AuditLog).execution_options(populate_existing=True)
            )
        ).scalars().all()
        entity_types = {row.entity_type for row in rows}
        assert {
            "imderty_barrio",
            "athlete_imderty_profile",
            "athlete_sensitive_authorization",
            "athlete_sensitive_data",
            "club_imderty_settings",
            "imderty_attendance_sheet",
        } <= entity_types
        dumped = json.dumps(
            [
                [
                    row.entity_type,
                    row.action,
                    row.changed_fields,
                    row.diff_json,
                    row.meta_json,
                    row.reason_code,
                ]
                for row in rows
            ],
            default=str,
            ensure_ascii=False,
        ).lower()
        for marker in _FLOW_LEAK_MARKERS:
            assert marker.lower() not in dumped, marker

        # The IMDERTY rows carry field names only — no values at all.
        for row in rows:
            if row.entity_type in {
                "athlete_imderty_profile",
                "athlete_sensitive_authorization",
                "athlete_sensitive_data",
            }:
                assert row.diff_json is None, row.entity_type

        export = [r for r in rows if r.entity_type == "imderty_attendance_sheet"]
        assert len(export) == 1
        assert set(export[0].meta_json) == {
            "document_kind", "from_month", "to_month", "row_count", "gap_count",
        }
        assert [
            r.reason_code
            for r in rows
            if r.entity_type == "athlete_sensitive_authorization" and r.action == "update"
        ] == ["withdrawn"]
