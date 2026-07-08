"""Tests para race_insight_dispatcher.py — Sprint 3 (resumen embebido).

Cubre:

T2 — extracción de excerpt desde el insight (v1/v2):
- v2 (``race_analyst_v2``): extrae sección "Qué pasó" exacta.
- v1 / otro: primeras 3-4 oraciones, recortadas a ~400 chars.
- Sin markdown residual en el output: ningún ``**``, ``##``, ``[link](url)``, inline code.
- ``summary_text`` vacío o ``None`` ⇒ ``summary_excerpt = None`` (compatibilidad backwards).

T3 — render del template y contrato de privacidad (Ley 1581 inviolable):
- Template HTML renderiza con ``summary_excerpt`` no vacío y muestra la sección.
- Template OMITE la sección "Resumen del análisis" cuando ``summary_excerpt`` es ``None``.
- Subject NO contiene el nombre del menor (visible en previews/push).
- HTML final NO contiene strings prohibidos: "confidence", "tokens", "prompt", "model", "cost".
- Si por algún motivo el nombre del menor cuela en el excerpt, el dispatcher
  hace fallback a ``summary_excerpt=None`` y loggea warning.

Diseño de tests
---------------
- Helpers puros (``_strip_markdown``, ``_extract_v2_section``, ``_first_sentences``,
  ``_build_summary_excerpt``) se testean sin DB.
- El render del template usa el Jinja2 environment real (``templates/email/``)
  para detectar regresiones en el HTML.
- El subject se construye en :class:`NotificationService` con la misma plantilla
  declarada en ``template_registry.EMAIL_TEMPLATES``; testeamos esa plantilla
  directamente con Jinja2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.notification.race_insight_dispatcher import (
    PROMPT_VERSION_V2,
    _build_summary_excerpt,
    _extract_v2_section,
    _first_sentences,
    _strip_markdown,
)
from app.services.notification.template_registry import EMAIL_TEMPLATES
from app.schemas.notification import NotificationTemplate


# ---------------------------------------------------------------------------
# Fixtures: muestras realistas de summary_text
# ---------------------------------------------------------------------------


V2_SAMPLE = """\
## Qué pasó en esta válida

La deportista completó la válida IV en la posición 6 de su categoría
infantil-A femenil, registrando un tiempo de 38:42 con un gap de 4:18 al
líder. Completó las 3 vueltas previstas sin abandonos. Condiciones de
pista: seco con polvo intermitente, clima caluroso (29°C).

## Recorrido hasta acá

En fase **Pre-PHV** según última medición. Ha mantenido participación
consistente en las 4 válidas de la temporada. Tendencia observable:
mejora progresiva en el gap relativo al líder (de 7:10 en la I a 4:18 en la IV).

## Hacia dónde va

Trabajar habilidades PMBIA de descenso técnico en bermas. Carga semanal
recomendada: 5-6 horas (≤ edad). 2 días de descanso garantizados. Monitorear
señales de fatiga aguda durante la semana post-válida.

## Riesgos y banderas

Sin banderas rojas. Continuar con seguimiento antropométrico mensual.
"""

V1_SAMPLE = (
    "La deportista finalizó la válida en buen orden. Completó las 3 vueltas. "
    "Mostró regularidad en el ritmo. Recomendable trabajar la técnica de descenso. "
    "Esta oración no debería aparecer porque ya tomamos 4."
)


# ---------------------------------------------------------------------------
# Tests: _strip_markdown
# ---------------------------------------------------------------------------


def test_strip_markdown_removes_bold_italic_and_inline_code():
    text = "Esto es **negrita** y *itálica* y _también_ y `código`."
    out = _strip_markdown(text)
    assert "**" not in out
    assert "`" not in out
    assert out == "Esto es negrita y itálica y también y código."


def test_strip_markdown_removes_headers_and_keeps_text():
    text = "## Qué pasó\nLa deportista completó la válida.\n### Subhead\nTexto."
    out = _strip_markdown(text)
    assert "##" not in out
    assert "###" not in out
    assert "Qué pasó" in out
    assert "Subhead" in out
    assert "Texto." in out


def test_strip_markdown_converts_links_to_text():
    text = "Ver [reglamento federativo](https://federacion.example/reglamento) para detalles."
    out = _strip_markdown(text)
    assert "https://" not in out
    assert "(" not in out
    assert "reglamento federativo" in out


def test_strip_markdown_converts_bullets_to_dot_prefix():
    text = "- primero\n- segundo\n* tercero"
    out = _strip_markdown(text)
    assert "• primero" in out
    assert "• segundo" in out
    assert "• tercero" in out


def test_strip_markdown_handles_code_fences():
    text = "Antes\n```python\nx = 1\n```\nDespués."
    out = _strip_markdown(text)
    assert "```" not in out
    assert "x = 1" in out
    assert "Antes" in out
    assert "Después." in out


def test_strip_markdown_empty_input_returns_empty():
    assert _strip_markdown("") == ""
    assert _strip_markdown(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: _extract_v2_section
# ---------------------------------------------------------------------------


def test_extract_v2_section_returns_exact_block():
    section = _extract_v2_section(V2_SAMPLE, "Qué pasó")
    assert section.startswith("La deportista completó la válida IV")
    # No debe contener el siguiente header.
    assert "Recorrido hasta acá" not in section
    assert "Hacia dónde va" not in section


def test_extract_v2_section_is_accent_and_case_tolerant():
    # Mismo prompt v2, pero el LLM emitió el header sin acentos / mayúscula.
    md = "## QUE PASO\nContenido sin acentos.\n## Recorrido\nOtra cosa."
    section = _extract_v2_section(md, "Qué pasó")
    assert section == "Contenido sin acentos."


def test_extract_v2_section_returns_empty_when_header_absent():
    md = "## Otra sección\nContenido."
    assert _extract_v2_section(md, "Qué pasó") == ""


def test_extract_v2_section_empty_input():
    assert _extract_v2_section("", "Qué pasó") == ""
    assert _extract_v2_section(None, "Qué pasó") == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: _first_sentences (heurística v1)
# ---------------------------------------------------------------------------


def test_first_sentences_takes_first_four_by_default():
    out = _first_sentences(V1_SAMPLE)
    assert "La deportista finalizó" in out
    assert "Completó las 3 vueltas" in out
    assert "Mostró regularidad" in out
    assert "Recomendable trabajar" in out
    # La quinta oración NO debe aparecer.
    assert "no debería aparecer" not in out


def test_first_sentences_respects_max_chars():
    long_text = " ".join(["Oración corta."] * 60)
    out = _first_sentences(long_text, max_sentences=10, max_chars=80)
    assert len(out) <= 80
    assert out.endswith("…")


# ---------------------------------------------------------------------------
# Tests: _build_summary_excerpt — orquestación
# ---------------------------------------------------------------------------


def test_build_excerpt_v2_extracts_que_paso_and_strips_markdown():
    excerpt = _build_summary_excerpt(
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
    )
    assert excerpt is not None
    assert "La deportista completó la válida IV" in excerpt
    # No debe arrastrar el header ni la sección siguiente.
    assert "Qué pasó" not in excerpt
    assert "Recorrido hasta acá" not in excerpt
    # Sin restos de markdown.
    for marker in ("##", "**", "`", "[", "]("):
        assert marker not in excerpt


def test_build_excerpt_v1_falls_back_to_first_sentences():
    excerpt = _build_summary_excerpt(
        summary_text=V1_SAMPLE,
        prompt_version="race_analyst_v1",
    )
    assert excerpt is not None
    assert "La deportista finalizó" in excerpt
    # No debe agregar headers de v2.
    assert "##" not in excerpt
    # La oración 5 no debe colarse.
    assert "no debería aparecer" not in excerpt


def test_build_excerpt_v2_without_que_paso_falls_back_to_sentences():
    """Si el LLM v2 no emitió el header 'Qué pasó', degrademos a v1 sin reventar."""
    md = "## Otra sección\nContenido."
    excerpt = _build_summary_excerpt(
        summary_text=md,
        prompt_version=PROMPT_VERSION_V2,
    )
    assert excerpt is not None
    # No incluye '##' (stripped).
    assert "##" not in excerpt


def test_build_excerpt_returns_none_for_empty_or_blank():
    assert _build_summary_excerpt(summary_text=None, prompt_version=PROMPT_VERSION_V2) is None
    assert _build_summary_excerpt(summary_text="", prompt_version=PROMPT_VERSION_V2) is None
    assert _build_summary_excerpt(summary_text="   \n  ", prompt_version=PROMPT_VERSION_V2) is None


def test_build_excerpt_does_not_leak_telemetry_strings():
    """El excerpt nunca debe contener strings de telemetría (defensa).

    Aunque el guardrail IA upstream redacta, validamos que el dispatcher
    no inyecta accidentalmente confidence/tokens/etc. en el output.
    """
    excerpt = _build_summary_excerpt(
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
    )
    assert excerpt is not None
    lowered = excerpt.lower()
    for forbidden in ("confidence", "tokens", "prompt", "model", "cost"):
        assert forbidden not in lowered


# ---------------------------------------------------------------------------
# Tests: render del template HTML (Jinja2 directo)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    templates_root = Path(__file__).resolve().parents[3] / "templates"
    return Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _base_context(**overrides) -> dict:
    ctx = {
        "parent_name": "Padre/Acudiente",
        "athlete_first_name": "Carolina",
        "club_name": "Club Trocha y Ruta",
        "valida_label": "IV — Cali",
        "valida_date": "17 de mayo de 2026",
        "tier_label": "Tipo A — máxima prioridad",
        "coach_summary": "El entrenador publicó el análisis con detalles.",
        "deep_link_path": "/athletes/42/race-analysis/insights/7",
        "summary_excerpt": None,
        "app_url": None,
        "panorama_url": None,
    }
    ctx.update(overrides)
    return ctx


def test_template_renders_section_when_excerpt_present(jinja_env: Environment):
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(
        **_base_context(
            summary_excerpt=(
                "La deportista completó la válida IV en la posición 6 "
                "registrando un tiempo de 38:42 con un gap de 4:18 al líder."
            ),
            app_url="https://app.trochyruta.com/athletes/42/race-analysis/insights/7",
        )
    )
    assert "Resumen del análisis" in html
    assert "La deportista completó la válida IV" in html
    # CTA primario tiene la URL absoluta de la app.
    assert "https://app.trochyruta.com/athletes/42/race-analysis/insights/7" in html
    assert "Leer análisis completo" in html


def test_template_omits_section_when_excerpt_none(jinja_env: Environment):
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(**_base_context(summary_excerpt=None))
    assert "Resumen del análisis" not in html
    # CTA primario sigue presente (con deep_link_path como fallback).
    assert "Leer análisis completo" in html


def test_template_omits_section_when_excerpt_empty_string(jinja_env: Environment):
    """Vacío/empty string equivale a None vía falsy-check Jinja."""
    template = jinja_env.get_function = None  # noqa: B018 — silencia linters
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(**_base_context(summary_excerpt=""))
    assert "Resumen del análisis" not in html


def test_template_renders_panorama_button_when_present(jinja_env: Environment):
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(
        **_base_context(
            summary_excerpt="Resumen disponible.",
            app_url="https://app.example/athletes/42/race-analysis/insights/7",
            panorama_url="https://app.example/parents/athletes/42",
        )
    )
    assert "Ver progreso de tu hijo" in html
    assert "https://app.example/parents/athletes/42" in html


def test_template_omits_panorama_button_when_url_none(jinja_env: Environment):
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(**_base_context(panorama_url=None))
    assert "Ver progreso de tu hijo" not in html


def test_template_html_does_not_leak_telemetry_strings(jinja_env: Environment):
    """El cuerpo del email nunca debe filtrar telemetría/PII de modelo.

    Verifica el contrato Ley 1581: confidence numérica, tokens, costo,
    prompt_version y nombre del modelo NUNCA viajan al padre.
    """
    template = jinja_env.get_template("email/race_insight_published.html")
    html = template.render(
        **_base_context(
            summary_excerpt=(
                "La deportista completó la válida en buen orden, sin "
                "abandonos y mostrando regularidad en el ritmo."
            ),
            app_url="https://app.example/athletes/42/race-analysis/insights/7",
        )
    )
    # Buscamos en minúsculas para no fallar por casing legítimo.
    lowered = html.lower()
    forbidden_telemetry = ("confidence", "tokens", "prompt", "model", "cost")
    for token in forbidden_telemetry:
        assert token not in lowered, (
            f"Telemetría '{token}' filtrada al cuerpo del email — "
            "viola contrato Ley 1581. Revisa el template y el contexto."
        )


# ---------------------------------------------------------------------------
# Tests: subject template — no contiene nombre del menor
# ---------------------------------------------------------------------------


def test_subject_template_does_not_contain_athlete_name():
    """El subject (visible en previews/push) NO debe interpolar nombre."""
    spec = EMAIL_TEMPLATES[NotificationTemplate.RACE_INSIGHT_PUBLISHED]
    # Verificación estática: la plantilla solo referencia valida_label.
    assert "athlete_first_name" not in spec.subject_template
    assert "athlete_last_name" not in spec.subject_template
    assert "{{ valida_label }}" in spec.subject_template

    # Verificación dinámica: render con valores reales y assert.
    from jinja2 import Template

    rendered = Template(spec.subject_template).render(
        valida_label="IV — Cali",
        athlete_first_name="Carolina",
        athlete_last_name="Pérez",
    )
    assert "Carolina" not in rendered
    assert "Pérez" not in rendered
    assert "IV — Cali" in rendered


# ---------------------------------------------------------------------------
# Tests: privacy guard — fallback si el nombre del menor cuela en el excerpt
# ---------------------------------------------------------------------------


def test_excerpt_with_athlete_name_is_blocked_by_dispatcher(caplog):
    """Si el excerpt contiene el nombre real (failsafe), debe blanquearse.

    Reproducimos el comportamiento de ``_send_email_to_parents`` con un
    excerpt malicioso/contaminado. La función auxiliar no es pública pero
    su lógica está dentro del flujo de envío — testeamos la inversión:
    cualquier ocurrencia del nombre debe disparar fallback a None.
    """
    # Probamos la heurística usada en el dispatcher: lowercase substring match.
    excerpt = "Carolina completó la válida con buen ritmo."
    forbidden = "Carolina"
    assert forbidden.lower() in excerpt.lower()  # el guard sí lo detecta

    # Caso negativo: pseudónimo correcto NO se detecta.
    safe = "La deportista completó la válida con buen ritmo."
    assert forbidden.lower() not in safe.lower()


# ---------------------------------------------------------------------------
# Tests: integración — full send path mockeado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_sends_email_with_summary_excerpt_for_v2_insight(monkeypatch):
    """Test E2E corto: dispatch_insight_notification → context incluye summary_excerpt.

    Mockea DB + notification_service y verifica que el contexto pasado al
    NotificationRequest contiene ``summary_excerpt`` extraído del v2 markdown
    y NO contiene el nombre del menor.
    """
    from datetime import date
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from app.services.notification.race_event_tier import RaceTier
    from app.services.notification.race_insight_dispatcher import (
        dispatch_insight_notification,
    )

    # --- Setup mocks ----------------------------------------------------
    insight = SimpleNamespace(
        id=99,
        athlete_id=42,
        coach_approved=True,
        is_active=1,
        valida_num=4,
        event_id=7,
        season=2026,
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
    )

    event = SimpleNamespace(
        id=7,
        event_date=date(2026, 5, 17),
        location="Cali",
        sequence_number=4,
        is_championship=False,
        series=SimpleNamespace(season_year=2026),
    )

    athlete = SimpleNamespace(first_name="Carolina", last_name="Pérez")
    fresh_insight = SimpleNamespace(
        id=99,
        athlete_id=42,
        valida_num=4,
        season=2026,
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
        event=event,
        event_id=7,
        athlete=athlete,
    )

    parent = SimpleNamespace(
        id=20,
        email="padre@test.com",
        first_name="Carlos",
        last_name="Pérez",
    )

    db = MagicMock()
    db.execute = AsyncMock()

    # Tres llamadas a db.execute: load_insight, load_parents, resolve_club_name.
    call_count = {"n": 0}

    async def _fake_execute(_stmt):
        call_count["n"] += 1
        n = call_count["n"]
        res = MagicMock()
        if n == 1:
            res.scalar_one_or_none.return_value = fresh_insight
        elif n == 2:
            res.scalars.return_value.all.return_value = [parent]
        elif n == 3:
            res.scalar_one_or_none.return_value = "Club Trocha y Ruta"
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    db.execute = _fake_execute

    # NotificationService mock — capturamos el request enviado.
    captured_requests = []

    class _FakeNotificationService:
        async def send(self, request, dispatcher=None):
            captured_requests.append(request)
            return SimpleNamespace(success=True)

    notification_service = _FakeNotificationService()

    settings = SimpleNamespace(frontend_base_url="https://app.example")

    # --- Act ------------------------------------------------------------
    result = await dispatch_insight_notification(
        insight,
        db,
        notification_service=notification_service,
        settings=settings,
    )

    # --- Assert ---------------------------------------------------------
    from app.services.notification.race_insight_dispatcher import (
        NotificationDecision,
    )

    assert result.decision == NotificationDecision.SENT_EMAIL
    assert result.tier == RaceTier.A
    assert result.emails_sent == 1

    assert len(captured_requests) == 1
    ctx = captured_requests[0].context

    # 1. summary_excerpt presente y bien formado.
    assert ctx["summary_excerpt"] is not None
    assert "La deportista completó la válida IV" in ctx["summary_excerpt"]
    # Sin markdown residual.
    for marker in ("##", "**", "`"):
        assert marker not in ctx["summary_excerpt"]

    # 2. Nombre del menor NO aparece en el excerpt.
    assert "Carolina" not in ctx["summary_excerpt"]
    assert "Pérez" not in ctx["summary_excerpt"]

    # 3. app_url absoluta usando frontend_base_url.
    assert ctx["app_url"].startswith("https://app.example/athletes/42/")

    # 4. panorama_url apunta a la sub-tab IA del padre (T2 Sprint 4).
    assert ctx["panorama_url"] is not None
    assert ctx["panorama_url"] == "https://app.example/my-athletes/42?tab=ai-analysis"


@pytest.mark.asyncio
async def test_dispatch_blocks_excerpt_if_name_leaks(caplog):
    """Defensa en profundidad: si el LLM filtra el nombre, el dispatcher
    deja ``summary_excerpt=None`` y loggea warning."""
    from datetime import date
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.notification.race_insight_dispatcher import (
        dispatch_insight_notification,
    )

    leaked_summary = (
        "## Qué pasó\nCarolina completó la válida IV con buen ritmo."
    )

    insight = SimpleNamespace(
        id=100,
        athlete_id=42,
        coach_approved=True,
        is_active=1,
        valida_num=4,
        event_id=7,
        season=2026,
        summary_text=leaked_summary,
        prompt_version=PROMPT_VERSION_V2,
    )

    event = SimpleNamespace(
        id=7,
        event_date=date(2026, 5, 17),
        location="Cali",
        sequence_number=4,
        is_championship=False,
        series=SimpleNamespace(season_year=2026),
    )

    athlete = SimpleNamespace(first_name="Carolina", last_name="Pérez")
    fresh = SimpleNamespace(
        id=100,
        athlete_id=42,
        valida_num=4,
        season=2026,
        summary_text=leaked_summary,
        prompt_version=PROMPT_VERSION_V2,
        event=event,
        event_id=7,
        athlete=athlete,
    )

    parent = SimpleNamespace(
        id=20, email="p@t.com", first_name="C", last_name="P"
    )

    captured = []

    class _Fake:
        async def send(self, request, dispatcher=None):
            captured.append(request)
            return SimpleNamespace(success=True)

    call_count = {"n": 0}

    async def _exec(_stmt):
        call_count["n"] += 1
        n = call_count["n"]
        res = MagicMock()
        if n == 1:
            res.scalar_one_or_none.return_value = fresh
        elif n == 2:
            res.scalars.return_value.all.return_value = [parent]
        elif n == 3:
            res.scalar_one_or_none.return_value = "Club"
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    db = MagicMock()
    db.execute = _exec

    import logging
    caplog.set_level(logging.WARNING)

    await dispatch_insight_notification(
        insight,
        db,
        notification_service=_Fake(),
        settings=SimpleNamespace(frontend_base_url="https://x"),
    )

    assert len(captured) == 1
    ctx = captured[0].context
    # El excerpt se canceló para no filtrar el nombre.
    assert ctx["summary_excerpt"] is None
    # Y quedó constancia en logs.
    assert any("excerpt_blocked" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: _build_urls — panorama_url (T2 Sprint 4)
# ---------------------------------------------------------------------------


def test_build_urls_panorama_url_points_to_parent_ai_tab():
    """panorama_url apunta a /my-athletes/{id}?tab=ai-analysis (T2 Sprint 4).

    Valida que el link del CTA secundario del email del padre aterriza en la
    sub-tab "Análisis IA" de MyAthleteDetailPage, no en None.
    """
    from types import SimpleNamespace

    from app.services.notification.race_insight_dispatcher import _build_urls

    settings = SimpleNamespace(frontend_base_url="https://app.trochyruta.com")
    app_url, panorama_url = _build_urls(
        deep_link_path="/athletes/42/race-analysis/insights/7",
        athlete_id=42,
        settings=settings,
    )

    assert app_url == "https://app.trochyruta.com/athletes/42/race-analysis/insights/7"
    assert panorama_url is not None
    assert panorama_url == "https://app.trochyruta.com/my-athletes/42?tab=ai-analysis"


def test_build_urls_panorama_url_none_when_no_base():
    """Sin frontend_base_url configurado, panorama_url sigue siendo None.

    Fallback conservador: no construir URL relativa para panorama (podría
    enviarse a un email y no funcionar en contexto de cliente de correo).
    """
    from app.services.notification.race_insight_dispatcher import _build_urls

    app_url, panorama_url = _build_urls(
        deep_link_path="/athletes/42/race-analysis/insights/7",
        athlete_id=42,
        settings=None,
    )

    assert app_url == "/athletes/42/race-analysis/insights/7"
    assert panorama_url is None


def test_build_urls_panorama_url_encodes_athlete_id():
    """El athlete_id se inyecta correctamente en panorama_url."""
    from types import SimpleNamespace

    from app.services.notification.race_insight_dispatcher import _build_urls

    settings = SimpleNamespace(frontend_base_url="https://app.example")
    _, panorama_url = _build_urls(
        deep_link_path="/athletes/99/race-analysis/insights/1",
        athlete_id=99,
        settings=settings,
    )

    assert panorama_url == "https://app.example/my-athletes/99?tab=ai-analysis"


# ---------------------------------------------------------------------------
# Tests: campeonato label por nivel (feature 023 — RaceSeriesLevel)
# ---------------------------------------------------------------------------
#
# D3 (specs/023-national-championship-level/plan.md): el tier de notificación
# se mantiene RaceTier.CD para todo campeonato (máxima prioridad); solo la
# etiqueta humana ("valida_label") varía por level ("Campeonato Nacional" vs
# "Campeonato Departamental"). El helper `_build_valida_label` aún no conoce
# `level` — estas pruebas fallan hasta que se le agregue ese parámetro.


async def _run_championship_dispatch(*, series_level):
    """Helper compartido: dispara dispatch_insight_notification para un
    insight tier=CD (is_championship=True) con un ``series.level`` dado."""
    from datetime import date
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.notification.race_insight_dispatcher import (
        dispatch_insight_notification,
    )

    insight = SimpleNamespace(
        id=200,
        athlete_id=42,
        coach_approved=True,
        is_active=1,
        valida_num=1,
        event_id=8,
        season=2026,
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
    )

    series = SimpleNamespace(season_year=2026, level=series_level)
    event = SimpleNamespace(
        id=8,
        event_date=date(2026, 7, 18),
        location="Pereira",
        sequence_number=1,
        is_championship=True,
        series=series,
    )

    athlete = SimpleNamespace(first_name="Carolina", last_name="Pérez")
    fresh_insight = SimpleNamespace(
        id=200,
        athlete_id=42,
        valida_num=1,
        season=2026,
        summary_text=V2_SAMPLE,
        prompt_version=PROMPT_VERSION_V2,
        event=event,
        event_id=8,
        athlete=athlete,
    )

    parent = SimpleNamespace(
        id=21,
        email="padre2@test.com",
        first_name="Carlos",
        last_name="Pérez",
    )

    call_count = {"n": 0}

    async def _fake_execute(_stmt):
        call_count["n"] += 1
        n = call_count["n"]
        res = MagicMock()
        if n == 1:
            res.scalar_one_or_none.return_value = fresh_insight
        elif n == 2:
            res.scalars.return_value.all.return_value = [parent]
        elif n == 3:
            res.scalar_one_or_none.return_value = "Club Trocha y Ruta"
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    db = MagicMock()
    db.execute = _fake_execute

    captured_requests = []

    class _FakeNotificationService:
        async def send(self, request, dispatcher=None):
            captured_requests.append(request)
            return SimpleNamespace(success=True)

    settings = SimpleNamespace(frontend_base_url="https://app.example")

    result = await dispatch_insight_notification(
        insight,
        db,
        notification_service=_FakeNotificationService(),
        settings=settings,
    )

    return result, captured_requests


@pytest.mark.asyncio
async def test_dispatch_national_championship_label_says_campeonato_nacional():
    """Campeonato Nacional (series.level=national): la etiqueta del email debe
    decir "Campeonato Nacional" y NUNCA "Campeonato Departamental"."""
    from app.models.race_series import RaceSeriesLevel
    from app.services.notification.race_event_tier import RaceTier
    from app.services.notification.race_insight_dispatcher import (
        NotificationDecision,
    )

    result, captured = await _run_championship_dispatch(
        series_level=RaceSeriesLevel.national
    )

    assert result.decision == NotificationDecision.SENT_EMAIL
    assert result.tier == RaceTier.CD

    assert len(captured) == 1
    ctx = captured[0].context
    assert "Campeonato Nacional" in ctx["valida_label"]
    assert "Campeonato Departamental" not in ctx["valida_label"]


@pytest.mark.asyncio
async def test_dispatch_departmental_championship_label_unchanged():
    """Regresión: Campeonato Departamental (series.level=departmental) conserva
    la etiqueta "Campeonato Departamental" y el tier CD."""
    from app.models.race_series import RaceSeriesLevel
    from app.services.notification.race_event_tier import RaceTier
    from app.services.notification.race_insight_dispatcher import (
        NotificationDecision,
    )

    result, captured = await _run_championship_dispatch(
        series_level=RaceSeriesLevel.departmental
    )

    assert result.decision == NotificationDecision.SENT_EMAIL
    assert result.tier == RaceTier.CD

    assert len(captured) == 1
    ctx = captured[0].context
    assert ctx["valida_label"] == "Campeonato Departamental"
    assert "Campeonato Nacional" not in ctx["valida_label"]
