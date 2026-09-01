"""T063 (feature 036, Wave 3 / US2): critic gana una regla de calidad NO

bloqueante para "enumeración sin conexión analítica".

El critic correctamente no es la causa de la calidad pobre del analyst
(spec.md US2: "The critic is not at fault"), pero puede volverse la red de
seguridad: si el analyst vuelve a producir una lista de datos sueltos sin
conectarlos, el critic debe señalarlo como issue de calidad — sin bloquear
la publicación (``must_block`` debe seguir en ``false`` y la severidad no
debe alcanzar ``high``, que es lo único que hitl_gate_review.py y
confidence.py tratan como bloqueante/degradante).
"""
from __future__ import annotations

from app.services.race.prompts import render_prompt


def _render(draft: str = "x", ground_truth: str = "sin condiciones registradas") -> str:
    return render_prompt(
        "race_critic_v2",
        {"draft_analysis": draft, "ground_truth": ground_truth},
        strict=False,
    )


def test_critic_prompt_names_enumeration_without_connection_as_quality_issue():
    out = _render()
    assert "enumeración sin conexión analítica" in out.lower(), (
        "Falta la regla de calidad que detecta datos enumerados sin "
        "conectar entre sí (T063)."
    )


def test_enumeration_rule_lives_under_non_blocking_quality_section():
    """La regla debe vivir bajo 'Reglas de calidad ... NO bloqueo', no bajo
    'Reglas inviolables' (que sí gatillan must_block=true)."""
    out = _render()
    quality_heading = "# Reglas de calidad (causan `approved=false` pero NO bloqueo)"
    assert quality_heading in out
    inviolable_heading = "# Reglas inviolables del club (causa de `must_block=true`)"
    assert inviolable_heading in out

    quality_start = out.index(quality_heading)
    inviolable_start = out.index(inviolable_heading)
    rule_pos = out.lower().index("enumeración sin conexión analítica")

    assert inviolable_start < quality_start, "El orden esperado de secciones cambió."
    assert rule_pos > quality_start, (
        "La regla de enumeración debe estar en la sección de calidad, "
        "no antes de ella."
    )
    # And it must not appear inside the must_block-triggering section.
    inviolable_block = out[inviolable_start:quality_start]
    assert "enumeración sin conexión analítica" not in inviolable_block.lower()
