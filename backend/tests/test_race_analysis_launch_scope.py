"""Un entrenador no puede lanzar ni listar análisis de menores de otro club.

Hallazgos **H1 y H2** de la revisión de seguridad de US6 (T080,
`checklists/integration-review.md`). La matriz de
`contracts/scope-ai-imports.md` §1.4 cubre **operar** una corrida que ya
existe, pero no **crearla**, y ese hueco dejaba dos agujeros:

- **H1**: `POST /api/race-analysis/runs` y el lanzamiento grupal no miraban el
  club del deportista. Un entrenador del club B lanzaba un análisis sobre una
  menor del club A: su nombre entraba en `forbidden_names` y salía hacia el
  proveedor de IA, se persistía un insight en su ficha, y la corrida nacía
  además inalcanzable para quien la lanzó, porque el chequeo de club sí actúa
  al leerla.
- **H2**: `GET /api/race-analysis/race-events/{id}/runs` resolvía nombres de
  deportistas desde los resultados del evento sin filtrar por club. Le
  entregaba a un entrenador ajeno el **nombre completo** de una menor y un
  `run_id` válido — que es, de paso, la única forma práctica de conseguir ids
  de corrida ajenos, porque son `uuid4`.

Una válida de la Copa Valle la corren menores de varios clubes: el evento es
de un tercero, así que el club nunca se puede inferir del evento, solo del
deportista. De ahí que el filtro viva en `resolve_group_members`.

Vía offline aiosqlite, con motor y subconjunto de tablas propios — no usa el
fixture `client` de `tests/conftest.py`, que exige MySQL real.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.race.group_launch import resolve_group_members

# `asyncio_mode = "auto"` (pyproject) ya reconoce las corrutinas: un
# `pytestmark` de asyncio marcaría también las pruebas síncronas de acá.


class _MembresiaFalsa:
    def __init__(self, club_id: int, role_in_club: ClubRole) -> None:
        self.club_id = club_id
        self.role_in_club = role_in_club


class _UsuarioFalso:
    """Doble mínimo: `coach_club_ids` solo lee `club_memberships`."""

    def __init__(self, user_id: int, role: UserRole, club_ids: tuple[int, ...]) -> None:
        self.id = user_id
        self.role = role
        self.club_memberships = [
            _MembresiaFalsa(cid, ClubRole.coach) for cid in club_ids
        ]


def test_el_ayudante_de_clubes_no_acota_al_administrador() -> None:
    """El administrador conserva su bypass: `None` es "sin filtro"."""
    from app.routers.race_analysis import _launcher_club_ids

    admin = _UsuarioFalso(1, UserRole.admin, ())
    assert _launcher_club_ids(admin) is None


def test_el_ayudante_de_clubes_acota_al_entrenador_a_sus_clubes() -> None:
    from app.routers.race_analysis import _launcher_club_ids

    coach = _UsuarioFalso(2, UserRole.coach, (7,))
    assert _launcher_club_ids(coach) == {7}


def test_un_entrenador_sin_club_no_alcanza_a_nadie() -> None:
    """Conjunto vacío, no `None`: un `None` sería el filtro del administrador
    y le abriría el evento entero a alguien sin club.
    """
    from app.routers.race_analysis import _launcher_club_ids

    huerfano = _UsuarioFalso(3, UserRole.coach, ())
    assert _launcher_club_ids(huerfano) == set()


async def test_resolve_group_members_acota_por_club(monkeypatch) -> None:
    """El filtro llega a la consulta como `athletes.club_id IN (...)`.

    Se inspecciona el SQL compilado en vez de sembrar el evento entero: lo que
    esta prueba tiene que fijar es que el predicado **exista**, que es
    justamente lo que faltaba.
    """
    capturado: dict[str, str] = {}

    class _ResultadoVacio:
        def all(self):
            return []

    class _SesionQueCaptura:
        async def execute(self, stmt):
            capturado["sql"] = str(stmt)
            return _ResultadoVacio()

    await resolve_group_members(
        _SesionQueCaptura(), race_event_id=77, athlete_ids=None, club_ids={2}
    )
    assert "club_id" in capturado["sql"], (
        "sin el predicado de club, el listado del evento entrega nombres de "
        "menores de otros clubes (H2)"
    )


async def test_resolve_group_members_sin_club_ids_no_filtra() -> None:
    """`None` sigue significando "sin filtro" — es lo que pasa el admin."""
    capturado: dict[str, str] = {}

    class _ResultadoVacio:
        def all(self):
            return []

    class _SesionQueCaptura:
        async def execute(self, stmt):
            capturado["sql"] = str(stmt)
            return _ResultadoVacio()

    await resolve_group_members(
        _SesionQueCaptura(), race_event_id=77, athlete_ids=None, club_ids=None
    )
    assert "club_id" not in capturado["sql"]
