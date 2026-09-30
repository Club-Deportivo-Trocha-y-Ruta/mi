"""Row-level tests for ``app.services.imderty.rows`` (feature 047, T032).

Pure: every athlete, profile, guardian and sensitive row is a transient ORM
object (never added to a session), so relationship reads never hit a DB.
All names, numbers, addresses and phones are fictitious (Ley 1581).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models.athlete import Athlete, ParentAthlete, Sex
from app.models.imderty import (
    AthleteImdertyProfile,
    AthleteSensitiveAuthorization,
    AthleteSensitiveData,
    ImdertyBarrio,
    ImdertyDisability,
    ImdertyDocumentType,
    ImdertyEthnicity,
    ImdertyGrade,
    ImdertyYesNo,
)
from app.models.user import User
from app.services.imderty import rows as rows_mod
from app.services.imderty.rows import build_rows
from app.services.imderty.workbook import PARTICIPANT_COLUMNS

MONTH = date(2026, 8, 1)
ATHLETE_ID = 9001


def _athlete(
    *,
    last_name: str = "Pérez Gómez",
    profile: AthleteImdertyProfile | None = None,
    guardians: list[tuple[int, str | None, bool]] | None = None,
    sex: Sex = Sex.F,
) -> Athlete:
    athlete = Athlete(
        id=ATHLETE_ID,
        first_name="Ana Sofía",
        last_name=last_name,
        birth_date=date(2014, 1, 1),
        sex=sex,
        club_join_date=date(2025, 1, 1),
        deleted_at=None,
    )
    athlete.imderty_profile = profile
    links: list[ParentAthlete] = []
    for link_id, phone, is_primary in guardians or []:
        links.append(
            ParentAthlete(
                id=link_id,
                parent_id=link_id + 100,
                athlete_id=ATHLETE_ID,
                primary_contact_key=ATHLETE_ID if is_primary else None,
                parent=User(id=link_id + 100, phone=phone),
            )
        )
    athlete.parents = links
    return athlete


def _profile(**overrides: object) -> AthleteImdertyProfile:
    values: dict[str, object] = {
        "athlete_id": ATHLETE_ID,
        "other_municipality": False,
    }
    values.update(overrides)
    return AthleteImdertyProfile(**values)


def _sensitive(*, active: bool = True, **overrides: object) -> AthleteSensitiveData:
    authorization = AthleteSensitiveAuthorization(
        id=77,
        athlete_id=ATHLETE_ID,
        guardian_user_id=1,
        authorized_on=date(2026, 7, 1),
        recorded_by_user_id=2,
        withdrawn_at=None if active else datetime(2026, 7, 20),
        active_key=ATHLETE_ID if active else None,
    )
    values: dict[str, object] = {
        "athlete_id": ATHLETE_ID,
        "authorization_id": 77,
        "ethnicity": ImdertyEthnicity.MESTIZO,
        "disability": ImdertyDisability.VISUAL,
        "conflict_victim": ImdertyYesNo.no,
    }
    values.update(overrides)
    data = AthleteSensitiveData(**values)
    data.authorization = authorization
    return data


def _row(athlete: Athlete, sensitive: dict[int, AthleteSensitiveData] | None = None):
    result = build_rows([athlete], {}, MONTH, sensitive=sensitive)
    assert len(result) == 1
    return result[0]


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


def test_unconfirmed_split_writes_last_name_in_c_and_blank_d() -> None:
    row = _row(_athlete(profile=_profile(first_surname="Pérez", second_surname="Gómez")))
    assert row["B"] == "Ana Sofía"
    assert row["C"] == "Pérez Gómez"
    assert row.get("D") is None


def test_no_profile_writes_last_name_in_c() -> None:
    row = _row(_athlete())
    assert row["C"] == "Pérez Gómez"
    assert row.get("D") is None


def test_confirmed_split_writes_both_surnames() -> None:
    profile = _profile(
        first_surname="Pérez",
        second_surname="Gómez",
        surname_split_confirmed_at=datetime(2026, 7, 1),
    )
    row = _row(_athlete(profile=profile))
    assert row["C"] == "Pérez"
    assert row["D"] == "Gómez"


def test_stale_confirmation_falls_back_to_last_name() -> None:
    # last_name changed after the split was confirmed and the split no longer rebuilds it
    profile = _profile(
        first_surname="Pérez",
        second_surname="Gómez",
        surname_split_confirmed_at=datetime(2026, 7, 1),
    )
    row = _row(_athlete(last_name="Ramírez Soto", profile=profile))
    assert row["C"] == "Ramírez Soto"
    assert row.get("D") is None


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_identity_columns() -> None:
    profile = _profile(
        document_type=ImdertyDocumentType.ti,
        document_number="0012345678",
        school="Institución Educativa Ficticia",
        grade=ImdertyGrade.g6,
    )
    row = _row(_athlete(profile=profile, sex=Sex.M))
    assert row["G"] == "T.I"
    assert row["H"] == "0012345678"  # text, leading zeros kept
    assert row["I"] == "HOMBRE"
    assert row["J"] == "Institución Educativa Ficticia"
    assert row["K"] == "6"
    assert row["E"] == date(2014, 1, 1)


def test_grade_label_non_numeric() -> None:
    row = _row(_athlete(profile=_profile(grade=ImdertyGrade.no_escolarizado)))
    assert row["K"] == "NO ESCOLARIZADO"


def test_sex_female() -> None:
    assert _row(_athlete(sex=Sex.F))["I"] == "MUJER"


def test_missing_profile_leaves_identity_blank() -> None:
    row = _row(_athlete())
    for column in ("G", "H", "J", "K", "P", "Q", "S", "T"):
        assert row.get(column) is None


# ---------------------------------------------------------------------------
# Sensitive block
# ---------------------------------------------------------------------------


def test_sensitive_columns_with_active_authorization() -> None:
    data = _sensitive(conflict_victim=ImdertyYesNo.si)
    row = _row(_athlete(), {ATHLETE_ID: data})
    assert row["L"] == "VISUAL"
    assert row["N"] == "SI"
    assert row["O"] == "MESTIZO"


def test_sensitive_columns_blank_without_data() -> None:
    row = _row(_athlete())
    for column in ("L", "N", "O"):
        assert row.get(column) is None


def test_sensitive_columns_blank_with_withdrawn_authorization() -> None:
    row = _row(_athlete(), {ATHLETE_ID: _sensitive(active=False)})
    for column in ("L", "N", "O"):
        assert row.get(column) is None


def test_sensitive_row_of_another_athlete_is_ignored() -> None:
    other = _sensitive()
    other.athlete_id = ATHLETE_ID + 1
    row = _row(_athlete(), {ATHLETE_ID: other})
    for column in ("L", "N", "O"):
        assert row.get(column) is None


def test_victim_unset_stays_blank() -> None:
    row = _row(_athlete(), {ATHLETE_ID: _sensitive(conflict_victim=None)})
    assert row.get("N") is None
    assert row["L"] == "VISUAL"


def test_column_m_is_never_written() -> None:
    profile = _profile(
        document_type=ImdertyDocumentType.rc,
        document_number="123",
        eps="EPS Ficticia",
        address="Calle 1 # 2-3",
        barrio=ImdertyBarrio(id=1, name="BARRIO FICTICIO", zone="1"),
        barrio_id=1,
    )
    row = _row(_athlete(profile=profile), {ATHLETE_ID: _sensitive()})
    assert "M" not in row
    assert set(row) - {"B", "C", "D", "E", "G", "H", "I", "J", "K", "L", "N", "O", "P", "Q", "S", "T"} == set()
    assert set(row) <= PARTICIPANT_COLUMNS


# ---------------------------------------------------------------------------
# Address and contact
# ---------------------------------------------------------------------------


def test_address_barrio_eps() -> None:
    profile = _profile(
        address="Calle 1 # 2-3",
        barrio=ImdertyBarrio(id=1, name="BARRIO FICTICIO", zone="1"),
        barrio_id=1,
        eps="EPS Ficticia",
    )
    row = _row(_athlete(profile=profile))
    assert row["P"] == "Calle 1 # 2-3"
    assert row["Q"] == "BARRIO FICTICIO"
    assert row["S"] == "EPS Ficticia"


def test_other_municipality_label() -> None:
    row = _row(_athlete(profile=_profile(other_municipality=True)))
    assert row["Q"] == "OTRO MUNICIPIO"


def test_no_barrio_blank() -> None:
    assert _row(_athlete(profile=_profile()))["Q"] is None


@pytest.mark.parametrize(
    ("own_phone", "guardians", "expected"),
    [
        # own phone wins
        ("3000000001", [(1, "3000000002", True)], "3000000001"),
        # primary contact next
        (None, [(1, "3000000003", False), (2, "3000000004", True)], "3000000004"),
        # primary without phone → first linked guardian (earliest link)
        (None, [(2, "3000000005", False), (1, "3000000006", False), (3, None, True)], "3000000006"),
        # no primary → first linked guardian
        ("  ", [(5, "3000000007", False), (9, "3000000008", False)], "3000000007"),
        # nobody has a phone → blank
        (None, [(1, None, False)], None),
        # no guardians at all → blank
        (None, [], None),
    ],
)
def test_phone_chain(
    own_phone: str | None,
    guardians: list[tuple[int, str | None, bool]],
    expected: str | None,
) -> None:
    athlete = _athlete(profile=_profile(phone=own_phone), guardians=guardians)
    assert _row(athlete)["T"] == expected


def test_phone_from_guardian_without_profile() -> None:
    athlete = _athlete(guardians=[(1, "3000000009", False)])
    assert _row(athlete)["T"] == "3000000009"


# ---------------------------------------------------------------------------
# Integration with the writer
# ---------------------------------------------------------------------------


def test_rows_are_accepted_by_build_sheet() -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    from app.services.imderty.workbook import (
        FIRST_DATA_ROW,
        MONTH_SHEET_NAMES,
        build_sheet,
    )

    profile = _profile(
        document_type=ImdertyDocumentType.ti,
        document_number="0012345678",
        other_municipality=True,
        phone="3000000001",
        eps="EPS Ficticia",
        grade=ImdertyGrade.g5,
    )
    rows = build_rows(
        [_athlete(profile=profile)], {}, MONTH, sensitive={ATHLETE_ID: _sensitive()}
    )
    content = build_sheet([MONTH], {MONTH: rows}, None, [])
    wb = load_workbook(BytesIO(content))
    ws = wb[MONTH_SHEET_NAMES[MONTH.month - 1]]
    r = FIRST_DATA_ROW
    assert ws[f"H{r}"].value == "0012345678"
    assert ws[f"Q{r}"].value == "OTRO MUNICIPIO"
    assert ws[f"K{r}"].value == "5"
    assert ws[f"M{r}"].value is None
    assert ws[f"T{r}"].value == "3000000001"


def test_module_exports_loader() -> None:
    assert callable(rows_mod.load_authorized_sensitive_data)


# ---------------------------------------------------------------------------
# Loader (DB): only rows backed by an active authorization come back
# ---------------------------------------------------------------------------

_SENSITIVE_TABLES = ("athlete_sensitive_authorizations", "athlete_sensitive_data")


@pytest.fixture
async def _sensitive_tables(imderty_engine):  # type: ignore[no-untyped-def]
    from app.models import Base

    async with imderty_engine.begin() as conn:
        for name in _SENSITIVE_TABLES:
            await conn.run_sync(
                lambda c, name=name: Base.metadata.tables[name].create(c, checkfirst=True)
            )
    yield


async def test_loader_returns_only_active_authorizations(
    _sensitive_tables, imderty_scenario
) -> None:  # type: ignore[no-untyped-def]
    s = imderty_scenario
    session = s.session
    active_id = s.parent_athlete_one_id
    withdrawn_id = s.parent_athlete_two_id
    session.add_all(
        [
            AthleteSensitiveAuthorization(
                id=501,
                athlete_id=active_id,
                guardian_user_id=s.parent_user_id,
                authorized_on=date(2026, 7, 1),
                recorded_by_user_id=s.coach_user_id,
                active_key=active_id,
            ),
            AthleteSensitiveAuthorization(
                id=502,
                athlete_id=withdrawn_id,
                guardian_user_id=s.parent_user_id,
                authorized_on=date(2026, 7, 1),
                recorded_by_user_id=s.coach_user_id,
                withdrawn_at=datetime(2026, 7, 10),
                active_key=None,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            AthleteSensitiveData(
                athlete_id=active_id,
                authorization_id=501,
                ethnicity=ImdertyEthnicity.RAIZAL,
                disability=ImdertyDisability.NA,
                conflict_victim=ImdertyYesNo.no,
            ),
            # Inconsistent leftover pointing at a withdrawn authorization.
            AthleteSensitiveData(
                athlete_id=withdrawn_id,
                authorization_id=502,
                ethnicity=ImdertyEthnicity.MESTIZO,
                disability=ImdertyDisability.NA,
                conflict_victim=ImdertyYesNo.si,
            ),
        ]
    )
    await session.commit()
    session.expunge_all()

    loaded = await rows_mod.load_authorized_sensitive_data(
        session, [active_id, withdrawn_id, s.two_guardians_athlete_id]
    )
    assert set(loaded) == {active_id}
    assert loaded[active_id].authorization.is_active
    assert await rows_mod.load_authorized_sensitive_data(session, []) == {}
