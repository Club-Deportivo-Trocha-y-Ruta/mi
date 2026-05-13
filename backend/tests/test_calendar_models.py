"""Tests del modelo de datos del módulo de calendario.

Cubre: constraints, enums, schemas Pydantic, atributos de columna y FK.
Estrategia: unit tests contra modelos ORM (sin DB real) + validación de
schemas Pydantic. No requiere base de datos.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.calendar_event import (
    ActualAttendanceStatus,
    AudienceType,
    CalendarEvent,
    EventAttendance,
    EventAudience,
    EventStatus,
    EventType,
    RSVPStatus,
)
from app.models.training_session import TrainingSession
from app.schemas.calendar import (
    AudienceCreate,
    EventCreate,
    EventListQuery,
    EventRead,
    EventReadParent,
    EventUpdate,
    RSVPUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2030, 6, 15, 17, 0, tzinfo=timezone.utc)
_END = datetime(2030, 6, 15, 18, 30, tzinfo=timezone.utc)


def _make_event_create(**kwargs) -> EventCreate:
    defaults = dict(
        event_type=EventType.CLUB_EVENT,
        title="Reunión del club",
        start_at=_NOW,
        end_at=_END,
        event_data={"kind": "meeting"},
    )
    defaults.update(kwargs)
    return EventCreate(**defaults)


# ---------------------------------------------------------------------------
# 1. Enums — valores almacenados en lowercase
# ---------------------------------------------------------------------------


class TestEnums:
    def test_event_type_values(self):
        assert EventType.TRAINING_SESSION.value == "training_session"
        assert EventType.COMPETITION.value == "competition"
        assert EventType.CLUB_EVENT.value == "club_event"
        assert EventType.PERSONAL_TRAINING.value == "personal_training"
        assert EventType.GROUP_TRAINING.value == "group_training"
        assert EventType.REST_DAY.value == "rest_day"

    def test_event_status_values(self):
        assert EventStatus.SCHEDULED.value == "scheduled"
        assert EventStatus.CONFIRMED.value == "confirmed"
        assert EventStatus.CANCELLED.value == "cancelled"
        assert EventStatus.COMPLETED.value == "completed"

    def test_audience_type_values(self):
        assert AudienceType.ALL_CLUB.value == "all_club"
        assert AudienceType.CATEGORY.value == "category"
        assert AudienceType.ATHLETE_LIST.value == "athlete_list"
        assert AudienceType.INDIVIDUAL.value == "individual"

    def test_rsvp_status_values(self):
        assert RSVPStatus.PENDING.value == "pending"
        assert RSVPStatus.ACCEPTED.value == "accepted"
        assert RSVPStatus.DECLINED.value == "declined"
        assert RSVPStatus.TENTATIVE.value == "tentative"

    def test_actual_attendance_status_values(self):
        assert ActualAttendanceStatus.UNKNOWN.value == "unknown"
        assert ActualAttendanceStatus.ATTENDED.value == "attended"
        assert ActualAttendanceStatus.NO_SHOW.value == "no_show"
        assert ActualAttendanceStatus.EXCUSED.value == "excused"


# ---------------------------------------------------------------------------
# 2. CalendarEvent — atributos de tabla y constraints
# ---------------------------------------------------------------------------


class TestCalendarEventModel:
    def test_has_required_columns(self):
        cols = {c.name for c in CalendarEvent.__table__.columns}
        required = {
            "id", "club_id", "event_type", "status", "title",
            "description", "location", "start_at", "end_at",
            "all_day", "timezone", "event_data", "color_hex",
            "created_by_user_id", "created_at", "updated_at",
        }
        assert required.issubset(cols)

    def test_check_constraint_range_present(self):
        check_names = {
            c.name
            for c in CalendarEvent.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "ck_calendar_event_range" in check_names

    def test_index_club_start_present(self):
        index_names = {idx.name for idx in CalendarEvent.__table__.indexes}
        assert "idx_calendar_club_start" in index_names

    def test_fk_club_restrict(self):
        fk = next(
            fk for fk in CalendarEvent.__table__.foreign_keys
            if "clubs" in fk.target_fullname
        )
        assert fk.ondelete == "RESTRICT"

    def test_fk_creator_restrict(self):
        fk = next(
            fk for fk in CalendarEvent.__table__.foreign_keys
            if "users" in fk.target_fullname
        )
        assert fk.ondelete == "RESTRICT"

    def test_has_audiences_relationship(self):
        assert hasattr(CalendarEvent, "audiences")

    def test_has_attendances_relationship(self):
        assert hasattr(CalendarEvent, "attendances")

    def test_has_training_session_relationship(self):
        assert hasattr(CalendarEvent, "training_session")


# ---------------------------------------------------------------------------
# 3. EventAudience — atributos de tabla y FK CASCADE
# ---------------------------------------------------------------------------


class TestEventAudienceModel:
    def test_has_required_columns(self):
        cols = {c.name for c in EventAudience.__table__.columns}
        assert {"id", "event_id", "audience_type", "audience_value"}.issubset(cols)

    def test_fk_event_cascade(self):
        fk = next(
            fk for fk in EventAudience.__table__.foreign_keys
            if "calendar_events" in fk.target_fullname
        )
        assert fk.ondelete == "CASCADE"

    def test_index_event_id_present(self):
        index_names = {idx.name for idx in EventAudience.__table__.indexes}
        assert "idx_audience_event" in index_names


# ---------------------------------------------------------------------------
# 4. EventAttendance — atributos de tabla, unique constraint y FKs
# ---------------------------------------------------------------------------


class TestEventAttendanceModel:
    def test_has_required_columns(self):
        cols = {c.name for c in EventAttendance.__table__.columns}
        required = {
            "id", "event_id", "athlete_id", "rsvp_status", "rsvp_at",
            "rsvp_by_user_id", "actual_status", "notes",
            "created_at", "updated_at",
        }
        assert required.issubset(cols)

    def test_unique_event_athlete(self):
        constraint_names = {
            c.name for c in EventAttendance.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_event_attendance" in constraint_names

    def test_fk_event_cascade(self):
        fk = next(
            fk for fk in EventAttendance.__table__.foreign_keys
            if "calendar_events" in fk.target_fullname
        )
        assert fk.ondelete == "CASCADE"

    def test_fk_athlete_restrict(self):
        fk = next(
            fk for fk in EventAttendance.__table__.foreign_keys
            if "athletes" in fk.target_fullname
        )
        assert fk.ondelete == "RESTRICT"

    def test_fk_rsvp_by_set_null(self):
        fk = next(
            fk for fk in EventAttendance.__table__.foreign_keys
            if "users" in fk.target_fullname
        )
        assert fk.ondelete == "SET NULL"


# ---------------------------------------------------------------------------
# 5. TrainingSession — columna calendar_event_id añadida
# ---------------------------------------------------------------------------


class TestTrainingSessionCalendarEventId:
    def test_has_calendar_event_id_column(self):
        cols = {c.name for c in TrainingSession.__table__.columns}
        assert "calendar_event_id" in cols

    def test_calendar_event_id_nullable(self):
        col = TrainingSession.__table__.c.calendar_event_id
        assert col.nullable is True

    def test_calendar_event_id_unique(self):
        # La constraint unique debe existir (puede ser inline o nombrada)
        col = TrainingSession.__table__.c.calendar_event_id
        # unique=True en mapped_column crea UniqueConstraint implícita
        constraint_names = {
            c.name for c in TrainingSession.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        # Verificar también via columna directa
        assert col.unique is True or any(
            "calendar_event" in (n or "") for n in constraint_names
        )

    def test_calendar_event_id_fk_set_null(self):
        fk = next(
            (
                fk for fk in TrainingSession.__table__.foreign_keys
                if "calendar_events" in fk.target_fullname
            ),
            None,
        )
        assert fk is not None, "FK calendar_event_id no encontrada en training_sessions"
        assert fk.ondelete == "SET NULL"

    def test_has_calendar_event_relationship(self):
        assert hasattr(TrainingSession, "calendar_event")


# ---------------------------------------------------------------------------
# 6. EventCreate — validación Pydantic
# ---------------------------------------------------------------------------


class TestEventCreate:
    def test_valid_club_event(self):
        e = _make_event_create()
        assert e.event_type == EventType.CLUB_EVENT
        assert e.title == "Reunión del club"

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError) as exc:
            _make_event_create(
                start_at=datetime(2030, 6, 15, 18, 0),
                end_at=datetime(2030, 6, 15, 17, 0),
            )
        assert "end_at" in str(exc.value)

    def test_equal_start_end_valid(self):
        e = _make_event_create(
            start_at=datetime(2030, 6, 15, 17, 0),
            end_at=datetime(2030, 6, 15, 17, 0),
        )
        assert e.start_at == e.end_at

    def test_title_max_length(self):
        e = _make_event_create(title="A" * 200)
        assert len(e.title) == 200

    def test_title_too_long_raises(self):
        with pytest.raises(ValidationError):
            _make_event_create(title="A" * 201)

    def test_color_hex_valid(self):
        e = _make_event_create(color_hex="#1A2B3C")
        assert e.color_hex == "#1A2B3C"

    def test_color_hex_invalid_raises(self):
        with pytest.raises(ValidationError):
            _make_event_create(color_hex="red")

    def test_default_status_scheduled(self):
        e = _make_event_create()
        assert e.status == EventStatus.SCHEDULED

    def test_event_data_training_session_valid(self):
        e = EventCreate(
            event_type=EventType.TRAINING_SESSION,
            title="Sesión",
            start_at=_NOW,
            end_at=_END,
            event_data={"training_session_id": 42},
        )
        assert e.event_data["training_session_id"] == 42

    def test_event_data_competition_valid(self):
        e = EventCreate(
            event_type=EventType.COMPETITION,
            title="Copa Valle IV",
            start_at=_NOW,
            end_at=_END,
            event_data={"city": "Cali", "race_category": "A", "is_departmental": False},
        )
        assert e.event_data["city"] == "Cali"

    def test_event_data_invalid_shape_raises(self):
        with pytest.raises(ValidationError):
            EventCreate(
                event_type=EventType.COMPETITION,
                title="Copa Valle IV",
                start_at=_NOW,
                end_at=_END,
                event_data={"city": "Cali"},  # falta race_category
            )

    def test_audiences_default_empty(self):
        e = _make_event_create()
        assert e.audiences == []

    def test_audiences_with_all_club(self):
        e = _make_event_create(
            audiences=[{"audience_type": "all_club", "audience_value": {}}]
        )
        assert len(e.audiences) == 1
        assert e.audiences[0].audience_type == AudienceType.ALL_CLUB


# ---------------------------------------------------------------------------
# 7. EventUpdate — validación parcial
# ---------------------------------------------------------------------------


class TestEventUpdate:
    def test_all_optional(self):
        u = EventUpdate()
        assert u.title is None
        assert u.start_at is None

    def test_invalid_range_raises(self):
        with pytest.raises(ValidationError):
            EventUpdate(
                start_at=datetime(2030, 6, 15, 18, 0),
                end_at=datetime(2030, 6, 15, 17, 0),
            )

    def test_partial_range_no_validation(self):
        # Solo start_at sin end_at no debe fallar
        u = EventUpdate(start_at=datetime(2030, 6, 15, 18, 0))
        assert u.start_at is not None
        assert u.end_at is None


# ---------------------------------------------------------------------------
# 8. AudienceCreate — validación de shapes
# ---------------------------------------------------------------------------


class TestAudienceCreate:
    def test_all_club_empty_value(self):
        a = AudienceCreate(audience_type=AudienceType.ALL_CLUB, audience_value={})
        assert a.audience_type == AudienceType.ALL_CLUB

    def test_category_valid(self):
        a = AudienceCreate(
            audience_type=AudienceType.CATEGORY,
            audience_value={"category": "Pre-juvenil A"},
        )
        assert a.audience_value["category"] == "Pre-juvenil A"

    def test_category_missing_key_raises(self):
        with pytest.raises(ValidationError) as exc:
            AudienceCreate(
                audience_type=AudienceType.CATEGORY,
                audience_value={"wrong_key": "value"},
            )
        assert "category" in str(exc.value)

    def test_athlete_list_valid(self):
        a = AudienceCreate(
            audience_type=AudienceType.ATHLETE_LIST,
            audience_value={"athlete_ids": [1, 2, 3]},
        )
        assert len(a.audience_value["athlete_ids"]) == 3

    def test_athlete_list_empty_raises(self):
        with pytest.raises(ValidationError):
            AudienceCreate(
                audience_type=AudienceType.ATHLETE_LIST,
                audience_value={"athlete_ids": []},
            )

    def test_athlete_list_non_int_raises(self):
        with pytest.raises(ValidationError):
            AudienceCreate(
                audience_type=AudienceType.ATHLETE_LIST,
                audience_value={"athlete_ids": ["abc", "def"]},
            )

    def test_individual_valid(self):
        a = AudienceCreate(
            audience_type=AudienceType.INDIVIDUAL,
            audience_value={"athlete_id": 7},
        )
        assert a.audience_value["athlete_id"] == 7

    def test_individual_missing_key_raises(self):
        with pytest.raises(ValidationError) as exc:
            AudienceCreate(
                audience_type=AudienceType.INDIVIDUAL,
                audience_value={"wrong": 7},
            )
        assert "athlete_id" in str(exc.value)


# ---------------------------------------------------------------------------
# 9. RSVPUpdate — validación básica
# ---------------------------------------------------------------------------


class TestRSVPUpdate:
    def test_valid_rsvp(self):
        r = RSVPUpdate(athlete_id=1, rsvp_status=RSVPStatus.ACCEPTED)
        assert r.rsvp_status == RSVPStatus.ACCEPTED

    def test_all_rsvp_statuses_accepted(self):
        for status in RSVPStatus:
            r = RSVPUpdate(athlete_id=1, rsvp_status=status)
            assert r.rsvp_status == status


# ---------------------------------------------------------------------------
# 10. EventListQuery — validación de rango de fechas
# ---------------------------------------------------------------------------


class TestEventListQuery:
    def test_valid_range(self):
        from datetime import date
        q = EventListQuery(from_date=date(2030, 6, 1), to_date=date(2030, 6, 30))
        assert q.mine_only is False

    def test_invalid_range_raises(self):
        from datetime import date
        with pytest.raises(ValidationError) as exc:
            EventListQuery(from_date=date(2030, 6, 30), to_date=date(2030, 6, 1))
        assert "to_date" in str(exc.value)

    def test_same_date_range_valid(self):
        from datetime import date
        q = EventListQuery(from_date=date(2030, 6, 15), to_date=date(2030, 6, 15))
        assert q.from_date == q.to_date

    def test_event_types_filter(self):
        from datetime import date
        q = EventListQuery(
            from_date=date(2030, 6, 1),
            to_date=date(2030, 6, 30),
            event_types=[EventType.COMPETITION, EventType.CLUB_EVENT],
        )
        assert len(q.event_types) == 2

    def test_mine_only_default_false(self):
        from datetime import date
        q = EventListQuery(from_date=date(2030, 6, 1), to_date=date(2030, 6, 30))
        assert q.mine_only is False


# ---------------------------------------------------------------------------
# 11. EventRead y EventReadParent — model_config from_attributes
# ---------------------------------------------------------------------------


class TestEventReadSchemas:
    def test_event_read_from_attributes(self):
        assert EventRead.model_config.get("from_attributes") is True

    def test_event_read_parent_from_attributes(self):
        assert EventReadParent.model_config.get("from_attributes") is True

    def test_event_read_parent_has_no_created_by_user_id(self):
        fields = EventReadParent.model_fields
        assert "created_by_user_id" not in fields

    def test_event_read_has_created_by_user_id(self):
        fields = EventRead.model_fields
        assert "created_by_user_id" in fields

    def test_event_read_parent_has_no_audiences(self):
        # EventReadParent no expone la audiencia interna
        fields = EventReadParent.model_fields
        assert "audiences" not in fields


# ---------------------------------------------------------------------------
# 12. Verificación de exports en __init__.py
# ---------------------------------------------------------------------------


class TestModelsInit:
    def test_calendar_models_exported(self):
        from app.models import (
            ActualAttendanceStatus,
            AudienceType,
            CalendarEvent,
            EventAttendance,
            EventAudience,
            EventStatus,
            EventType,
            RSVPStatus,
        )
        assert CalendarEvent.__tablename__ == "calendar_events"
        assert EventAudience.__tablename__ == "event_audiences"
        assert EventAttendance.__tablename__ == "event_attendances"
