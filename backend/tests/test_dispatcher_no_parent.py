"""Tests BUG-002 — dispatcher marca failed cuando atleta no tiene padres vinculados.

Cubre:
  1. Newsletter approved sin padres → status=failed, error_message="no_parent_linked".
  2. Newsletter approved con padre → flujo de agrupación normal (no regresión).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.athlete_newsletter import NewsletterStatus
from app.services.notification.newsletter_dispatcher import _group_by_parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_nl(athlete_id: int, nl_id: int = 1) -> MagicMock:
    """Crea un mock de AthleteMonthlyNewsletter."""
    nl = MagicMock()
    nl.id = nl_id
    nl.athlete_id = athlete_id
    nl.status = NewsletterStatus.approved
    nl.error_message = None
    return nl


def _make_pa(parent_id: int, athlete_id: int) -> MagicMock:
    """Crea un mock de ParentAthlete."""
    pa = MagicMock()
    pa.parent_id = parent_id
    pa.athlete_id = athlete_id
    return pa


def _make_db(parent_athletes: list) -> AsyncMock:
    """Crea un AsyncSession mock que devuelve los parent_athletes dados."""
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = parent_athletes
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroupByParentNoParent:
    """BUG-002: atleta sin padres vinculados."""

    @pytest.mark.asyncio
    async def test_newsletter_marcado_failed_sin_padres(self):
        """Cuando el atleta no tiene padres, el newsletter pasa a failed con código de catálogo."""
        nl = _make_nl(athlete_id=42, nl_id=7)
        db = _make_db(parent_athletes=[])  # sin padres

        grouped = await _group_by_parent(db, [nl])

        # No debe haber grupos (nadie a quien enviar)
        assert grouped == {}

        # El newsletter debe haberse marcado como failed
        assert nl.status == NewsletterStatus.failed
        assert nl.error_message == "no_parent_linked"

        # flush debe haberse llamado
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_message_en_catalogo(self):
        """El error_message asignado pertenece al catálogo cerrado de auditoría."""
        catalog = {
            "llm_timeout",
            "guardrails_rejected",
            "llm_internal_error",
            "consent_missing",
            "no_parent_linked",
        }
        nl = _make_nl(athlete_id=43, nl_id=8)
        db = _make_db(parent_athletes=[])

        await _group_by_parent(db, [nl])

        assert nl.error_message in catalog


class TestGroupByParentWithParent:
    """Regresión: atleta con padre sigue agrupando correctamente."""

    @pytest.mark.asyncio
    async def test_newsletter_agrupado_por_padre(self):
        """Cuando hay padres vinculados, los newsletters se agrupan y no se marcan failed."""
        nl = _make_nl(athlete_id=10, nl_id=1)
        pa = _make_pa(parent_id=99, athlete_id=10)
        db = _make_db(parent_athletes=[pa])

        grouped = await _group_by_parent(db, [nl])

        # El newsletter debe estar en el grupo del padre
        assert 99 in grouped
        assert nl in grouped[99]

        # El estado no debe haber cambiado
        assert nl.status == NewsletterStatus.approved
        assert nl.error_message is None

        # flush no debe haberse llamado (no hay atletas sin padres)
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiples_atletas_mismo_padre(self):
        """Varios atletas de un mismo padre se agrupan en una sola entrada."""
        nl1 = _make_nl(athlete_id=10, nl_id=1)
        nl2 = _make_nl(athlete_id=11, nl_id=2)
        pa1 = _make_pa(parent_id=99, athlete_id=10)
        pa2 = _make_pa(parent_id=99, athlete_id=11)
        db = _make_db(parent_athletes=[pa1, pa2])

        grouped = await _group_by_parent(db, [nl1, nl2])

        assert 99 in grouped
        assert len(grouped[99]) == 2
        assert nl1 in grouped[99]
        assert nl2 in grouped[99]

    @pytest.mark.asyncio
    async def test_mix_atleta_con_y_sin_padre(self):
        """Un atleta con padre se agrupa; el atleta sin padre se marca failed."""
        nl_con = _make_nl(athlete_id=10, nl_id=1)
        nl_sin = _make_nl(athlete_id=20, nl_id=2)
        pa = _make_pa(parent_id=99, athlete_id=10)
        db = _make_db(parent_athletes=[pa])

        grouped = await _group_by_parent(db, [nl_con, nl_sin])

        # Atleta con padre → en grupo
        assert 99 in grouped
        assert nl_con in grouped[99]

        # Atleta sin padre → failed
        assert nl_sin.status == NewsletterStatus.failed
        assert nl_sin.error_message == "no_parent_linked"
        db.flush.assert_awaited_once()
