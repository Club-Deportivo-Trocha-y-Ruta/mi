"""Sentinels de auditoría de privacidad — Módulo Race (Paso 8).

Estos tests son **regresión sentinel**: bloquean cambios silenciosos al CLI
o al ingestor que filtren nombres completos de menores en superficies que
deberían estar agregadas o enmascaradas por default.

Marco legal:
- Ley 1581/2012 Colombia (Habeas Data) — datos sensibles de menores.
- CLAUDE.md principio #2: "Nunca exponer datos personales (DOB, datos médicos)
  en logs, commits o respuestas públicas".
- Workflow `docs/10-race-results/workflow.md` §8.1 — superficies auditables.

Sentinels cubiertos:
1. ``ingest --non-interactive`` stdout no debe contener nombres TyR completos
   (los 10 oracle de edge-cases §5). El stdout de ``ingest`` es para conteos
   y warnings — los warnings ya están validados por
   ``test_warnings_do_not_leak_names``; este test cubre además el resto del
   stdout (banner Parseo, tabla resumen, IngestReport panel).
2. ``analyze ranking`` stdout no debe contener nombres TyR (ranking es
   agregado por categoría, NO individual — workflow §8.1).
3. ``riders list`` default (sin ``--show-names``) no debe revelar apellido
   completo de los oracle TyR; sólo inicial+apellido del helper ``_mask_name``.

Ver `docs/10-race-results/privacy-audit.md` Paso 8 para el reporte completo.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from scripts import ingest_race as cli_module
from tests.services.race.conftest import FakeAsyncSession, _build_seeded_store
from tests.test_ingest_race_cli import _AsyncSessionCM


# ---------------------------------------------------------------------------
# Oracle de nombres TyR Válida IV (edge-cases.md §5)
# ---------------------------------------------------------------------------
#
# Apellidos/nombres completos que NO deben aparecer literalmente en stdout
# de comandos agregados o de listado default. Validamos sobre el primer
# nombre + último apellido — fragmentos cortos (Dnf, etc.) se ignoran para
# evitar falsos positivos con texto técnico.
_TYR_FULL_NAMES_VALIDA_IV: tuple[str, ...] = (
    "Thiago Duque Cardona",
    "Juan David Giraldo Ortiz",
    "Sofia Gomez",
    "Eileen Sophia Vargas Bonilla",
    "Miguel Angel Anaya",
    "Matías Montoya",
    "Jostin Villamizar García",
    "Isabel Cristhina Quiñones Batero",
    "Mariana Coronado Delgado",
    "Juan Diego Garcia",
)


def _name_fragments_to_check() -> set[str]:
    """Devuelve tokens >= 5 chars de los 10 oracle TyR.

    Filtramos por longitud para evitar colisiones con texto técnico
    (ej. "Ana" colisionaría con "Anaya" si no filtramos a >=5).
    """
    out: set[str] = set()
    for full in _TYR_FULL_NAMES_VALIDA_IV:
        for tok in full.split():
            tok_clean = tok.strip(".,;:")
            if len(tok_clean) >= 5:
                out.add(tok_clean)
    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shared_store():
    return _build_seeded_store()


@pytest.fixture
def patched_session(monkeypatch, shared_store):
    session = FakeAsyncSession(store=shared_store)

    def _open():
        return _AsyncSessionCM(session)

    async def _fake_get_system_user(db):
        return 1

    monkeypatch.setattr(cli_module, "_open_session", _open)
    monkeypatch.setattr(cli_module, "_get_or_create_system_user", _fake_get_system_user)
    return session


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def event_meta_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "event.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "season": 2026,
                "copa_code": "copa_valle",
                "valida_num": 4,
                "name": "VALIDA IV CALI MAYO 17 DE 2026",
                "event_date": "2026-05-17",
                "location": "CALI",
                "climate": "soleado",
                "temperature_c": "27.5",
                "surface_condition": "seca",
                "altitude_msnm": 1003,
                "weather_notes": "Pista en buen estado.",
            }
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def empty_decisions_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "decisions.yaml"
    p.write_text("[]\n", encoding="utf-8")
    return p


@pytest.fixture(scope="session")
def valida_iv_resultados_pdf() -> Path:
    p = Path(__file__).parent / "fixtures" / "race" / "valida_iv_2026_resultados.pdf"
    assert p.exists(), f"Fixture faltante: {p}"
    return p


@pytest.fixture(scope="session")
def valida_iv_general_pdf() -> Path:
    p = Path(__file__).parent / "fixtures" / "race" / "valida_iv_2026_general.pdf"
    assert p.exists(), f"Fixture faltante: {p}"
    return p


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------


class TestIngestStdoutDoesNotLeakNames:
    def test_ingest_non_interactive_stdout_has_no_tyr_full_names(
        self,
        runner,
        patched_session,
        event_meta_yaml,
        empty_decisions_yaml,
        valida_iv_resultados_pdf,
        valida_iv_general_pdf,
    ):
        """``ingest --non-interactive`` no debe filtrar nombres TyR completos.

        El stdout legítimo del comando incluye: banner Parseo (filename),
        línea ``parseo OK: N categorías | M corredores | K TyR``, tabla
        resumen previo (sin nombres), panel IngestReport (conteos), lista
        de warnings (validada por sentinel separado).

        Ningún apellido oracle de los 10 TyR de Válida IV debe aparecer
        literal en stdout — la confirmación interactiva de matches (donde
        SÍ se muestran nombres al coach) está bypasseada en
        ``--non-interactive``.
        """
        r = runner.invoke(
            cli_module.app,
            [
                "ingest",
                "--results",
                str(valida_iv_resultados_pdf),
                "--general",
                str(valida_iv_general_pdf),
                "--non-interactive",
                "--event-meta",
                str(event_meta_yaml),
                "--match-decisions",
                str(empty_decisions_yaml),
                "--user-id",
                "1",
            ],
        )
        assert r.exit_code == 0, (
            f"ingest falló inesperadamente: {r.stdout}\n{r.stderr}"
        )
        stdout = r.stdout
        leaked: list[str] = []
        for fragment in _name_fragments_to_check():
            if fragment in stdout:
                leaked.append(fragment)
        assert not leaked, (
            f"Fragmentos TyR filtrados en stdout de `ingest`: {sorted(leaked)}.\n"
            "Si añadiste un nuevo `console.print` con `row.name` o "
            "`competitor.display_name`, considera enmascarar con `_mask_name`.\n"
            f"STDOUT:\n{stdout}"
        )


class TestAnalyzeRankingDoesNotLeakNames:
    def test_ranking_stdout_has_no_individual_names(
        self,
        runner,
        patched_session,
        event_meta_yaml,
        empty_decisions_yaml,
        valida_iv_resultados_pdf,
        monkeypatch,
        tmp_path,
    ):
        """``analyze ranking`` es agregado por categoría — sin nombres
        individuales (CLAUDE.md principio #2 + design.md §8).

        Mockeamos ``analytics.club_ranking`` para devolver datos consistentes
        y verificamos que el stdout (tablas rich + markdown opcional) no
        contenga ningún apellido oracle TyR. El ranking se compone de
        ``category_code`` + métricas agregadas (active_riders, podiums,
        wins, total_points) — nunca individual.
        """
        # Ingest dummy para tener serie/evento
        r0 = runner.invoke(
            cli_module.app,
            [
                "ingest",
                "--results",
                str(valida_iv_resultados_pdf),
                "--non-interactive",
                "--event-meta",
                str(event_meta_yaml),
                "--match-decisions",
                str(empty_decisions_yaml),
            ],
        )
        assert r0.exit_code == 0

        # Mock club_ranking con datos limpios (sin nombres)
        async def fake_ranking(db, season):
            return {
                "by_category": [
                    {
                        "category_code": "INF_A",
                        "total_points": 200,
                        "podiums": 3,
                        "wins": 1,
                        "active_riders": 4,
                    },
                    {
                        "category_code": "PJUV_A_F",
                        "total_points": 150,
                        "podiums": 2,
                        "wins": 1,
                        "active_riders": 2,
                    },
                ],
                "total_points": 350,
                "total_podiums": 5,
                "total_wins": 2,
                "active_riders": 6,
                "distribution_by_tier": {
                    "menores": 4,
                    "juvenil": 2,
                    "adulto": 0,
                    "master": 0,
                },
            }

        from app.services.race import analytics as analytics_mod

        monkeypatch.setattr(analytics_mod, "club_ranking", fake_ranking)

        out_md = tmp_path / "ranking.md"
        r = runner.invoke(
            cli_module.app,
            [
                "analyze",
                "ranking",
                "--season",
                "2026",
                "--output",
                str(out_md),
            ],
        )
        assert r.exit_code == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"

        stdout = r.stdout
        md_text = out_md.read_text(encoding="utf-8") if out_md.exists() else ""
        combined = stdout + "\n" + md_text

        leaked: list[str] = []
        for fragment in _name_fragments_to_check():
            if fragment in combined:
                leaked.append(fragment)
        assert not leaked, (
            f"Fragmentos TyR filtrados en `analyze ranking`: {sorted(leaked)}.\n"
            "El ranking debe ser agregado por categoría/tier — NO incluir "
            "competitors individuales.\n"
            f"STDOUT:\n{stdout}\n\nMARKDOWN:\n{md_text}"
        )


class TestRidersListDefaultMasksTyrNames:
    def test_riders_list_default_masks_oracle_names(
        self,
        runner,
        patched_session,
        event_meta_yaml,
        empty_decisions_yaml,
        valida_iv_resultados_pdf,
        valida_iv_general_pdf,
    ):
        """``riders list`` sin ``--show-names`` enmascara con inicial+apellido.

        El helper ``_mask_name("Thiago Duque Cardona")`` produce ``"T. Cardona"``.
        El stdout NO debe contener fragmentos largos del nombre original
        (``"Thiago"``, ``"Cardona"`` están bien por separado SÍ pueden
        aparecer porque "Cardona" es apellido y queda visible — pero
        ``"Thiago"`` (nombre completo) no debería verse). Verificamos el
        contrato más estricto: los apellidos compuestos largos como
        ``"Quiñones"`` (que en la versión enmascarada queda como apellido
        visible) sí aparecen — eso es comportamiento esperado del enmascarado.

        Lo crítico: el nombre completo NO debe aparecer. Esto es weaker que
        el sentinel de ingest porque ``_mask_name`` SÍ revela el último
        apellido. La validación es: el nombre COMPLETO (todos los tokens
        consecutivos) no aparece junto.
        """
        # Ingest TyR primero
        r0 = runner.invoke(
            cli_module.app,
            [
                "ingest",
                "--results",
                str(valida_iv_resultados_pdf),
                "--general",
                str(valida_iv_general_pdf),
                "--non-interactive",
                "--event-meta",
                str(event_meta_yaml),
                "--match-decisions",
                str(empty_decisions_yaml),
            ],
        )
        assert r0.exit_code == 0

        # riders list default — debe enmascarar
        r = runner.invoke(
            cli_module.app,
            ["riders", "list", "--tyr-only", "--limit", "50"],
        )
        assert r.exit_code == 0
        stdout = r.stdout

        # Ningún nombre COMPLETO (≥2 tokens consecutivos) debe aparecer.
        # _mask_name produce "T. Cardona" — el primer nombre "Thiago" no
        # aparece. Verificamos que no haya cadena tipo "Thiago Duque".
        for full in _TYR_FULL_NAMES_VALIDA_IV:
            tokens = full.split()
            if len(tokens) >= 2:
                first_two = f"{tokens[0]} {tokens[1]}"
                assert first_two not in stdout, (
                    f"Nombre completo filtrado en `riders list` default: "
                    f"{first_two!r}.\n"
                    "Debe usarse `_mask_name` (T. Apellido) salvo "
                    "`--show-names`.\n"
                    f"STDOUT:\n{stdout}"
                )
