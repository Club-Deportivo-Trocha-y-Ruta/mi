"""T203 — Tests para el PDF de la bitácora de etapa (feature 038, v2).

Cubre (spec: specs/038-newsletter-bitacora-redesign/tasks.md T203):
  - Conteo de páginas ≤ 3 sobre tres fixtures (mes completo, mes sin
    carrera, mes de cero asistencia) construidas directamente como
    ``StageLog`` (sin depender del builder de la Wave 1).
  - El "Anexo de crecimiento" (página 3) solo aparece cuando hay una
    medición antropométrica fechada en el mes.
  - Los gráficos de temporada del anexo solo aparecen cuando la cima del
    mes vino de una carrera (``summit.kind == "race"``).
  - ``stage_log`` viaja ya proyectado con ``to_parent_dto()`` — el PDF nunca
    debe imprimir claves de uso exclusivo del coach.

NOTA DE ENTORNO: estos tests renderizan con WeasyPrint. En esta máquina
(macOS sin libgobject-2.0-0) fallan por la misma causa preexistente que
``test_newsletter_pdf_layout.py`` (ver baseline de la tarea) — no es un bug
de este módulo. Además, ``pypdf`` no está instalado en este venv (a pesar de
lo indicado en la tarea); se usa ``pdfplumber`` para contar páginas, igual
que el test v1 ya existente en este mismo directorio.
"""

from __future__ import annotations

import io
from datetime import date

import pdfplumber
import pytest

from app.services.notification.athlete_newsletter_pdf import (
    _build_stage_log_pdf_context,
    generate_stage_log_pdf,
)
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.template_registry import TemplateRegistry
from app.services.training.stage_log import (
    AnalystReading,
    BadgeView,
    EffortWeek,
    FamilyCompass,
    NextRace,
    NextSegment,
    Observation,
    PhotoView,
    StageLog,
    Summit,
    SummitKind,
    Waypoint,
    WaypointKind,
    to_parent_dto,
)

# ---------------------------------------------------------------------------
# Fixtures — StageLog construido directamente (sin builder), como pide T203.
# ---------------------------------------------------------------------------


def _full_month_stage_log() -> StageLog:
    """Mes completo: carrera, insignias, racha, fotos y nota del entrenador."""
    return StageLog(
        stage_number=6,
        period_label="Junio 2026",
        is_current_month=False,
        athlete_first_name="Atleta",
        athlete_reference="su hijo",
        stage_title="Una etapa sólida con la mejor carrera de la temporada",
        trail=[
            Waypoint(
                kind=WaypointKind.FIRST_SESSION,
                date=date(2026, 6, 2),
                label="Primera sesión de la temporada",
                icon="flag",
            ),
            Waypoint(
                kind=WaypointKind.RACE,
                date=date(2026, 6, 15),
                label="Válida 3 · P2",
                sublabel="+4,1 % al P1",
                icon="map-pin",
            ),
            Waypoint(
                kind=WaypointKind.BADGE,
                date=date(2026, 6, 20),
                label="Asistencia 100 %",
                icon="award",
            ),
            Waypoint(
                kind=WaypointKind.NEXT_RACE,
                date=date(2026, 7, 10),
                label="Próxima: Válida 4",
                sublabel="Ginebra",
                icon="compass",
                is_future=True,
            ),
        ],
        summit=Summit(
            kind=SummitKind.RACE,
            title="P2 en la Válida 3",
            detail="Prejuvenil A Femenino · +4,1 % al P1",
            caption="Subió dos puestos respecto al mes pasado.",
            date=date(2026, 6, 15),
        ),
        observations=[
            Observation(
                claim="Asistió a 14 de 14 sesiones planificadas este mes.",
                evidence="14/14 sesiones (100 %).",
                block_ref="attendance",
            ),
            Observation(
                claim="Mejoró la frenada en curva cerrada en las últimas sesiones.",
                evidence="Rúbrica técnica subió de 3,2 a 4,1 sobre 5.",
                block_ref="technical",
            ),
            Observation(
                claim="Logró su mejor resultado de la temporada en la Válida 3.",
                evidence="P2, a 4,1 % del primer lugar.",
                block_ref="race",
            ),
        ],
        analyst_reading=AnalystReading(
            headline_family="Mantuvo el ritmo del grupo de punta toda la carrera.",
            action_family="Practicar la salida en pendiente antes de la próxima válida.",
            valida_label="Válida 3 · Copa Valle",
            source_insight_id=99,
        ),
        effort_profile=[
            EffortWeek(week_label="1–7 jun", sessions_planned=3, sessions_attended=3, mean_rpe=4.5),
            EffortWeek(week_label="8–14 jun", sessions_planned=3, sessions_attended=3, mean_rpe=5.0),
            EffortWeek(week_label="15–21 jun", sessions_planned=4, sessions_attended=4, mean_rpe=6.0),
            EffortWeek(week_label="22–30 jun", sessions_planned=4, sessions_attended=4, mean_rpe=4.0),
        ],
        next_segment=NextSegment(
            focus_groups=["Frenada", "Curvas largas"],
            next_race=NextRace(label="Válida 4", date=date(2026, 7, 10), venue="Ginebra", priority_label="Prioridad A"),
            text="Seguimos trabajando frenada y curvas antes de la Válida 4 en Ginebra.",
        ),
        family_compass=FamilyCompass(
            conversation_question="¿Qué fue lo que más disfrutó de la carrera este mes?",
            monthly_challenge="Practicar la rutina de calentamiento sin recordatorio.",
            what_to_watch="Cómo enfrenta las salidas en pendiente en el próximo entrenamiento.",
        ),
        badges=[
            BadgeView(code="attendance_100", label="Asistencia 100 %", icon="award", earned_at=date(2026, 6, 20)),
            BadgeView(code="top10", label="Top 10", icon="award", earned_at=date(2026, 6, 15)),
        ],
        photos=[
            PhotoView(thumbnail_url="https://cdn.example.com/photos/thumb1.jpg", caption="Entrenamiento en pista"),
        ],
        coach_note="Vamos muy bien este mes, sigamos con la misma constancia.",
    )


def _no_race_month_stage_log() -> StageLog:
    """Mes sin carrera: la cima es un hito de entrenamiento, sin lectura del analista."""
    return StageLog(
        stage_number=3,
        period_label="Mayo 2026",
        is_current_month=False,
        athlete_first_name="Atleta",
        athlete_reference="su hija",
        stage_title="Un mes de trabajo de base sin carrera",
        trail=[
            Waypoint(
                kind=WaypointKind.BEST_SESSION,
                date=date(2026, 5, 12),
                label="Mejor sesión · técnica 4,5/5",
                icon="star",
            ),
            Waypoint(
                kind=WaypointKind.NEXT_RACE,
                date=date(2026, 6, 15),
                label="Próxima: Válida 3",
                sublabel="Cali",
                icon="compass",
                is_future=True,
            ),
        ],
        summit=Summit(
            kind=SummitKind.TRAINING,
            title="Mejor sesión de entrenamiento del mes",
            detail=None,
            caption="La mejor sesión técnica del mes, con foco en frenada.",
            date=date(2026, 5, 12),
        ),
        observations=[
            Observation(
                claim="Asistió a 10 de 12 sesiones planificadas este mes.",
                evidence="10/12 sesiones (83 %).",
                block_ref="attendance",
            ),
            Observation(
                claim="Consolidó la técnica de frenada en curva cerrada.",
                evidence="Rúbrica técnica promedio de 4,2 sobre 5.",
                block_ref="technical",
            ),
            Observation(
                claim="Mantuvo una racha de 6 sesiones consecutivas.",
                evidence="6 sesiones seguidas sin faltar.",
                block_ref="streak",
            ),
        ],
        analyst_reading=None,
        effort_profile=[
            EffortWeek(week_label="1–7 may", sessions_planned=3, sessions_attended=2, mean_rpe=4.0),
            EffortWeek(week_label="8–14 may", sessions_planned=3, sessions_attended=3, mean_rpe=5.0),
        ],
        next_segment=NextSegment(
            focus_groups=["Frenada"],
            next_race=NextRace(label="Válida 3", date=date(2026, 6, 15), venue="Cali", priority_label="Prioridad A"),
            text="Se acerca la Válida 3 en Cali — seguimos afinando la frenada.",
        ),
        family_compass=FamilyCompass(
            conversation_question="¿Qué le gustaría trabajar antes de la próxima carrera?",
            monthly_challenge="Llegar 10 minutos antes a cada entrenamiento.",
            what_to_watch="Su confianza en curvas cerradas de cara a la Válida 3.",
        ),
        badges=[],
        photos=[],
        coach_note=None,
    )


def _zero_attendance_month_stage_log() -> StageLog:
    """Mes de cero asistencia: sin cima, sin observaciones (024: nunca copy de reproche)."""
    return StageLog(
        stage_number=2,
        period_label="Abril 2026",
        is_current_month=False,
        athlete_first_name="Atleta",
        athlete_reference="su hijo/a",
        stage_title="Etapa de pausa",
        trail=[
            Waypoint(
                kind=WaypointKind.NEXT_RACE,
                date=date(2026, 5, 20),
                label="Próxima: Válida 2",
                sublabel="Palmira",
                icon="compass",
                is_future=True,
            ),
        ],
        summit=None,
        observations=[],
        analyst_reading=None,
        effort_profile=[],
        next_segment=NextSegment(
            focus_groups=[],
            next_race=NextRace(label="Válida 2", date=date(2026, 5, 20), venue="Palmira", priority_label=None),
            text=None,
        ),
        family_compass=None,
        badges=[],
        photos=[],
        coach_note=None,
    )


_ANTHRO_IN_MONTH = {
    "has_records": True,
    "records": [
        {
            "evaluation_date": "2026-06-10",
            "weight_kg": 45.2,
            "standing_height_cm": 158.5,
            "bmi": 18.0,
            "height_z_score": -0.12,
            "height_percentile": 45.2,
            "bmi_z_score": 0.05,
            "bmi_percentile": 52.0,
            "maturity_offset": -0.82,
            "maturation_status": "Pre-PHV",
            "age_at_phv": None,
            "maturation_pedagogy": "En fase pre-PHV: priorizar coordinación.",
            "training_implications": "Evitar cargas de fuerza máxima.",
        }
    ],
    "latest": None,
}

_ANTHRO_OUT_OF_MONTH = {
    "has_records": True,
    "records": [
        {**_ANTHRO_IN_MONTH["records"][0], "evaluation_date": "2026-03-01"},
    ],
    "latest": None,
}

_CHARTS_CTX = {
    "has_data": True,
    "low_confidence": False,
    "positions": [{"x": 1, "y": 5}, {"x": 2, "y": 3}, {"x": 3, "y": 2}],
    "gap_pcts": [{"x": 1, "y": 15.2}, {"x": 2, "y": 9.8}, {"x": 3, "y": 4.1}],
    "points_accumulated": [{"x": 1, "y": 20}, {"x": 2, "y": 70}, {"x": 3, "y": 110}],
}

# email_blocks.race_results (feature 039, contracts/newsletter-context.md) —
# solo el bloque "championships" importa para el gate F-9.
_RACE_RESULTS_CTX = {
    "has_races": True,
    "cups": [],
    "championships": [
        {
            "event_id": 6011,
            "label": "Campeonato Departamental",
            "short_label": "Cto. Dep.",
            "level": "departmental",
            "location": "Ginebra",
            "event_date": "2026-06-20",
            "category_label": "Prejuvenil A Femenino",
            "finished": True,
            "position": 4,
            "field_size": 20,
            "gap_pct": 4.2,
            "percentile": 84.2,
        }
    ],
}


# ---------------------------------------------------------------------------
# Helper de render
# ---------------------------------------------------------------------------


async def _render(
    stage_log: StageLog,
    *,
    year: int = 2026,
    month: int = 6,
    anthropometry: dict | None = None,
    charts_context: dict | None = None,
    percentile_curves: dict | None = None,
) -> bytes:
    # year/month deben coincidir con el mes real de las fixtures (todas caen
    # en 2026-06 salvo _no_race_month_stage_log, que el propio test que la
    # usa junto a antropometría pasa explícitamente) — generate_stage_log_pdf
    # usa (year, month) para filtrar qué mediciones antropométricas caen
    # "en el mes" (regla del Anexo de crecimiento).
    generator = DocumentGenerator(TemplateRegistry())
    dto = to_parent_dto(stage_log, hidden_blocks=None)
    doc, sha256 = await generate_stage_log_pdf(
        generator=generator,
        athlete_first_name="Atleta",
        athlete_last_name="Prueba",
        athlete_id=1,
        year=year,
        month=month,
        stage_log=dto,
        anthropometry=anthropometry,
        charts_context=charts_context,
        percentile_curves=percentile_curves,
    )
    assert len(sha256) == 64
    return doc.data


def _page_count(pdf_bytes: bytes) -> int:
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    return len(pdf.pages)


def _all_text(pdf_bytes: bytes) -> str:
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in pdf.pages)


# ---------------------------------------------------------------------------
# Page count ≤ 3 sobre las tres fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage_log_factory",
    [_full_month_stage_log, _no_race_month_stage_log, _zero_attendance_month_stage_log],
    ids=["full_month", "no_race_month", "zero_attendance_month"],
)
async def test_page_count_within_three_pages(stage_log_factory):
    pdf_bytes = await _render(stage_log_factory())
    assert _page_count(pdf_bytes) <= 3


async def test_full_month_with_annex_still_within_three_pages():
    """Mes completo + anexo de crecimiento (medición del mes + gráficos, ya
    que summit.kind == 'race') sigue en ≤ 3 páginas (AC-5.2)."""
    pdf_bytes = await _render(
        _full_month_stage_log(),
        anthropometry=_ANTHRO_IN_MONTH,
        charts_context=_CHARTS_CTX,
    )
    assert _page_count(pdf_bytes) <= 3
    text = _all_text(pdf_bytes)
    assert "Anexo de crecimiento" in text


# ---------------------------------------------------------------------------
# Anexo de crecimiento — solo cuando hay medición fechada en el mes
# ---------------------------------------------------------------------------


async def test_annex_absent_without_anthropometry():
    pdf_bytes = await _render(_full_month_stage_log())
    assert "Anexo de crecimiento" not in _all_text(pdf_bytes)


async def test_annex_absent_when_record_out_of_month():
    pdf_bytes = await _render(_full_month_stage_log(), anthropometry=_ANTHRO_OUT_OF_MONTH)
    assert "Anexo de crecimiento" not in _all_text(pdf_bytes)


async def test_annex_present_when_record_in_month():
    pdf_bytes = await _render(_full_month_stage_log(), anthropometry=_ANTHRO_IN_MONTH)
    assert "Anexo de crecimiento" in _all_text(pdf_bytes)


# ---------------------------------------------------------------------------
# Gráficos de temporada — solo cuando hubo carrera en el mes (summit.kind == race)
# ---------------------------------------------------------------------------


async def test_charts_absent_without_race_even_with_anthro_in_month():
    no_race_anthro = {**_ANTHRO_IN_MONTH, "records": [
        {**_ANTHRO_IN_MONTH["records"][0], "evaluation_date": "2026-05-10"}
    ]}
    pdf_bytes = await _render(
        _no_race_month_stage_log(),
        year=2026,
        month=5,
        anthropometry=no_race_anthro,
        charts_context=_CHARTS_CTX,
    )
    text = _all_text(pdf_bytes)
    assert "Anexo de crecimiento" in text
    assert "Evolución en la temporada" not in text


async def test_charts_present_when_race_and_anthro_in_month():
    pdf_bytes = await _render(
        _full_month_stage_log(),
        anthropometry=_ANTHRO_IN_MONTH,
        charts_context=_CHARTS_CTX,
    )
    assert "Evolución en la temporada" in _all_text(pdf_bytes)


# ---------------------------------------------------------------------------
# F-9 — "Campeonatos" comparte el gate has_race_this_month con charts_annex.
#
# Prueba directa de ``_build_stage_log_pdf_context`` (función pura) en vez
# de renderizar el PDF: WeasyPrint no carga en este entorno local (ver nota
# del módulo), así que un test que dependa de él quedaría igual de rojo que
# los de arriba sin poder confirmar el fix. El contexto es exactamente lo
# que ``generate_stage_log_pdf`` le pasa al template — probarlo cubre el
# gate sin depender de libgobject.
# ---------------------------------------------------------------------------


def test_context_drops_race_results_without_race_this_month():
    """Mes sin carrera (summit.kind != race) → ``race_results`` es ``None``
    en el contexto, aunque el llamador sí lo haya pasado poblado (F-9)."""
    dto = to_parent_dto(_no_race_month_stage_log(), hidden_blocks=None)
    context = _build_stage_log_pdf_context(
        athlete_first_name="Atleta",
        athlete_last_name="Prueba",
        year=2026,
        month=5,
        stage_log=dto,
        anthropometry=None,
        charts_context=None,
        percentile_curves=None,
        race_results=_RACE_RESULTS_CTX,
        club_name="Trocha y Ruta",
        season_year=None,
    )
    assert context["race_results"] is None
    assert context["charts_annex"] is None


def test_context_keeps_race_results_with_race_this_month():
    """Mes con carrera (summit.kind == race) → ``race_results`` llega intacto
    al contexto, con su bloque ``championships`` disponible para el template."""
    dto = to_parent_dto(_full_month_stage_log(), hidden_blocks=None)
    context = _build_stage_log_pdf_context(
        athlete_first_name="Atleta",
        athlete_last_name="Prueba",
        year=2026,
        month=6,
        stage_log=dto,
        anthropometry=None,
        charts_context=None,
        percentile_curves=None,
        race_results=_RACE_RESULTS_CTX,
        club_name="Trocha y Ruta",
        season_year=None,
    )
    assert context["race_results"] == _RACE_RESULTS_CTX
    assert context["race_results"]["championships"][0]["position"] == 4


# ---------------------------------------------------------------------------
# Privacidad — el PDF nunca imprime claves de uso exclusivo del coach
# ---------------------------------------------------------------------------


async def test_pdf_never_prints_source_insight_id():
    """``analyst_reading.source_insight_id`` (99 en la fixture) es de uso
    exclusivo del coach — ``to_parent_dto`` ya lo elimina antes de llegar al
    contexto del PDF (defensa en profundidad: se verifica en el texto)."""
    pdf_bytes = await _render(_full_month_stage_log())
    assert "99" not in _all_text(pdf_bytes)


# ---------------------------------------------------------------------------
# Válvula de paginación — mes cargado al tope sigue en ≤ 3 páginas
# ---------------------------------------------------------------------------


def _photo_data_uri() -> str:
    """Miniatura real (data-URI) para que el bloque de fotos ocupe altura.

    Con una URL remota el `<img>` no carga en el entorno de test y la sección
    de fotos mide casi nada — justo lo que este test necesita medir.
    """
    import base64

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (140, 200, 60)).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _heaviest_month_stage_log() -> StageLog:
    """Mes en el peor caso admitido por el modelo: 3 observaciones largas, el
    tope de fotos (`_PHOTO_SOFT_CAP` = 8), muchas insignias, 5 semanas de
    esfuerzo y nota del entrenador al límite de palabras."""
    sl = _full_month_stage_log()
    uri = _photo_data_uri()
    sl.photos = [
        PhotoView(thumbnail_url=uri, caption="Entrenamiento en pista, sesión de técnica de curvas")
        for _ in range(8)
    ]
    sl.badges = list(sl.badges) + [
        BadgeView(code=f"extra_{i}", label=f"Insignia larga número {i}") for i in range(6)
    ]
    sl.effort_profile = list(sl.effort_profile) + [
        EffortWeek(week_label="29 jun–5 jul", sessions_planned=3, sessions_attended=3, mean_rpe=5.0)
    ]
    sl.observations = [
        obs.model_copy(
            update={
                "claim": (
                    "Sostuvo el ritmo del grupo de punta durante la segunda vuelta completa, "
                    "algo que no había logrado en ninguna de las válidas anteriores."
                ),
                "evidence": "Parciales de la válida 3: vuelta 2 a cuatro segundos del líder.",
            }
        )
        for obs in sl.observations
    ]
    sl.stage_title = (
        "Una etapa sólida con la mejor carrera de la temporada y una progresión técnica clara"
    )
    sl.coach_note = (
        "Vamos muy bien este mes, sigamos con la misma constancia en los entrenamientos y "
        "cuidando el descanso entre sesiones para llegar enteros a la próxima válida del "
        "calendario departamental."
    )
    return sl


async def test_heaviest_month_with_annex_still_within_three_pages():
    """Un mes cargado al tope + anexo sigue en ≤ 3 páginas (AC-5.2).

    El anexo abre página propia, así que el cuerpo debe caber en dos; cuando no
    cabe, ``generate_stage_log_pdf`` recompone el documento sin ese salto en vez
    de dejar una página casi vacía y crecer a cuatro.
    """
    pdf_bytes = await _render(
        _heaviest_month_stage_log(),
        anthropometry=_ANTHRO_IN_MONTH,
        charts_context=_CHARTS_CTX,
    )
    assert _page_count(pdf_bytes) <= 3
    assert "Anexo de crecimiento" in _all_text(pdf_bytes)


# ---------------------------------------------------------------------------
# Galería de fotos — tope de 4 en el PDF, resto en el portal
# ---------------------------------------------------------------------------


async def test_photo_gallery_caps_at_four_and_points_to_portal():
    """El PDF muestra hasta 4 fotos grandes; el resto se anuncia con una nota.

    El portal (`PhotosGrid`) sí muestra todas — el tope es del PDF, que tiene
    un presupuesto de 3 páginas y no puede permitirse una segunda fila.
    """
    sl = _full_month_stage_log()
    uri = _photo_data_uri()
    sl.photos = [
        PhotoView(thumbnail_url=uri, caption=f"Foto número {i}") for i in range(7)
    ]
    text = _all_text(await _render(sl))

    assert "Foto número 3" in text  # la cuarta, la última que entra
    assert "Foto número 4" not in text  # la quinta ya no se dibuja
    assert "Hay 3 fotos más del mes en el portal." in text


async def test_photo_gallery_without_extras_has_no_portal_note():
    """Con 4 fotos o menos no se anuncia nada: no hay fotos fuera del PDF."""
    sl = _full_month_stage_log()
    uri = _photo_data_uri()
    sl.photos = [PhotoView(thumbnail_url=uri, caption="Salida del sábado") for _ in range(4)]
    text = _all_text(await _render(sl))

    assert "Salida del sábado" in text
    assert "en el portal." not in text
