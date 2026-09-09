"""Tests for ``can_view_audit`` in services/permissions.py (T020).

Covers the RBAC matrix of contracts/audit-log-api.md §4.1/§4.2 for the
club-scoped audit-log read path:
- admin → any club.
- coach, member of the club → allowed.
- coach, other club → denied.
- coach with no club membership → denied.
- parent (even for their own child's club) → denied.
- athlete role account → denied.

``can_view_audit`` is synchronous and DB-free (it only reads ``user.role``
and ``user.club_memberships``), so these are plain unit tests against
in-memory objects — no aiosqlite session is needed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.permissions import can_view_audit


def _user(role: UserRole, memberships: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    """Build a lightweight stand-in for ``User``.

    ``can_view_audit`` only reads ``.role`` and ``.club_memberships``, so a
    plain ``SimpleNamespace`` is used instead of instantiating the mapped
    ``User`` model — assigning a list of plain objects to a real
    SQLAlchemy relationship attribute fires backref events that expect
    mapped instances (``_sa_instance_state``), which a lightweight test
    double does not have.
    """
    return SimpleNamespace(role=role, club_memberships=memberships or [])


def _membership(club_id: int, role_in_club: ClubRole) -> SimpleNamespace:
    return SimpleNamespace(club_id=club_id, role_in_club=role_in_club)


class TestCanViewAudit:
    def test_admin_puede_ver_cualquier_club(self) -> None:
        admin = _user(UserRole.admin)
        assert can_view_audit(admin, club_id=1) is True
        assert can_view_audit(admin, club_id=999) is True

    def test_coach_del_club_puede_ver_su_club(self) -> None:
        coach = _user(
            UserRole.coach,
            [_membership(club_id=1, role_in_club=ClubRole.coach)],
        )
        assert can_view_audit(coach, club_id=1) is True

    def test_coach_de_otro_club_es_rechazado(self) -> None:
        coach = _user(
            UserRole.coach,
            [_membership(club_id=1, role_in_club=ClubRole.coach)],
        )
        assert can_view_audit(coach, club_id=2) is False

    def test_coach_sin_membresia_es_rechazado(self) -> None:
        coach = _user(UserRole.coach, [])
        assert can_view_audit(coach, club_id=1) is False

    def test_coach_con_rol_no_coach_en_el_club_es_rechazado(self) -> None:
        """Un usuario con role=coach pero cuya fila en club_members no es
        ClubRole.coach (p.ej. quedo como member) no debe ver el historial:
        ``coach_club_ids`` filtra estrictamente por ``role_in_club``.
        """
        coach = _user(
            UserRole.coach,
            [_membership(club_id=1, role_in_club=ClubRole.parent)],
        )
        assert can_view_audit(coach, club_id=1) is False

    def test_parent_es_rechazado_incluso_para_el_club_de_su_hijo(self) -> None:
        parent = _user(UserRole.parent)
        assert can_view_audit(parent, club_id=1) is False

    def test_athlete_es_rechazado(self) -> None:
        athlete = _user(UserRole.athlete)
        assert can_view_audit(athlete, club_id=1) is False
