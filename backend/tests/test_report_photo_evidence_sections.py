"""Tests T019 (specs/022-align-monthly-report-format) — derivación de
``section`` en ``build_report_photo_evidence``
(``backend/app/services/training/reports.py``).

Cubre:
(happy) foto de una sesión ``session_kind in (entrenamiento, otro)`` ->
        ``section == "Grupo de Alto Rendimiento"``.
(happy) foto de una sesión ``session_kind in (actividad_conjunta, salida)``
        -> ``section == "Actividades Conjuntas"``.
(happy) foto cuya fecha de sesión coincide con ``RaceEvent.event_date`` de
        una competencia de un atleta del club en el período ->
        ``section == "Competencia"`` (heurística de fecha, tiene prioridad
        sobre el `session_kind` — ver research.md R6).
(edge)  un período sin fotos retorna una lista vacía sin excepción (ningún
        "grupo" es responsabilidad de esta función — eso lo resuelve el
        template con placeholders reservados).
(edge)  los filtros existentes (``consent_ack``, thumbnail, cap de 6 fotos /
        2 MB) se preservan sin cambios tras la extensión de `section`.

NOTA (T019, escrito antes/junto a T020): a la fecha de este test,
``build_report_photo_evidence`` NO deriva ni popula la clave ``section`` en
los items que retorna. Los tests de "happy" (sección derivada) DEBEN FALLAR
(``KeyError`` o `AssertionError`) hasta que T020 implemente la derivación.
Se documenta explícitamente para que el fallo inicial no se confunda con un
test mal escrito. Los tests de "edge" (filtros preexistentes, período vacío)
ya deben pasar hoy — cubren el comportamiento que T020 NO debe romper.

Estrategia: SQLite async in-memory real (mismo patrón que
``tests/test_competition_results_grouping.py`` /
``tests/fixtures/race_history_fixtures.py``), con archivos temporales reales
como "thumbnails descargados" (se parchea únicamente
``storage_sftp.download_to_tempfile`` para no requerir SFTP real).
"""

from __future__ import annotations

import tempfile
from datetime import date, time, timezone
from datetime import datetime as dt
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_series import RaceSeriesKind
from app.models.session_media import MediaType, SessionMedia
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from app.models.user import UserRole
from app.services.training.reports import build_report_photo_evidence

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)


# ---------------------------------------------------------------------------
# Engine / sesión SQLite in-memory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            "training_sessions",
            "session_media",
            "session_media_athlete",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_club_and_coach(session: AsyncSession, club_id: int = 1) -> None:
    await create_club(session, club_id=club_id)
    await create_user(session, user_id=10, role=UserRole.coach)


async def _create_session(
    session: AsyncSession,
    *,
    session_id: int,
    club_id: int = 1,
    scheduled_date: date,
    session_kind: SessionKind = SessionKind.ENTRENAMIENTO,
    status: SessionStatus = SessionStatus.EXECUTED,
    technical_focus: str = "Técnica general",
    location: str = "Sede Club",
) -> TrainingSession:
    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=10,
        status=status,
        scheduled_date=scheduled_date,
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location=location,
        technical_focus=technical_focus,
        session_kind=session_kind,
    )
    session.add(ts)
    await session.flush()
    return ts


async def _create_media(
    session: AsyncSession,
    *,
    media_id: int,
    session_id: int,
    storage_path: str,
    consent_ack: bool = True,
    thumbnail_url: str | None = "https://cdn.example.com/thumb.jpg",
    deleted_at: dt | None = None,
    caption: str | None = None,
) -> SessionMedia:
    m = SessionMedia(
        id=media_id,
        session_id=session_id,
        media_type=MediaType.PHOTO,
        storage_url="https://cdn.example.com/original.jpg",
        storage_path=storage_path,
        thumbnail_url=thumbnail_url,
        filename_original="foto.jpg",
        mime_type="image/jpeg",
        size_bytes=12_345,
        caption=caption,
        consent_ack=consent_ack,
        uploaded_by_user_id=10,
        deleted_at=deleted_at,
    )
    session.add(m)
    await session.flush()
    return m


def _make_fake_thumbnail(content: bytes = b"\xff\xd8\xff\xe0FAKEJPEG") -> str:
    """Crea un archivo temporal real que simula el thumbnail descargado."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(content)
    tmp.close()
    return tmp.name


def _patched_download(paths_to_files: dict[str, str]):
    """Devuelve un side_effect para ``download_to_tempfile`` basado en el
    ``storage_path`` derivado del thumbnail (ver ``build_report_photo_evidence``:
    ``{stem}.thumb.jpg``)."""

    async def _fake(thumb_path: str, suffix: str = "") -> str:
        if thumb_path not in paths_to_files:
            raise FileNotFoundError(thumb_path)
        return paths_to_files[thumb_path]

    return _fake


def _thumb_path_for(storage_path: str) -> str:
    from pathlib import PurePosixPath

    orig = PurePosixPath(storage_path)
    return str(orig.with_name(f"{orig.stem}.thumb.jpg"))


# ---------------------------------------------------------------------------
# (happy) session_kind entrenamiento|otro -> Grupo de Alto Rendimiento
# ---------------------------------------------------------------------------


class TestSectionAltoRendimiento:
    async def test_session_kind_entrenamiento_mapea_a_alto_rendimiento(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session,
                session_id=1,
                scheduled_date=date(2026, 5, 15),
                session_kind=SessionKind.ENTRENAMIENTO,
            )
            storage_path = "static/uploads/media/sessions/1/foo.jpg"
            await _create_media(session, media_id=1, session_id=1, storage_path=storage_path)
            await session.commit()

            fake_file = _make_fake_thumbnail()
            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(
                    side_effect=_patched_download(
                        {_thumb_path_for(storage_path): fake_file}
                    )
                ),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) == 1
        assert items[0]["section"] == "Grupo de Alto Rendimiento"

    async def test_session_kind_otro_mapea_a_alto_rendimiento(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session,
                session_id=1,
                scheduled_date=date(2026, 5, 20),
                session_kind=SessionKind.OTRO,
            )
            storage_path = "static/uploads/media/sessions/1/bar.jpg"
            await _create_media(session, media_id=1, session_id=1, storage_path=storage_path)
            await session.commit()

            fake_file = _make_fake_thumbnail()
            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(
                    side_effect=_patched_download(
                        {_thumb_path_for(storage_path): fake_file}
                    )
                ),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) == 1
        assert items[0]["section"] == "Grupo de Alto Rendimiento"


# ---------------------------------------------------------------------------
# (happy) session_kind actividad_conjunta|salida -> Actividades Conjuntas
# ---------------------------------------------------------------------------


class TestSectionActividadesConjuntas:
    async def test_session_kind_actividad_conjunta_mapea_a_actividades_conjuntas(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session,
                session_id=1,
                scheduled_date=date(2026, 5, 10),
                session_kind=SessionKind.ACTIVIDAD_CONJUNTA,
            )
            storage_path = "static/uploads/media/sessions/1/act.jpg"
            await _create_media(session, media_id=1, session_id=1, storage_path=storage_path)
            await session.commit()

            fake_file = _make_fake_thumbnail()
            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(
                    side_effect=_patched_download(
                        {_thumb_path_for(storage_path): fake_file}
                    )
                ),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) == 1
        assert items[0]["section"] == "Actividades Conjuntas"

    async def test_session_kind_salida_mapea_a_actividades_conjuntas(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session,
                session_id=1,
                scheduled_date=date(2026, 5, 12),
                session_kind=SessionKind.SALIDA,
            )
            storage_path = "static/uploads/media/sessions/1/salida.jpg"
            await _create_media(session, media_id=1, session_id=1, storage_path=storage_path)
            await session.commit()

            fake_file = _make_fake_thumbnail()
            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(
                    side_effect=_patched_download(
                        {_thumb_path_for(storage_path): fake_file}
                    )
                ),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) == 1
        assert items[0]["section"] == "Actividades Conjuntas"


# ---------------------------------------------------------------------------
# (happy) fecha de sesión == RaceEvent.event_date de una competencia del
# club en el período -> Competencia (prioridad sobre session_kind)
# ---------------------------------------------------------------------------


class TestSectionCompetencia:
    async def _seed_race_on(
        self, session: AsyncSession, *, event_date: date, athlete_id: int = 144
    ) -> None:
        await create_athlete(session, athlete_id=athlete_id, club_id=1, user_id=10, created_by=10)
        await create_race_category(session, category_id=100, code="INF_B", label="Infantil B")
        await create_race_series(session, series_id=1, season_year=2026, kind=RaceSeriesKind.cup)
        await create_race_event(
            session,
            event_id=501,
            series_id=1,
            sequence_number=1,
            name="Copa Valle I",
            event_date=event_date,
            created_by_user_id=10,
        )
        await create_race_competitor(session, competitor_id=1441, athlete_id=athlete_id)
        await create_race_result(
            session,
            event_id=501,
            category_id=100,
            competitor_id=1441,
            athlete_id=athlete_id,
            position=2,
            created_by_user_id=10,
        )

    async def test_fecha_de_sesion_coincide_con_evento_de_carrera_mapea_a_competencia(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        race_date = date(2026, 5, 17)
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await self._seed_race_on(session, event_date=race_date)
            # session_kind = SALIDA a propósito: sin la heurística de fecha
            # mapearía a "Actividades Conjuntas". La coincidencia de fecha con
            # la carrera debe tener prioridad y producir "Competencia".
            await _create_session(
                session,
                session_id=1,
                scheduled_date=race_date,
                session_kind=SessionKind.SALIDA,
            )
            storage_path = "static/uploads/media/sessions/1/carrera.jpg"
            await _create_media(session, media_id=1, session_id=1, storage_path=storage_path)
            await session.commit()

            fake_file = _make_fake_thumbnail()
            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(
                    side_effect=_patched_download(
                        {_thumb_path_for(storage_path): fake_file}
                    )
                ),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) == 1
        assert items[0]["section"] == "Competencia"


# ---------------------------------------------------------------------------
# (edge) período sin fotos -> lista vacía sin excepción
# ---------------------------------------------------------------------------


class TestNoPhotosInPeriod:
    async def test_periodo_sin_fotos_retorna_lista_vacia_sin_error(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await session.commit()

            items = await build_report_photo_evidence(
                db=session, club_id=1, year=2026, month=5
            )

        assert items == []


# ---------------------------------------------------------------------------
# (edge) filtros existentes se preservan: consent_ack, thumbnail, cap 6/2MB
# ---------------------------------------------------------------------------


class TestExistingFiltersPreserved:
    async def test_foto_sin_consentimiento_se_excluye(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session, session_id=1, scheduled_date=date(2026, 5, 15)
            )
            storage_path = "static/uploads/media/sessions/1/no_consent.jpg"
            await _create_media(
                session,
                media_id=1,
                session_id=1,
                storage_path=storage_path,
                consent_ack=False,
            )
            await session.commit()

            items = await build_report_photo_evidence(
                db=session, club_id=1, year=2026, month=5
            )

        assert items == []

    async def test_foto_sin_thumbnail_se_excluye(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session, session_id=1, scheduled_date=date(2026, 5, 15)
            )
            storage_path = "static/uploads/media/sessions/1/no_thumb.jpg"
            await _create_media(
                session,
                media_id=1,
                session_id=1,
                storage_path=storage_path,
                thumbnail_url=None,
            )
            await session.commit()

            items = await build_report_photo_evidence(
                db=session, club_id=1, year=2026, month=5
            )

        assert items == []

    async def test_foto_borrada_se_excluye(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session, session_id=1, scheduled_date=date(2026, 5, 15)
            )
            storage_path = "static/uploads/media/sessions/1/deleted.jpg"
            await _create_media(
                session,
                media_id=1,
                session_id=1,
                storage_path=storage_path,
                deleted_at=dt.now(timezone.utc),
            )
            await session.commit()

            items = await build_report_photo_evidence(
                db=session, club_id=1, year=2026, month=5
            )

        assert items == []

    async def test_cap_de_6_fotos_se_mantiene_con_7_candidatas(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            paths_to_files: dict[str, str] = {}
            for i in range(1, 8):  # 7 fotos consentidas
                await _create_session(
                    session,
                    session_id=i,
                    scheduled_date=date(2026, 5, i),
                )
                storage_path = f"static/uploads/media/sessions/{i}/foto{i}.jpg"
                await _create_media(
                    session, media_id=i, session_id=i, storage_path=storage_path
                )
                paths_to_files[_thumb_path_for(storage_path)] = _make_fake_thumbnail(
                    content=b"\xff\xd8\xff\xe0SMALLJPEG"
                )
            await session.commit()

            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(side_effect=_patched_download(paths_to_files)),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert len(items) <= 6

    async def test_cap_de_2mb_detiene_acumulacion(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            paths_to_files: dict[str, str] = {}
            big_chunk = b"\xff\xd8\xff\xe0" + (b"A" * (900 * 1024))  # ~900 KB c/u
            for i in range(1, 4):  # 3 fotos de ~900 KB -> excede 2 MB al acumular
                await _create_session(
                    session,
                    session_id=i,
                    scheduled_date=date(2026, 5, i),
                )
                storage_path = f"static/uploads/media/sessions/{i}/big{i}.jpg"
                await _create_media(
                    session, media_id=i, session_id=i, storage_path=storage_path
                )
                paths_to_files[_thumb_path_for(storage_path)] = _make_fake_thumbnail(
                    content=big_chunk
                )
            await session.commit()

            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(side_effect=_patched_download(paths_to_files)),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        # 3 fotos de ~900 KB no caben completas bajo el tope de 2 MB.
        assert len(items) < 3

    async def test_foto_ilegible_se_omite_sin_romper(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await _seed_club_and_coach(session)
            await _create_session(
                session, session_id=1, scheduled_date=date(2026, 5, 15)
            )
            storage_path = "static/uploads/media/sessions/1/missing.jpg"
            await _create_media(
                session, media_id=1, session_id=1, storage_path=storage_path
            )
            await session.commit()

            with patch(
                "app.services.training.storage_sftp.download_to_tempfile",
                AsyncMock(side_effect=FileNotFoundError("nope")),
            ):
                items = await build_report_photo_evidence(
                    db=session, club_id=1, year=2026, month=5
                )

        assert items == []
