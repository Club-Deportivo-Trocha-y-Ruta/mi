"""Fixtures locales para tests del módulo race.

Convención: los PDFs Válida IV se copian a ``backend/tests/fixtures/race/``
durante el bootstrap (Paso 3). Estos fixtures son públicos por publicación
oficial de la Federación Colombiana de Ciclismo (edge-cases.md §6.3) — no
hay riesgo de privacidad al versionarlos.

Para los tests del ingestor (Paso 4) se incluye un ``FakeAsyncSession`` que
emula el subconjunto de la API ``sqlalchemy.ext.asyncio.AsyncSession`` que
usa el ``RaceIngestor``: ``execute(select(...))``, ``add(obj)``, ``flush()``,
``commit()``, ``rollback()``. La razón: ni aiosqlite ni MySQL están disponibles
en este sandbox, y la convención del proyecto en
``tests/test_training_session_service.py`` ya usa mocks/fakes para evitar DB
real. Este fake es estricto (lanza ``RuntimeError`` ante queries no soportadas)
para no enmascarar bugs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_import import RaceImport
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries

_FIXTURES_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "race"


# ---------------------------------------------------------------------------
# PDFs fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def valida_iv_resultados_pdf() -> Path:
    """Ruta al PDF RESULTADOS Válida IV 2026 (Cali, 17-mayo)."""
    p = _FIXTURES_ROOT / "valida_iv_2026_resultados.pdf"
    assert p.exists(), f"Fixture faltante: {p}"
    return p


@pytest.fixture(scope="session")
def valida_iv_general_pdf() -> Path:
    """Ruta al PDF GENERAL acumulado tras Válida IV 2026."""
    p = _FIXTURES_ROOT / "valida_iv_2026_general.pdf"
    assert p.exists(), f"Fixture faltante: {p}"
    return p


# ---------------------------------------------------------------------------
# FakeAsyncSession: in-memory mini-DB para tests del ingestor
# ---------------------------------------------------------------------------


@dataclass
class _Store:
    """Estado interno del fake — un dict por tabla más un counter de IDs."""

    series: dict[int, RaceSeries] = field(default_factory=dict)
    events: dict[int, RaceEvent] = field(default_factory=dict)
    categories: dict[int, RaceCategory] = field(default_factory=dict)
    competitors: dict[int, RaceCompetitor] = field(default_factory=dict)
    results: dict[int, RaceResult] = field(default_factory=dict)
    imports: dict[int, RaceImport] = field(default_factory=dict)

    # Pending: objetos agregados via session.add() pero aún sin flush
    pending: list[Any] = field(default_factory=list)

    # Snapshots para rollback (deep-ish copy de la situación pre-tx)
    snapshot: Optional[dict[str, dict]] = None

    # Counters de PK por tabla
    _id_counters: dict[str, Iterator[int]] = field(
        default_factory=lambda: {
            "series": count(1),
            "events": count(1),
            "categories": count(1),
            "competitors": count(1),
            "results": count(1),
            "imports": count(1),
        }
    )

    def next_id(self, table: str) -> int:
        return next(self._id_counters[table])

    def table_for(self, obj: Any) -> str:
        if isinstance(obj, RaceSeries):
            return "series"
        if isinstance(obj, RaceEvent):
            return "events"
        if isinstance(obj, RaceCategory):
            return "categories"
        if isinstance(obj, RaceCompetitor):
            return "competitors"
        if isinstance(obj, RaceResult):
            return "results"
        if isinstance(obj, RaceImport):
            return "imports"
        raise RuntimeError(f"FakeAsyncSession: tipo no soportado {type(obj)!r}")

    def get_table_dict(self, table: str) -> dict:
        return getattr(self, table)


class _FakeResult:
    """Emula el ``Result`` de SQLAlchemy con sólo lo que usa el ingestor."""

    def __init__(self, rows: list[Any]):
        # rows: lista de instancias de modelo (NO tuplas — ingestor solo usa
        # select(Model) y select(Model.col) sobre columnas escalares).
        self._rows = rows

    def scalar_one_or_none(self) -> Optional[Any]:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise RuntimeError(
                f"FakeAsyncSession: scalar_one_or_none() recibió {len(self._rows)} filas"
            )
        return self._rows[0]

    def scalars(self) -> "_FakeScalars":
        return _FakeScalars(self._rows)


class _FakeScalars:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Optional[Any]:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeAsyncSession:
    """Mini-AsyncSession que el ``RaceIngestor`` puede consumir sin DB real.

    Soporta exactamente las queries que el ingestor ejecuta:

    - ``select(RaceSeries).where(name=..., season_year=...)``.
    - ``select(RaceEvent).where(series_id=..., sequence_number=...)``.
    - ``select(RaceImport).where(sha256=..., status=committed)``.
    - ``select(RaceCategory)`` (todos).
    - ``select(RaceCompetitor).where(normalized_name=...)``.
    - ``select(RaceResult.competitor_id).where(event_id=..., category_id=...)``.

    Cualquier otra forma de query lanza ``RuntimeError`` para no enmascarar
    bugs del servicio bajo prueba.

    Limitaciones reconocidas (no es una DB real):
    - No valida UNIQUE constraints físicamente — el ingestor consulta antes
      de insertar, así que la idempotencia se valida por la lógica del
      servicio, no por la DB.
    - ``commit()`` confirma los pending → tablas.
    - ``rollback()`` restaura el snapshot pre-tx (si existe).
    """

    def __init__(self, store: Optional[_Store] = None) -> None:
        self.store = store or _Store()
        self._begin_snapshot()

    # -- snapshot / rollback support -------------------------------------

    def _begin_snapshot(self) -> None:
        # Snapshot superficial de PKs comprometidos (no de atributos mutables) —
        # suficiente para los tests que verifican commit vs rollback.
        self.store.snapshot = {
            "series": dict(self.store.series),
            "events": dict(self.store.events),
            "categories": dict(self.store.categories),
            "competitors": dict(self.store.competitors),
            "results": dict(self.store.results),
            "imports": dict(self.store.imports),
        }

    # -- API que consume el ingestor -------------------------------------

    async def execute(self, stmt: Any) -> _FakeResult:
        """Mini-router que matchea la statement contra los patrones soportados."""
        return _FakeResult(self._evaluate(stmt))

    def _evaluate(self, stmt: Any) -> list[Any]:
        # Importamos aquí para evitar import circular en módulo de fixtures
        from sqlalchemy.sql.selectable import Select

        if not isinstance(stmt, Select):
            raise RuntimeError(f"FakeAsyncSession: stmt no soportado {type(stmt)!r}")

        # Identificar la entidad/columna seleccionada
        cols = stmt.selected_columns
        col_names = [c.name for c in cols]

        # Identificar la FROM clause primaria
        froms = list(stmt.get_final_froms())
        if not froms:
            raise RuntimeError("FakeAsyncSession: select sin FROM")
        from_table = froms[0].name  # nombre de tabla del modelo

        # Construir lista candidata desde el store
        table_map = {
            "race_series": ("series", self.store.series),
            "race_events": ("events", self.store.events),
            "race_categories": ("categories", self.store.categories),
            "race_competitors": ("competitors", self.store.competitors),
            "race_results": ("results", self.store.results),
            "race_imports": ("imports", self.store.imports),
        }
        if from_table not in table_map:
            raise RuntimeError(f"FakeAsyncSession: tabla {from_table!r} no soportada")
        _, store_dict = table_map[from_table]

        # Aplicar WHERE
        whereclause = stmt.whereclause
        rows = list(store_dict.values())
        if whereclause is not None:
            rows = [r for r in rows if self._row_matches(r, whereclause)]

        # Si la query es select(Col) (no select(Model)), proyectamos
        # — el ingestor sólo usa esto para ``select(RaceResult.competitor_id)``.
        # En ese caso retornamos los valores escalares.
        if col_names and len(col_names) == 1 and col_names[0] != "id" and from_table != table_map.get(from_table, (None,))[0]:
            # heurística: si el único col seleccionado es distinto del id implícito
            pass  # caemos al manejo abajo
        if len(cols) == 1:
            col = cols[0]
            # Si la selección es la entidad completa (Model.__table__.columns[0])
            # SQLAlchemy expone primera columna; chequeamos por nombre tabla:
            # Mejor heurística: si el number of columns == número de columnas de la tabla → entidad
            # Como no es trivial, distinguimos por presence of selected column distinta a 'id'
            if col.name == "competitor_id":
                return [r.competitor_id for r in rows]

        return rows

    def _row_matches(self, row: Any, whereclause: Any) -> bool:
        """Evalúa el ``whereclause`` contra una fila instancia de modelo.

        Soporta:
        - ``col == value`` (BinaryExpression con op eq).
        - ``a AND b`` (BooleanClauseList con op and_).
        """
        from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList
        from sqlalchemy.sql import operators

        if isinstance(whereclause, BooleanClauseList):
            if whereclause.operator is operators.and_:
                return all(self._row_matches(row, c) for c in whereclause.clauses)
            if whereclause.operator is operators.or_:
                return any(self._row_matches(row, c) for c in whereclause.clauses)
            raise RuntimeError(
                f"FakeAsyncSession: operador booleano no soportado {whereclause.operator}"
            )

        if isinstance(whereclause, BinaryExpression):
            left = whereclause.left
            right = whereclause.right
            op = whereclause.operator
            if op is operators.eq:
                col_name = getattr(left, "name", None) or getattr(left, "key", None)
                if col_name is None:
                    raise RuntimeError(f"FakeAsyncSession: left sin name: {left!r}")
                # right es un BindParameter
                right_val = getattr(right, "value", right)
                lhs = getattr(row, col_name, None)
                # Coerce enum si lhs es Enum y right_val es str
                if hasattr(lhs, "value") and isinstance(right_val, str):
                    return lhs.value == right_val or lhs == right_val
                return lhs == right_val
            raise RuntimeError(f"FakeAsyncSession: op no soportada {op!r}")

        raise RuntimeError(
            f"FakeAsyncSession: whereclause no soportada {type(whereclause)!r}"
        )

    def add(self, obj: Any) -> None:
        self.store.pending.append(obj)

    async def flush(self) -> None:
        """Asigna IDs a pending y los promueve a tablas."""
        for obj in list(self.store.pending):
            table = self.store.table_for(obj)
            if getattr(obj, "id", None) is None:
                obj.id = self.store.next_id(table)
            self.store.get_table_dict(table)[obj.id] = obj
        self.store.pending.clear()

    async def commit(self) -> None:
        await self.flush()
        self._begin_snapshot()

    async def rollback(self) -> None:
        # Restaurar snapshot pre-tx
        snap = self.store.snapshot or {}
        self.store.series = dict(snap.get("series", {}))
        self.store.events = dict(snap.get("events", {}))
        self.store.categories = dict(snap.get("categories", {}))
        self.store.competitors = dict(snap.get("competitors", {}))
        self.store.results = dict(snap.get("results", {}))
        self.store.imports = dict(snap.get("imports", {}))
        self.store.pending.clear()


# ---------------------------------------------------------------------------
# Seed de categorías (26 oficiales Copa Valle 2026)
# ---------------------------------------------------------------------------


_SEED_CATEGORIES: list[tuple[str, str, CategoryGender, int | None, int | None, CategoryTier | None, int]] = [
    ("TET_SP",   "Teteros Sin Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 10),
    ("TET_CP",   "Teteros Con Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 11),
    ("PRE_A",    "Preinfantil A",             CategoryGender.M,     6,    7,    CategoryTier.menores, 20),
    ("PRE_B",    "Preinfantil B",             CategoryGender.M,     7,    8,    CategoryTier.menores, 21),
    ("PRE_A_F",  "Preinfantil A Femenino",    CategoryGender.F,     6,    7,    CategoryTier.menores, 22),
    ("PRE_B_F",  "Preinfantil B Femenino",    CategoryGender.F,     7,    8,    CategoryTier.menores, 23),
    ("INF_A",    "Infantil A",                CategoryGender.M,     9,    10,   CategoryTier.menores, 30),
    ("INF_B",    "Infantil B",                CategoryGender.M,     11,   12,   CategoryTier.menores, 31),
    ("INF_A_F",  "Infantil A Femenino",       CategoryGender.F,     9,    10,   CategoryTier.menores, 32),
    ("INF_B_F",  "Infantil B Femenino",       CategoryGender.F,     11,   12,   CategoryTier.menores, 33),
    ("PJUV_A",   "Prejuvenil A",              CategoryGender.M,     13,   13,   CategoryTier.menores, 40),
    ("PJUV_B",   "Prejuvenil B",              CategoryGender.M,     14,   14,   CategoryTier.menores, 41),
    ("PJUV_A_F", "Prejuvenil A Femenino",     CategoryGender.F,     13,   13,   CategoryTier.menores, 42),
    ("PJUV_B_F", "Prejuvenil B Femenino",     CategoryGender.F,     14,   14,   CategoryTier.menores, 43),
    ("JUN_M",    "Junior",                    CategoryGender.M,     15,   16,   CategoryTier.juvenil, 50),
    ("JUN_F",    "Junior Femenino",           CategoryGender.F,     15,   16,   CategoryTier.juvenil, 51),
    ("ELITE_M",  "Elite",                     CategoryGender.M,     17,   None, CategoryTier.adulto,  60),
    ("ELITE_F",  "Elite Femenino",            CategoryGender.F,     17,   None, CategoryTier.adulto,  61),
    ("PROMO",    "Promocional",               CategoryGender.MIXED, None, None, CategoryTier.adulto,  70),
    ("MAS_A",    "Master A",                  CategoryGender.M,     30,   39,   CategoryTier.master,  80),
    ("MAS_B1",   "Master B1",                 CategoryGender.M,     40,   44,   CategoryTier.master,  81),
    ("MAS_B2",   "Master B2",                 CategoryGender.M,     45,   49,   CategoryTier.master,  82),
    ("MAS_C1",   "Master C1",                 CategoryGender.M,     50,   54,   CategoryTier.master,  83),
    ("MAS_C2",   "Master C2",                 CategoryGender.M,     55,   59,   CategoryTier.master,  84),
    ("MAS_D",    "Master D",                  CategoryGender.M,     60,   None, CategoryTier.master,  85),
    ("MAS_F",    "Master Femenino",           CategoryGender.F,     30,   None, CategoryTier.master,  90),
]


def _build_seeded_store() -> _Store:
    store = _Store()
    for code, label, sex, age_min, age_max, tier, sort_order in _SEED_CATEGORIES:
        cid = store.next_id("categories")
        cat = RaceCategory(
            id=cid,
            code=code,
            label=label,
            sex=sex,
            age_min=age_min,
            age_max=age_max,
            tier=tier,
            sort_order=sort_order,
            is_active=True,
        )
        store.categories[cid] = cat
    return store


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    """Sesión fake con las 26 categorías ya seedeadas."""
    return FakeAsyncSession(store=_build_seeded_store())
