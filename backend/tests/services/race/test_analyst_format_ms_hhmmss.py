"""Regression (feature 036, Wave 3 / US2): ``_format_ms_hhmmss`` con signo.

Bug encontrado durante la integración de T059: ``divmod`` sobre un total de
segundos NEGATIVO trunca hacia -infinito (semántica estándar de Python), así
que restar la hora entera producía una hora corrida en vez de preservar el
signo — p. ej. ``-30_000`` ms (30 s de mejora) se mostraba como ``-1:59:30``
en lugar de ``-0:00:30``.

El único caller real que puede pasar un valor negativo es
``_build_v2_context`` formateando ``delta_time_ms`` de
``AnalysisInput.season_comparative`` (T014) — es decir, dispara en CADA
comparación válida-sobre-válida donde el atleta mejoró su tiempo, uno de los
casos centrales que esta ola del feature 036 existe para habilitar
(spec.md US2, escenario 1: "el texto ... nombra la dirección del cambio").
``race_time_ms`` y ``gap_to_winner_ms`` nunca son negativos por construcción
del dominio, así que ``delta_time_ms`` es el único caso realista.
"""
from __future__ import annotations

from app.services.race.agents.analyst import _format_ms_hhmmss


def test_format_ms_hhmmss_positive_unchanged():
    """Caso ya cubierto implícitamente por otros tests — control positivo."""
    assert _format_ms_hhmmss(30_000) == "0:00:30"
    assert _format_ms_hhmmss(3_600_000) == "1:00:00"


def test_format_ms_hhmmss_negative_preserves_sign_and_magnitude():
    """-30 s debe mostrarse como ``-0:00:30``, no como ``-1:59:30``."""
    assert _format_ms_hhmmss(-30_000) == "-0:00:30"


def test_format_ms_hhmmss_negative_over_a_minute():
    """-90 s (1:30) debe mostrarse como ``-0:01:30``."""
    assert _format_ms_hhmmss(-90_000) == "-0:01:30"


def test_format_ms_hhmmss_negative_over_an_hour():
    """-1h01m05s debe conservar el signo en la componente de horas."""
    assert _format_ms_hhmmss(-3_665_000) == "-1:01:05"


def test_format_ms_hhmmss_zero_has_no_sign():
    assert _format_ms_hhmmss(0) == "0:00:00"


def test_format_ms_hhmmss_none_and_blank_unaffected_by_sign_fix():
    """El control de vacío/no numérico sigue devolviendo el placeholder."""
    assert _format_ms_hhmmss(None) == "—"
    assert _format_ms_hhmmss("") == "—"
    assert _format_ms_hhmmss("<NA>") == "—"
    assert _format_ms_hhmmss("no-es-un-numero") == "—"
