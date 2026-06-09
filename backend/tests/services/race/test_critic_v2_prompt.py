"""US3 (feature 011): race_critic_v2 prompt validates v2 sections + ground truth."""
from __future__ import annotations

from app.services.race.prompts import render_prompt


def test_critic_v2_accepts_v2_sections():
    out = render_prompt(
        "race_critic_v2",
        {"draft_analysis": "## Qué pasó en esta válida\n...", "ground_truth": "x"},
        strict=False,
    )
    # Lists the v2 headings...
    assert "## Qué pasó en esta válida" in out
    assert "## Recorrido hasta acá" in out
    assert "## Hacia dónde va" in out
    # ...and explicitly does NOT penalize missing v1 sections.
    assert "NO penalices la ausencia de secciones del formato v1" in out


def test_critic_prompt_includes_ground_truth():
    gt = (
        "### Condiciones registradas\n- Superficie de la pista: Húmeda\n"
        "### Resultado del atleta (Válida 4)\n- Posición: 2\n"
        "### Podio (evento foco)\n- P1: 0:33:40"
    )
    out = render_prompt(
        "race_critic_v2",
        {"draft_analysis": "## Qué pasó en esta válida\n...", "ground_truth": gt},
        strict=False,
    )
    assert "Húmeda" in out
    assert "Posición: 2" in out
    assert "P1: 0:33:40" in out


def test_critic_v2_flags_fabricated_conditions_rule():
    out = render_prompt(
        "race_critic_v2",
        {"draft_analysis": "x", "ground_truth": "sin condiciones registradas"},
        strict=False,
    )
    assert "sin condiciones registradas" in out
    assert "fabricación" in out.lower() or "PROHIBIDO" in out or "high" in out
