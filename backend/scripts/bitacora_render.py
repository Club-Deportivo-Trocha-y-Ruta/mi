"""Valida una narrativa escrita a mano/por Claude Code contra los guardrails
del producto y renderiza el PDF de la bitácora de etapa (feature 038).

No toca la base de datos: todo sale de ``snapshot.json`` + ``brief.md``
(generados por ``bitacora_snapshot.py``) y ``narrative.json`` (escrito por el
skill ``bitacora-pdf``).

Uso (desde ``backend/`` con el venv activo)::

    python scripts/bitacora_render.py --dir ../output/bitacora/2026-08/athlete-12
    python scripts/bitacora_render.py --dir ... --coach-note "Texto en primera persona"
    python scripts/bitacora_render.py --dir ... --hide photos,badges
    python scripts/bitacora_render.py --dir ... --check   # solo guardrails, sin PDF

Salida en la misma carpeta: ``bitacora.pdf``, ``stage_log.json`` (DTO de
familia) y ``violations.json``. Código de salida 2 si algún bloque cayó a
copy estático por guardrails — corrige ``narrative.json`` y vuelve a correr.

Guardrails aplicados (idénticos al use case v2 del producto): nombres
prohibidos del club, términos médicos/nutricionales, frases prohibidas,
grounding numérico contra ``brief.md``, solapamiento con el mes anterior y
límite de palabras por bloque.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_MODEL_LABEL = "claude-code/bitacora-pdf"


def _ensure_weasyprint_libs() -> None:
    """WeasyPrint en macOS necesita las libs de Homebrew visibles para dyld.
    dyld solo lee DYLD_* al arrancar, así que re-ejecutamos si falta."""
    if sys.platform != "darwin" or os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
        return
    brew_lib = "/opt/homebrew/lib"
    if os.path.isdir(brew_lib):
        env = {**os.environ, "DYLD_FALLBACK_LIBRARY_PATH": brew_lib}
        os.execve(sys.executable, [sys.executable, *sys.argv], env)


def _load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Falta {path}")
    return json.loads(path.read_text(encoding="utf-8"))


async def _render(args: argparse.Namespace) -> int:
    folder = Path(args.dir)
    snap = _load_json(folder / "snapshot.json")
    brief = (folder / "brief.md").read_text(encoding="utf-8")
    narrative_raw = _load_json(folder / "narrative.json") if (folder / "narrative.json").exists() else None

    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        StageNarrative,
        StageNarrativeGuardrails,
        _accept_analyst_reading,
        _accept_family_compass,
        _accept_observations,
        _accept_text_field,
    )
    from app.services.race.insight_v3 import extract_numeric_tokens
    from app.services.training.stage_log import StageLog, to_parent_dto
    from app.services.training.stage_log_builder import build_stage_log

    athlete = snap["athlete"]
    year, month = snap["period"]["year"], snap["period"]["month"]
    forbidden = frozenset(snap["forbidden_names"])
    family_input = snap.get("family_input")

    narrative = None
    violations: list[str] = []
    if narrative_raw is not None and athlete["has_ai_consent"]:
        guardrails = StageNarrativeGuardrails(
            forbidden_names=forbidden,
            grounding_numbers=extract_numeric_tokens(brief),
            previous_stage_text=snap.get("previous_stage_text"),
        )
        stage_title = _accept_text_field("stage_title", narrative_raw.get("stage_title"), guardrails, violations)
        summit_caption = _accept_text_field("summit_caption", narrative_raw.get("summit_caption"), guardrails, violations)
        next_segment_text = _accept_text_field("next_segment_text", narrative_raw.get("next_segment_text"), guardrails, violations)
        observations = _accept_observations(narrative_raw.get("observations"), guardrails, violations)
        family_compass = _accept_family_compass(narrative_raw.get("family_compass"), guardrails, violations)
        analyst_reading = (
            _accept_analyst_reading(narrative_raw.get("analyst_reading"), guardrails, violations)
            if family_input is not None
            else None
        )
        narrative = StageNarrative(
            stage_title=stage_title,
            summit_caption=summit_caption,
            observations=observations,
            next_segment_text=next_segment_text,
            family_compass=family_compass,
            analyst_reading=analyst_reading,
            model=_MODEL_LABEL,
            confidence=snap["confidence"],
            grounding_violations=violations,
        )
    elif narrative_raw is not None:
        violations.append("narrative:skipped_no_ai_consent")

    hidden = [h.strip() for h in (args.hide or "").split(",") if h.strip()] or None
    # Misma regla que el PATCH del router: la nota del coach pasa por
    # redacción de nombres antes de tocar el StageLog.
    from app.services.ai.use_cases.monthly_report import _redact_names

    coach_note = _redact_names(args.coach_note.strip(), forbidden) if args.coach_note else None
    stage_log: StageLog = build_stage_log(
        snap["metrics_snapshot"],
        narrative,
        family_input,
        None,
        coach_note,
        hidden,
        athlete["sex"],
        athlete["first_name"],
    )
    if violations:
        stage_log.grounding_violations = list(violations)

    parent_dto = to_parent_dto(stage_log, hidden)
    (folder / "stage_log.json").write_text(
        json.dumps(parent_dto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "violations.json").write_text(
        json.dumps(violations, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    static_blocks = [
        name
        for name, state in (stage_log.model_dump().get("block_states") or {}).items()
        if state == "static"
    ]
    print(f"athlete-{athlete['id']} · {snap['period']['label']}")
    print(f"  bloques en estático: {', '.join(static_blocks) or 'ninguno'}")
    if violations:
        print("  violaciones de guardrails:")
        for v in violations:
            print(f"    - {v}")

    if args.check:
        return 2 if violations else 0

    from app.config import settings
    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf
    from app.services.notification.document_generator import DocumentGenerator
    from app.services.notification.template_registry import TemplateRegistry

    generator = DocumentGenerator(registry=TemplateRegistry(), settings=settings)
    pdf_only = snap["metrics_snapshot"].get("pdf_only_blocks", {})
    email_blocks = snap["metrics_snapshot"].get("email_blocks", {})
    doc, sha256 = await generate_stage_log_pdf(
        generator,
        athlete_first_name=athlete["first_name"],
        athlete_last_name=athlete["last_name"],
        athlete_id=athlete["id"],
        year=year,
        month=month,
        stage_log=parent_dto,
        anthropometry=pdf_only.get("anthropometry"),
        charts_context=pdf_only.get("charts_context"),
        percentile_curves=pdf_only.get("percentile_curves"),
        race_results=email_blocks.get("race_results"),
    )
    pdf_path = folder / "bitacora.pdf"
    pdf_path.write_bytes(doc.data)
    print(f"  PDF: {pdf_path} ({len(doc.data) // 1024} KB, sha256 {sha256[:12]}…)")
    return 2 if violations else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="carpeta athlete-<id> con snapshot.json, brief.md y narrative.json")
    parser.add_argument("--coach-note", default=None, help="nota del entrenador en primera persona (≤ 60 palabras)")
    parser.add_argument("--hide", default=None, help="bloques a ocultar: analyst_reading,photos,badges,coach_note")
    parser.add_argument("--check", action="store_true", help="solo valida guardrails, no genera PDF")
    args = parser.parse_args()

    if not args.check:
        _ensure_weasyprint_libs()
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("AI_ENABLED", "false")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    return asyncio.run(_render(args))


if __name__ == "__main__":
    sys.exit(main())
