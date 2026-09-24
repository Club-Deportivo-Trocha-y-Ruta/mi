"""Revisión de identidad de competidores (feature 044, US4 — research R-06).

El coach decide quién es quién; nada se fusiona solo. Este módulo arma la cola
de candidatos, registra las decisiones y las revierte
(``contracts/identity-review-api.md``).

Estructura — núcleo puro + cáscara de base de datos:

- ``load_universe`` (async): lee competidores existentes, sus firmas y
  resultados, y las filas de los imports **en staging** (no confirmados) a
  través de un ``rows_loader`` inyectado por el router. Devuelve
  ``IdentityRecord`` inmutables: uno por terna observada
  ``(normalized_name, club_norm, city_norm)``.
- ``build_candidates`` (sync, puro, sin I/O): corre en un hilo de trabajo.
  Comparación bloqueada por apellido compartido, así que el trabajo queda
  muy por debajo de n².
- ``persist_candidates`` (async): idempotente por ``pair_hash``; nunca pisa
  una decisión tomada.
- ``rebuild`` compone los tres con un timeout opcional y borra los
  candidatos ``pending`` que quedaron fuera de alcance.

Alcance (decisión del dueño 2026-09-22): la cola solo pregunta por pares en
los que **al menos un lado es un competidor vinculado a un atleta del club**
(``athlete_id`` no nulo). Lo que involucra solo a terceros lo resuelve
``IdentityResolver`` sin preguntar y, por defecto, separado.

La clave de un registro es su terna, no el id del competidor: así el
``pair_hash`` de un par es el mismo antes y después del commit, y una
pregunta respondida no se vuelve a hacer.

Privacidad: ningún log, excepción ni fila de auditoría lleva nombre, club o
ciudad — solo ids, conteos y el ``pair_hash``. Los snapshots de la tabla son
de la misma clase de sensibilidad que ``race_competitors`` y solo salen por
``record_view`` (coach/admin). No hay aquí ningún parámetro público que
reciba ids de competidor: se opera sobre ids de candidato (candado de
terceros, ``tests/privacy/test_third_party_lock.py``).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Optional

from rapidfuzz import fuzz
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_event import RaceEvent
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.user import User
from app.services.audit import AuditEntityType, record_audit
from app.services.race.identity_resolver import (
    Triple,
    band_discriminator,
    discriminator_compatible,
    record_discriminator,
    record_triple,
    signature_triple,
)
from app.services.race.normalizer import normalize_club, normalize_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes (research R-06, revisión T043)
# ---------------------------------------------------------------------------

#: ``token_set_ratio`` mínimo para sospechar que dos nombres distintos son la
#: misma persona.
SAME_PERSON_MIN_SCORE = 90

#: Por debajo de este ``token_set_ratio`` dos clubes (o dos ciudades) se
#: consideran distintos. Solo cuenta si difieren **ambos**.
DIVERGENCE_MAX_SCORE = 70

#: Largo mínimo de un token de apellido para la clave de bloqueo.
_BLOCKING_TOKEN_MIN_LEN = 3

DEFAULT_PAGE_SIZE = 20

# Señales — valores estables, se persisten en ``signals`` y la UI los traduce.
SIGNAL_EXTRA_SURNAME = "extra_or_missing_surname"
SIGNAL_INVERTED_SURNAMES = "inverted_surname_order"
SIGNAL_SPELLING_VARIANT = "spelling_variant"
SIGNAL_SAME_VALIDA_TWO_CATEGORIES = "same_valida_two_categories"
SIGNAL_SAME_VALIDA_SAME_CATEGORY = "same_valida_same_category"
SIGNAL_SEX_CONFLICT = "sex_conflict"
SIGNAL_AGE_PATH_BACKWARDS = "age_path_backwards"
SIGNAL_CLUB_AND_CITY_DIFFER = "club_and_city_differ"
SIGNAL_MULTIPLE_EXISTING_COMPETITORS = "multiple_existing_competitors"
#: Misma terna (nombre, club, ciudad) con apariciones en categorías de edad
#: incompatibles — el caso padre/hijo del mismo club (decisión 2026-09-21).
SIGNAL_AGE_INCOMPATIBLE = "age_incompatible_categories"

#: Clave interna del snapshot con los resultados que una decisión
#: ``same_person`` movió o adjuntó. Nunca se serializa (``record_view``).
_ATTACHED_KEY = "attached_result_ids"

#: Ids de ``race_results`` confirmados que caen en un sub-registro separado
#: por categoría; ``decide(different_people)`` los usa para partir un
#: competidor que ya mezclaba a dos personas. Nunca se serializa.
_RESULT_IDS_KEY = "result_ids"

#: Campos del snapshot que salen hacia el coach (``IdentityRecordRead``).
_PUBLIC_RECORD_FIELDS = (
    "name_printed",
    "club",
    "city",
    "seasons",
    "category_labels",
    "competitor_id",
    "athlete_linked",
)

_STAGED_STATUSES = (RaceImportStatus.pending, RaceImportStatus.dry_run)

#: ``valida_num`` de la aparición que aporta GENERAL. GENERAL es el acumulado
#: de la temporada, no una válida: con un número real ``_shared_valida``
#: trataría a la variante de GENERAL y a la atleta que corrió esa válida como
#: dos personas distintas y apagaría justo el candidato que el candado busca.
#: Ninguna válida real usa 0 (regulares 1..7, CD 99).
GENERAL_VALIDA_NUM = 0


@dataclass(frozen=True)
class ImportRows:
    """Filas de una carga que ``load_universe`` incorpora al universo:
    ``results`` (RESULTADOS por código de categoría) y ``general`` (GENERAL por
    código de categoría, si la carga lo trae).

    El ingestor crea/actualiza competidores desde GENERAL en todas las
    categorías (research R-08, nota 1 del G2), así que sus ternas también son
    parte de lo que el coach debe poder revisar antes del commit.
    """

    results: Mapping[str, Sequence[Any]]
    general: Mapping[str, Sequence[Any]] = field(default_factory=dict)


#: Un ``rows_loader`` puede devolver solo RESULTADOS (``Mapping``) o
#: ``ImportRows`` con GENERAL incluido.
RowsLoader = Callable[[RaceImport], Awaitable[Mapping[str, Sequence[Any]] | ImportRows]]


# ---------------------------------------------------------------------------
# Excepciones de dominio (el router las traduce a HTTP)
# ---------------------------------------------------------------------------


class CandidateNotFound(LookupError):
    """No existe el candidato (404)."""


class CandidateNotPending(RuntimeError):
    """Se intentó decidir un candidato que ya no está ``pending`` (409)."""


class CandidateNotDecided(RuntimeError):
    """Se intentó revertir un candidato que está ``pending`` (409)."""


class IdentityDecisionConflict(RuntimeError):
    """La decisión no se puede aplicar sin perder datos (409).

    ``code`` es estable: ``linked_to_different_athletes``,
    ``shared_valida``, ``already_same_competitor``,
    ``linked_competitor_ambiguous`` (hay que partir un competidor vinculado a
    un atleta y no se sabe cuál de las dos personas es el atleta: el coach
    desvincula, decide y vuelve a vincular).
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"conflicto de identidad: {code}")
        self.code = code


# ---------------------------------------------------------------------------
# Objetos de valor del núcleo puro
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Appearance:
    """Una aparición en una válida: ``event_key = (series_id, valida_num)``."""

    event_key: tuple[int, int]
    season: int
    category_code: str
    age_rank: Optional[int]
    #: Sexo y rango de edad de la fila del catálogo (para el discriminador).
    cat_sex: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    #: Id del ``race_result`` si la aparición ya está confirmada.
    result_id: Optional[int] = None


@dataclass(frozen=True)
class IdentityRecord:
    """Una terna observada, con lo que se sabe de ella."""

    key: str
    name_printed: str
    normalized_name: str
    club: str
    club_norm: str
    city: str
    city_norm: str
    sex: Optional[str]
    competitor_id: Optional[int]
    athlete_linked: bool
    appearances: tuple[Appearance, ...] = ()
    category_labels: tuple[str, ...] = ()
    extra_seasons: tuple[int, ...] = ()
    #: ``''`` salvo en un registro separado por categoría (misma terna).
    discriminator: str = ""

    @property
    def triple(self) -> Triple:
        return (self.normalized_name, self.club_norm, self.city_norm)

    @property
    def seasons(self) -> list[int]:
        return sorted({a.season for a in self.appearances} | set(self.extra_seasons))

    @property
    def category_codes(self) -> list[str]:
        return sorted({a.category_code for a in self.appearances})

    def snapshot(self) -> dict[str, Any]:
        """Snapshot persistido en ``left_record`` / ``right_record``."""
        snap: dict[str, Any] = {
            "key": self.key,
            "name_printed": self.name_printed,
            "normalized_name": self.normalized_name,
            "club": self.club,
            "club_norm": self.club_norm,
            "city": self.city,
            "city_norm": self.city_norm,
            "seasons": self.seasons,
            "category_codes": self.category_codes,
            "category_labels": list(self.category_labels),
            "sex": self.sex,
            "competitor_id": self.competitor_id,
            "athlete_linked": self.athlete_linked,
        }
        if self.discriminator:
            snap["discriminator"] = self.discriminator
            snap[_RESULT_IDS_KEY] = sorted(
                a.result_id for a in self.appearances if a.result_id is not None
            )
        return snap


@dataclass(frozen=True)
class CandidateDraft:
    """Candidato calculado por ``build_candidates``, aún no persistido."""

    kind: IdentityCandidateKind
    pair_hash: str
    left: dict[str, Any]
    right: dict[str, Any]
    score: int
    signals: list[str]
    linked_athlete_involved: bool


@dataclass(frozen=True)
class Universe:
    records: list[IdentityRecord]
    imports_scanned: int
    imports_unreadable: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class RebuildResult:
    """Retorno de ``rebuild``: ``{created, unchanged, pending}`` del contrato
    más ``removed`` (candidatos ``pending`` borrados por quedar fuera de
    alcance, decisión 2026-09-22) e ``imports_unreadable`` (ids de imports en
    staging cuyo archivo no se pudo leer — sus filas NO entraron al
    universo)."""

    created: int
    unchanged: int
    pending: int
    removed: int = 0
    imports_unreadable: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class CandidatePage:
    """Retorno de ``list_candidates``. ``items`` son dicts con la forma de
    ``IdentityCandidateRead``: ``id, kind, score, signals, left, right, state,
    linked_athlete_involved, decided_at, reversed_at``; ``left``/``right`` con
    la forma de ``IdentityRecordRead`` (ver ``record_view``)."""

    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class DecisionOutcome:
    """Retorno de ``decide``. ``merged`` es True si la decisión ``same_person``
    unió en el acto dos competidores ya confirmados."""

    candidate_id: int
    state: str
    merged: bool
    results_moved: int


@dataclass(frozen=True)
class ReversalOutcome:
    """Retorno de ``reverse``. ``split`` es True si se separó un competidor
    confirmado; ``links_cleared`` cuenta resultados que perdieron su
    ``athlete_id`` al moverse al competidor separado."""

    candidate_id: int
    state: str
    split: bool
    results_moved: int
    links_cleared: int


# ---------------------------------------------------------------------------
# Núcleo puro
# ---------------------------------------------------------------------------


#: Separador de las partes de una clave de registro (terna + discriminador).
#: Es un carácter de control: ningún valor normalizado lo contiene.
_KEY_SEP = "\x1f"


def record_key(triple: Triple, discriminator: str = "") -> str:
    """Clave estable de un registro: la terna, más el discriminador si el
    registro fue separado por categoría."""
    parts = [*triple, discriminator] if discriminator else list(triple)
    return _KEY_SEP.join(parts)


def base_key(key: str) -> str:
    """La terna de una clave de registro, sin el discriminador de categoría.

    Una misma terna puede aparecer en la cola con discriminador o sin él según
    cómo se vea el universo al recalcular (``split_by_category``); lo que
    identifica a las filas de una carga es la terna.
    """
    return _KEY_SEP.join(key.split(_KEY_SEP, 3)[:3])


def row_triple(row: Any) -> Optional[Triple]:
    """Terna ``(nombre, club, ciudad)`` normalizada de una fila del acta, o
    ``None`` si el nombre normaliza a vacío (la fila no entra a la cola)."""
    triple = signature_triple(row.name, row.club, row.city)
    return triple if triple[0] else None


def import_record_keys(
    rows_by_category: Mapping[str, Sequence[Any]],
    general_by_category: Optional[Mapping[str, Sequence[Any]]] = None,
) -> set[str]:
    """Claves de registro (sin discriminador) de las filas de una carga:
    RESULTADOS y, si se pasa, GENERAL (el ingestor también resuelve
    competidores desde sus filas).

    Es la misma clave que ``load_universe`` le asigna a esas filas, así que un
    candidato calculado antes del commit sigue reconociéndose después
    (``pending_candidates_for_import``).
    """
    keys: set[str] = set()
    for group in (rows_by_category, general_by_category or {}):
        for rows in group.values():
            for row in rows:
                triple = row_triple(row)
                if triple is not None:
                    keys.add(record_key(triple))
    return keys


def appearance_discriminator(ap: Appearance) -> str:
    return band_discriminator(ap.cat_sex, ap.age_min, ap.age_max, ap.season)


def split_by_category(appearances: Iterable[Appearance]) -> list[tuple[str, list[Appearance]]]:
    """Agrupa las apariciones de una misma terna en personas compatibles.

    Voraz y determinista: en orden de temporada, cada aparición se suma al
    primer grupo cuyo discriminador (el de su primera aparición) es
    compatible con su categoría y que no tiene ya otra categoría en la misma
    válida; si no hay, abre un grupo nuevo. Un solo grupo = una persona.
    """
    groups: list[tuple[str, list[Appearance]]] = []
    ordered = sorted(
        appearances, key=lambda a: (a.season, a.event_key, a.category_code, a.result_id or 0)
    )
    for ap in ordered:
        for disc, members in groups:
            if any(
                m.event_key == ap.event_key and m.category_code != ap.category_code
                for m in members
            ):
                continue
            if discriminator_compatible(disc, ap.cat_sex, ap.age_min, ap.age_max, ap.season):
                members.append(ap)
                break
        else:
            groups.append((appearance_discriminator(ap), [ap]))
    return groups


def pair_hash(key_a: str, key_b: str) -> str:
    """SHA-256 de las dos claves de registro ordenadas."""
    low, high = sorted((key_a, key_b))
    return hashlib.sha256(f"{low}\x1e{high}".encode("utf-8")).hexdigest()


def _surname_tokens(normalized: str) -> set[str]:
    tokens = normalized.split()
    return {t for t in tokens[1:] if len(t) >= _BLOCKING_TOKEN_MIN_LEN}


def _sex_conflict(a: IdentityRecord, b: IdentityRecord) -> bool:
    return a.sex is not None and b.sex is not None and a.sex != b.sex


def _age_path_backwards(appearances: Iterable[Appearance]) -> bool:
    """True si una temporada posterior está entera por debajo, en edad, de una
    anterior (la edad solo sube). Categorías sin rango acotado no cuentan."""
    by_season: dict[int, list[int]] = defaultdict(list)
    for a in appearances:
        if a.age_rank is not None:
            by_season[a.season].append(a.age_rank)
    seasons = sorted(by_season)
    for i, earlier in enumerate(seasons):
        for later in seasons[i + 1:]:
            if max(by_season[later]) < min(by_season[earlier]):
                return True
    return False


def _shared_valida(a: IdentityRecord, b: IdentityRecord) -> tuple[bool, bool]:
    """``(misma válida en dos categorías, misma válida y misma categoría)``."""
    cats_a: dict[tuple[int, int], set[str]] = defaultdict(set)
    for ap in a.appearances:
        cats_a[ap.event_key].add(ap.category_code)
    two_categories = same_category = False
    for ap in b.appearances:
        codes = cats_a.get(ap.event_key)
        if not codes:
            continue
        if ap.category_code in codes:
            same_category = True
        if codes - {ap.category_code}:
            two_categories = True
    return two_categories, same_category


def _club_and_city_differ(a: IdentityRecord, b: IdentityRecord) -> bool:
    if not (a.club_norm and b.club_norm and a.city_norm and b.city_norm):
        return False
    return (
        fuzz.token_set_ratio(a.club_norm, b.club_norm) < DIVERGENCE_MAX_SCORE
        and fuzz.token_set_ratio(a.city_norm, b.city_norm) < DIVERGENCE_MAX_SCORE
    )


def _name_variant_signal(a: str, b: str) -> str:
    ta, tb = a.split(), b.split()
    if sorted(ta) == sorted(tb):
        return SIGNAL_INVERTED_SURNAMES
    sa, sb = set(ta), set(tb)
    if sa < sb or sb < sa:
        return SIGNAL_EXTRA_SURNAME
    return SIGNAL_SPELLING_VARIANT


def _draft(
    kind: IdentityCandidateKind,
    a: IdentityRecord,
    b: IdentityRecord,
    score: int,
    signals: list[str],
) -> CandidateDraft:
    left, right = sorted((a, b), key=lambda r: r.key)
    return CandidateDraft(
        kind=kind,
        pair_hash=pair_hash(a.key, b.key),
        left=left.snapshot(),
        right=right.snapshot(),
        score=score,
        signals=signals,
        linked_athlete_involved=a.athlete_linked or b.athlete_linked,
    )


def in_club_scope(a: IdentityRecord, b: IdentityRecord) -> bool:
    """¿El par involucra a un atleta del club? (decisión 2026-09-22)."""
    return a.athlete_linked or b.athlete_linked


def build_candidates(records: Sequence[IdentityRecord]) -> list[CandidateDraft]:
    """Núcleo puro y síncrono (apto para ``asyncio.to_thread``).

    Alcance: solo se levanta un candidato (de cualquier tipo) si al menos un
    lado es un competidor vinculado a un atleta del club (``in_club_scope``);
    un par entre terceros no levanta nada.

    Reglas (contrato §Candidate rules, research R-06):

    - ``same_person_suspect``: ``normalized_name`` distinto,
      ``token_set_ratio >= SAME_PERSON_MIN_SCORE``, sexo compatible, ruta de
      edad que no retrocede y ninguna válida compartida. Solo se comparan
      registros que comparten un token de apellido (≥ 3 letras, sin contar el
      primer token).
    - ``homonym_suspect``: ``normalized_name`` idéntico y al menos una señal:
      ``same_valida_two_categories`` / ``same_valida_same_category``,
      ``sex_conflict``, ``age_path_backwards``, ``club_and_city_differ``, o
      ``multiple_existing_competitors`` (un registro sin competidor cuyo
      nombre coincide con varios competidores: el resolver no tendría
      desempate). Un cambio de club solo no es señal.
    - Dos registros del mismo competidor nunca forman par, salvo dos
      sub-registros de **la misma terna** separados por categoría (padre e
      hijo impresos igual): ese par siempre es ``homonym_suspect``, con
      ``age_incompatible_categories`` si ninguna otra señal lo explica.
      Dos registros de competidores distintos solo forman par
      ``same_person_suspect`` (la pregunta de si fusionarlos).

    Devuelve los borradores ordenados por ``score`` desc y ``pair_hash``.
    """
    drafts: dict[str, CandidateDraft] = {}

    # --- homónimos ------------------------------------------------------
    by_name: dict[str, list[IdentityRecord]] = defaultdict(list)
    for r in records:
        by_name[r.normalized_name].append(r)
    for group in by_name.values():
        if len(group) < 2:
            continue
        existing_ids = {r.competitor_id for r in group if r.competitor_id is not None}
        for a, b in combinations(group, 2):
            if not in_club_scope(a, b):
                continue
            same_triple = a.triple == b.triple
            if a.competitor_id is not None and b.competitor_id is not None:
                # Dos competidores distintos ya están separados; el mismo
                # competidor solo forma par si mezcla dos personas de la
                # misma terna (sub-registros por categoría).
                if a.competitor_id != b.competitor_id or not same_triple:
                    continue
            signals: list[str] = []
            two_cats, same_cat = _shared_valida(a, b)
            if two_cats:
                signals.append(SIGNAL_SAME_VALIDA_TWO_CATEGORIES)
            if same_cat:
                signals.append(SIGNAL_SAME_VALIDA_SAME_CATEGORY)
            if _sex_conflict(a, b):
                signals.append(SIGNAL_SEX_CONFLICT)
            if _age_path_backwards(a.appearances + b.appearances):
                signals.append(SIGNAL_AGE_PATH_BACKWARDS)
            if _club_and_city_differ(a, b):
                signals.append(SIGNAL_CLUB_AND_CITY_DIFFER)
            if len(existing_ids) > 1 and not same_triple:
                signals.append(SIGNAL_MULTIPLE_EXISTING_COMPETITORS)
            if same_triple and not signals:
                signals.append(SIGNAL_AGE_INCOMPATIBLE)
            if signals:
                d = _draft(IdentityCandidateKind.homonym_suspect, a, b, 100, signals)
                drafts[d.pair_hash] = d

    # --- misma persona, bloqueado por apellido ---------------------------
    buckets: dict[str, list[int]] = defaultdict(list)
    for idx, r in enumerate(records):
        for token in _surname_tokens(r.normalized_name):
            buckets[token].append(idx)
    seen: set[tuple[int, int]] = set()
    for members in buckets.values():
        for i, j in combinations(members, 2):
            pair = (i, j) if i < j else (j, i)
            if pair in seen:
                continue
            seen.add(pair)
            a, b = records[pair[0]], records[pair[1]]
            if not in_club_scope(a, b):
                continue
            if a.normalized_name == b.normalized_name:
                continue
            if a.competitor_id is not None and a.competitor_id == b.competitor_id:
                continue
            score = int(round(fuzz.token_set_ratio(a.normalized_name, b.normalized_name)))
            if score < SAME_PERSON_MIN_SCORE:
                continue
            if _sex_conflict(a, b):
                continue
            if any(_shared_valida(a, b)):
                continue
            if _age_path_backwards(a.appearances + b.appearances):
                continue
            signal = _name_variant_signal(a.normalized_name, b.normalized_name)
            d = _draft(IdentityCandidateKind.same_person_suspect, a, b, score, [signal])
            drafts[d.pair_hash] = d

    return sorted(drafts.values(), key=lambda d: (-d.score, d.pair_hash))


# ---------------------------------------------------------------------------
# Cáscara de base de datos — universo
# ---------------------------------------------------------------------------


def _age_rank(category: Optional[RaceCategory]) -> Optional[int]:
    """Rango de edad comparable: ``age_min`` de categorías acotadas; 0 para
    las que solo tienen tope (teteros); ``None`` para las abiertas (élite,
    master D/F, promocional), donde un adulto elige libremente."""
    if category is None or category.age_max is None:
        return None
    return category.age_min if category.age_min is not None else 0


def _display(raw: Optional[str], normalized: str, normalizer: Callable[[str], str]) -> str:
    """Texto impreso si corresponde a la forma normalizada; si no, la forma
    normalizada capitalizada (una firma vieja del mismo competidor)."""
    if raw and normalizer(raw) == normalized:
        return raw
    return normalized.title()


@dataclass
class _Printed:
    """Forma impresa de una terna (para mostrar al coach)."""

    name: str
    club: str
    city: str


def _apps_sex(apps: Iterable[Appearance], fallback: Optional[str]) -> Optional[str]:
    sexes = {a.cat_sex for a in apps if a.cat_sex in ("M", "F")}
    return sexes.pop() if len(sexes) == 1 else fallback


async def load_universe(db: AsyncSession, rows_loader: RowsLoader) -> Universe:
    """Carga el universo de registros: competidores existentes (una entrada
    por firma) + filas de los imports en staging (``pending``/``dry_run``,
    ``kind != general``, cuyo sha no esté ya confirmado) + las categorías aún
    pendientes de un import confirmado a medias (``pending_categories``).

    ``rows_loader(import)`` devuelve ``{code: [ResultsRow, ...]}`` con las
    correcciones ya aplicadas (el router pasa su propio recargador del
    archivo almacenado), o un ``ImportRows`` si además trae GENERAL. Un
    import cuyo archivo falla se reporta en ``imports_unreadable`` y no
    aporta filas.

    GENERAL (feature 045, R-08): una terna que solo aparece en GENERAL y no
    corresponde a ningún competidor ni a otras filas en staging es un
    competidor que el commit CREARÍA sin que nadie lo revisara; entra al
    universo con una sola aparición (categoría de GENERAL, válida
    ``GENERAL_VALIDA_NUM``) para poder levantar candidatos contra los
    atletas del club. Las ternas que ya están por RESULTADOS o por firma no
    reciben una aparición extra: ya están representadas y una categoría
    distinta las partiría en dos personas.

    Separación por categoría (decisión 2026-09-21): las apariciones de una
    misma terna se agrupan con ``split_by_category``; si forman más de un
    grupo, cada grupo es un registro con su discriminador. Para un
    competidor con varias firmas no se parten sus resultados confirmados
    (no se sabe bajo qué terna entró cada uno): solo se separan sus filas en
    staging.
    """
    categories = {c.id: c for c in (await db.execute(select(RaceCategory))).scalars().all()}
    by_code = {c.code: c for c in categories.values()}
    competitors = {c.id: c for c in (await db.execute(select(RaceCompetitor))).scalars().all()}
    signatures = (await db.execute(select(RaceCompetitorSignature))).scalars().all()

    def appearance(
        category: Optional[RaceCategory], code: str, event_key, season: int, result_id=None
    ) -> Appearance:
        return Appearance(
            event_key,
            season,
            code,
            _age_rank(category),
            cat_sex=getattr(getattr(category, "sex", None), "value", None),
            age_min=category.age_min if category is not None else None,
            age_max=category.age_max if category is not None else None,
            result_id=result_id,
        )

    # Apariciones confirmadas, a nivel competidor.
    comp_apps: dict[int, list[Appearance]] = defaultdict(list)
    comp_labels: dict[int, set[str]] = defaultdict(set)
    rows = await db.execute(
        select(
            RaceResult.id,
            RaceResult.competitor_id,
            RaceResult.category_id,
            RaceResult.category_label_raw,
            RaceEvent.series_id,
            RaceEvent.sequence_number,
            RaceSeries.season_year,
        )
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
        .where(RaceResult.deleted_at.is_(None))
    )
    for result_id, competitor_id, category_id, label_raw, series_id, seq, season in rows.all():
        category = categories.get(category_id)
        code = category.code if category is not None else ""
        comp_apps[competitor_id].append(
            appearance(category, code, (series_id, seq), season, result_id)
        )
        label = label_raw or (category.label if category is not None else "")
        if label:
            comp_labels[competitor_id].add(label)

    sigs_by_triple: dict[Triple, list[RaceCompetitorSignature]] = defaultdict(list)
    sig_count: dict[int, int] = defaultdict(int)
    for sig in signatures:
        if sig.competitor_id in competitors:
            sigs_by_triple[(sig.normalized_name, sig.club_norm, sig.city_norm)].append(sig)
            sig_count[sig.competitor_id] += 1

    # Filas en staging, por terna.
    staged: dict[Triple, list[Appearance]] = defaultdict(list)
    printed: dict[Triple, _Printed] = {}
    # Ternas que solo trae GENERAL: se fusionan a `staged` tras leer todos los
    # imports, para no depender del orden en que aparezcan.
    general_staged: dict[Triple, tuple[Appearance, _Printed]] = {}
    committed_shas = set(
        (
            await db.execute(
                select(RaceImport.sha256).where(
                    RaceImport.status == RaceImportStatus.committed
                )
            )
        ).scalars().all()
    )
    staged_imports = (
        await db.execute(
            select(RaceImport)
            .where(
                RaceImport.status.in_(_STAGED_STATUSES)
                | (RaceImport.status == RaceImportStatus.committed)
            )
            .order_by(RaceImport.id)
        )
    ).scalars().all()
    # Suelta la conexión MySQL ANTES de descargar y reparsear los archivos:
    # con 15 válidas históricas el bucle tarda minutos y Hostinger cierra la
    # conexión ociosa, lo que en producción tumbó el rebuild con un
    # RuntimeError de driver. `expire_on_commit=False`, así que los objetos ya
    # cargados siguen siendo utilizables; la próxima consulta toma una conexión
    # nueva del pool (con `pool_pre_ping`).
    await db.commit()

    unreadable: list[int] = []
    scanned = 0
    for imp in staged_imports:
        if imp.kind == RaceImportKind.general:
            continue
        # Un import confirmado a medias (feature 044, US5) sigue en el
        # universo mientras le queden ``pending_categories``: esas filas aún
        # no son resultados y ``/commit-pending`` las ingestará después. El
        # ``rows_loader`` devuelve solo esas categorías, así que lo ya
        # confirmado nunca se cuenta dos veces.
        if imp.status == RaceImportStatus.committed:
            if not (imp.parse_meta_json or {}).get("pending_categories"):
                continue
        elif imp.sha256 in committed_shas:
            continue
        header = (imp.parse_meta_json or {}).get("header") or {}
        try:
            season = int(header["season"])
            valida_num = int(header["valida_num"])
        except (KeyError, TypeError, ValueError):
            unreadable.append(imp.id)
            continue
        try:
            loaded = await rows_loader(imp)
        except Exception as exc:  # noqa: BLE001 — cualquier fallo de storage/parseo
            logger.warning(
                "race_identity_universe_import_unreadable import_id=%s err=%s",
                imp.id,
                type(exc).__name__,
            )
            unreadable.append(imp.id)
            continue
        scanned += 1
        by_category, general_rows = (
            (loaded.results, loaded.general) if isinstance(loaded, ImportRows) else (loaded, {})
        )
        event_key = (imp.series_id, valida_num)
        for code, parsed_rows in by_category.items():
            ap = appearance(by_code.get(code), code, event_key, season)
            for row in parsed_rows:
                triple = row_triple(row)
                if triple is None:
                    continue
                staged[triple].append(ap)
                printed.setdefault(
                    triple,
                    _Printed(
                        row.name.strip(),
                        (row.club or "").strip() if triple[1] else "",
                        (row.city or "").strip() if triple[2] else "",
                    ),
                )
        general_event_key = (imp.series_id, GENERAL_VALIDA_NUM)
        for code in sorted(general_rows):
            ap = appearance(by_code.get(code), code, general_event_key, season)
            for row in general_rows[code]:
                triple = row_triple(row)
                if triple is None or triple in general_staged:
                    continue
                general_staged[triple] = (
                    ap,
                    _Printed(
                        row.name.strip(),
                        (row.club or "").strip() if triple[1] else "",
                        (row.city or "").strip() if triple[2] else "",
                    ),
                )

    for triple, (ap, shown) in general_staged.items():
        if triple in staged or triple in sigs_by_triple:
            continue
        staged[triple].append(ap)
        printed.setdefault(triple, shown)

    def labels_of(apps: Iterable[Appearance]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    by_code[a.category_code].label if a.category_code in by_code else a.category_code
                    for a in apps
                    if a.category_code
                }
            )
        )

    records: list[IdentityRecord] = []

    def emit(
        triple: Triple,
        shown: _Printed,
        apps: list[Appearance],
        *,
        competitor: Optional[RaceCompetitor],
        discriminator: str = "",
        labels: Optional[tuple[str, ...]] = None,
        extra_seasons: tuple[int, ...] = (),
    ) -> None:
        comp_sex = competitor.sex.value if competitor is not None and competitor.sex else None
        records.append(
            IdentityRecord(
                key=record_key(triple, discriminator),
                name_printed=shown.name,
                normalized_name=triple[0],
                club=shown.club,
                club_norm=triple[1],
                city=shown.city,
                city_norm=triple[2],
                sex=_apps_sex(apps, comp_sex) if discriminator else (comp_sex or _apps_sex(apps, None)),
                competitor_id=competitor.id if competitor is not None else None,
                athlete_linked=competitor is not None and competitor.athlete_id is not None,
                appearances=tuple(apps),
                category_labels=labels if labels is not None else labels_of(apps),
                extra_seasons=extra_seasons,
                discriminator=discriminator,
            )
        )

    def shown_for(triple: Triple, comp: RaceCompetitor) -> _Printed:
        return _Printed(
            _display(comp.display_name, triple[0], normalize_name),
            _display(comp.club_text, triple[1], normalize_club) if triple[1] else "",
            _display(comp.city_text, triple[2], normalize_club) if triple[2] else "",
        )

    def emit_split(triple: Triple, shown: _Printed, apps: list[Appearance], comp) -> bool:
        """Emite un registro por grupo si hay más de uno; True si partió."""
        groups = split_by_category(apps)
        if len(groups) < 2:
            return False
        for disc, members in groups:
            owner = comp if comp is not None and any(m.result_id for m in members) else None
            emit(triple, shown, members, competitor=owner, discriminator=disc)
        return True

    for triple in sorted(set(sigs_by_triple) | set(staged)):
        sigs = sigs_by_triple.get(triple, [])
        rows_here = staged.get(triple, [])
        separated = [s for s in sigs if s.discriminator]
        blank = next((s for s in sigs if not s.discriminator), None)

        # 1. Firmas ya separadas por categoría: un registro cada una; las
        #    filas en staging van a la única firma compatible.
        leftovers: list[Appearance] = []
        assigned: dict[int, list[Appearance]] = defaultdict(list)
        for ap in rows_here:
            fits = [
                s for s in separated
                if discriminator_compatible(s.discriminator, ap.cat_sex, ap.age_min, ap.age_max, ap.season)
            ]
            if len(fits) == 1:
                assigned[fits[0].id].append(ap)
            else:
                leftovers.append(ap)
        for sig in separated:
            comp = competitors[sig.competitor_id]
            emit(
                triple,
                shown_for(triple, comp),
                comp_apps.get(comp.id, []) + assigned.get(sig.id, []),
                competitor=comp,
                discriminator=sig.discriminator,
                extra_seasons=(sig.first_season, sig.last_season),
            )

        # 2. Firma normal ('').
        if blank is not None:
            comp = competitors[blank.competitor_id]
            shown = shown_for(triple, comp)
            if sig_count[comp.id] == 1:
                apps = comp_apps.get(comp.id, []) + leftovers
                if not emit_split(triple, shown, apps, comp):
                    emit(
                        triple, shown, apps, competitor=comp,
                        labels=tuple(sorted(comp_labels.get(comp.id, set()) | set(labels_of(leftovers)))),
                        extra_seasons=(blank.first_season, blank.last_season),
                    )
            else:
                own = comp_apps.get(comp.id, [])
                groups = split_by_category(leftovers) if leftovers else []
                if len(groups) > 1:
                    emit(triple, shown, own, competitor=comp,
                         labels=tuple(sorted(comp_labels.get(comp.id, set()))),
                         extra_seasons=(blank.first_season, blank.last_season))
                    for disc, members in groups:
                        emit(triple, printed.get(triple, shown), members, competitor=None, discriminator=disc)
                else:
                    emit(triple, shown, own + leftovers, competitor=comp,
                         labels=tuple(sorted(comp_labels.get(comp.id, set()) | set(labels_of(leftovers)))),
                         extra_seasons=(blank.first_season, blank.last_season))
            continue

        # 3. Sin firma normal: filas en staging que no encajaron.
        if not leftovers:
            continue
        shown = printed[triple]
        if separated:
            for disc, members in split_by_category(leftovers):
                emit(triple, shown, members, competitor=None, discriminator=disc)
        elif not emit_split(triple, shown, leftovers, None):
            emit(triple, shown, leftovers, competitor=None)

    # Competidor sin firmas (defensivo: el backfill crea una por competidor).
    with_sigs = set(sig_count)
    seen_keys = {r.key for r in records}
    for comp in competitors.values():
        if comp.id in with_sigs:
            continue
        triple = signature_triple(comp.display_name, comp.club_text, comp.city_text)
        if record_key(triple) in seen_keys:
            continue
        emit(
            triple,
            _Printed(comp.display_name, comp.club_text or "", comp.city_text or ""),
            comp_apps.get(comp.id, []),
            competitor=comp,
            labels=tuple(sorted(comp_labels.get(comp.id, set()))),
        )

    records.sort(key=lambda r: r.key)
    return Universe(records=records, imports_scanned=scanned, imports_unreadable=unreadable)


# ---------------------------------------------------------------------------
# Cáscara de base de datos — persistencia de candidatos
# ---------------------------------------------------------------------------


async def persist_candidates(
    db: AsyncSession, drafts: Sequence[CandidateDraft]
) -> tuple[int, int]:
    """Inserta los borradores nuevos; devuelve ``(created, unchanged)``.

    Un ``pair_hash`` ya existente nunca se reinicia: si está decidido no se
    toca; si sigue ``pending`` se refrescan snapshot, score y señales (un
    competidor pudo haberse vinculado desde el último rebuild). Solo hace
    ``flush``; el commit es del llamador.
    """
    existing = {
        c.pair_hash: c
        for c in (await db.execute(select(RaceIdentityCandidate))).scalars().all()
    }
    created = unchanged = 0
    for d in drafts:
        current = existing.get(d.pair_hash)
        if current is None:
            db.add(
                RaceIdentityCandidate(
                    kind=d.kind,
                    pair_hash=d.pair_hash,
                    left_record=d.left,
                    right_record=d.right,
                    score=d.score,
                    signals=d.signals,
                    state=IdentityCandidateState.pending,
                    linked_athlete_involved=d.linked_athlete_involved,
                )
            )
            existing[d.pair_hash] = None  # type: ignore[assignment]
            created += 1
            continue
        unchanged += 1
        if current is not None and current.state == IdentityCandidateState.pending:
            current.left_record = d.left
            current.right_record = d.right
            current.score = d.score
            current.signals = d.signals
            current.linked_athlete_involved = d.linked_athlete_involved
    await db.flush()
    return created, unchanged


async def rebuild(
    db: AsyncSession,
    *,
    rows_loader: RowsLoader,
    timeout_s: Optional[float] = None,
) -> RebuildResult:
    """Recalcula la cola sobre todo el universo. Idempotente.

    El cálculo (``build_candidates``) corre en un hilo de trabajo con
    ``asyncio.to_thread``; ``timeout_s`` lo acota con ``asyncio.wait_for``
    (``TimeoutError`` al llamador; nada se persiste en ese caso). Solo hace
    ``flush``. Presupuesto del contrato: ≤ 10 s, timeout 30 s en el router.
    """
    universe = await load_universe(db, rows_loader)
    work = asyncio.to_thread(build_candidates, universe.records)
    drafts = await (asyncio.wait_for(work, timeout_s) if timeout_s else work)
    created, unchanged = await persist_candidates(db, drafts)
    removed = await remove_out_of_scope(db, universe.records, drafts)
    pending = await _count_state(db, IdentityCandidateState.pending)
    logger.info(
        "race_identity_rebuild records=%d imports=%d unreadable=%d created=%d "
        "unchanged=%d removed=%d pending=%d",
        len(universe.records),
        universe.imports_scanned,
        len(universe.imports_unreadable),
        created,
        unchanged,
        removed,
        pending,
    )
    return RebuildResult(
        created=created,
        unchanged=unchanged,
        pending=pending,
        removed=removed,
        imports_unreadable=list(universe.imports_unreadable),
    )


async def remove_out_of_scope(
    db: AsyncSession,
    records: Sequence[IdentityRecord],
    drafts: Sequence[CandidateDraft],
) -> int:
    """Borra los candidatos ``pending`` que ya no involucran a un atleta del
    club (decisión 2026-09-22); devuelve cuántos. Un candidato decidido
    nunca se toca — tampoco uno revertido a ``pending``, que ya tiene
    historia (``decided_at``) —, ni uno que este rebuild volvió a producir. Un lado cuenta
    como del club si su competidor está vinculado hoy o si su registro del
    universo actual lo está (el snapshot puede ser viejo). Solo ``flush``."""
    keep = {d.pair_hash for d in drafts}
    linked_keys = {r.key for r in records if r.athlete_linked}
    linked_ids = set(
        (
            await db.execute(
                select(RaceCompetitor.id).where(RaceCompetitor.athlete_id.is_not(None))
            )
        ).scalars().all()
    )

    def side_linked(record: Mapping[str, Any]) -> bool:
        return record.get("key") in linked_keys or record.get("competitor_id") in linked_ids

    stale = [
        c.id
        for c in (
            await db.execute(
                select(RaceIdentityCandidate).where(
                    RaceIdentityCandidate.state == IdentityCandidateState.pending
                )
            )
        ).scalars().all()
        if c.pair_hash not in keep
        and c.decided_at is None
        and not side_linked(c.left_record or {})
        and not side_linked(c.right_record or {})
    ]
    if stale:
        await db.execute(
            delete(RaceIdentityCandidate).where(RaceIdentityCandidate.id.in_(stale))
        )
        await db.flush()
    return len(stale)


# ---------------------------------------------------------------------------
# Lecturas para el router
# ---------------------------------------------------------------------------


async def _count_state(db: AsyncSession, state: IdentityCandidateState) -> int:
    result = await db.execute(
        select(func.count(RaceIdentityCandidate.id)).where(
            RaceIdentityCandidate.state == state
        )
    )
    return int(result.scalar_one())


async def summary(db: AsyncSession) -> dict[str, int]:
    """``{"pending": n, "same_person": n, "different_people": n}`` — alimenta
    el banner del candado de commit."""
    rows = await db.execute(
        select(RaceIdentityCandidate.state, func.count(RaceIdentityCandidate.id)).group_by(
            RaceIdentityCandidate.state
        )
    )
    counts = {s.value: 0 for s in IdentityCandidateState}
    for state, n in rows.all():
        counts[IdentityCandidateState(state).value] = int(n)
    return counts


async def pending_candidates_for_import(
    db: AsyncSession, import_record_keys: Collection[str]
) -> list[RaceIdentityCandidate]:
    """Candidatos ``pending`` que frenan el commit de UNA carga (feature 045,
    research R-08): aquellos cuyo ``left_record.key`` o ``right_record.key`` es
    la terna de alguna fila de la carga (``import_record_keys``).

    El ``OR`` cubre los dos casos que importan: un candidato que cruza esta
    carga con otra (basta que un lado sea de esta) y uno sobre un competidor
    nuevo de la carga (tiene clave aunque aún no tenga ``competitor_id``).
    Un candidato que habla solo de otras cargas no la frena. Se compara la
    terna (``base_key``), no la clave completa: el discriminador de categoría
    de un lado puede cambiar entre recálculos y no debe abrir un hueco.

    Se filtra en Python, como ``remove_out_of_scope``: la cola del club es de
    decenas o cientos de filas y el snapshot es JSON, sin operador portable
    entre SQLite (tests) y MySQL. Solo lee; ordenado por ``id``.
    """
    wanted = {base_key(k) for k in import_record_keys}
    if not wanted:
        return []
    pending = (
        await db.execute(
            select(RaceIdentityCandidate)
            .where(RaceIdentityCandidate.state == IdentityCandidateState.pending)
            .order_by(RaceIdentityCandidate.id)
        )
    ).scalars().all()

    def side_in_import(record: Optional[Mapping[str, Any]]) -> bool:
        key = (record or {}).get("key")
        return isinstance(key, str) and base_key(key) in wanted

    return [
        c for c in pending if side_in_import(c.left_record) or side_in_import(c.right_record)
    ]


def record_view(record: Mapping[str, Any]) -> dict[str, Any]:
    """Forma pública de un snapshot (``IdentityRecordRead``): ``name_printed,
    club, city, seasons[], category_labels[], competitor_id, athlete_linked``.
    Omite las claves internas (terna normalizada, resultados adjuntos)."""
    view = {k: record.get(k) for k in _PUBLIC_RECORD_FIELDS}
    view["seasons"] = list(view["seasons"] or [])
    view["category_labels"] = list(view["category_labels"] or [])
    view["athlete_linked"] = bool(view["athlete_linked"])
    view["club"] = view["club"] or ""
    view["city"] = view["city"] or ""
    return view


def candidate_view(cand: RaceIdentityCandidate) -> dict[str, Any]:
    """Forma pública de un candidato (``IdentityCandidateRead``)."""
    return {
        "id": cand.id,
        "kind": IdentityCandidateKind(cand.kind).value,
        "score": cand.score,
        "signals": list(cand.signals or []),
        "left": record_view(cand.left_record or {}),
        "right": record_view(cand.right_record or {}),
        "state": IdentityCandidateState(cand.state).value,
        "linked_athlete_involved": bool(cand.linked_athlete_involved),
        "decided_at": cand.decided_at,
        "reversed_at": cand.reversed_at,
    }


async def list_candidates(
    db: AsyncSession,
    *,
    state: Optional[str] = None,
    kind: Optional[str] = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> CandidatePage:
    """Cola paginada, ``score DESC`` y luego ``id``. ``state``/``kind`` son
    los valores de los enums (``ValueError`` si no existen)."""
    page = max(1, page)
    filters = []
    if state:
        filters.append(RaceIdentityCandidate.state == IdentityCandidateState(state))
    if kind:
        filters.append(RaceIdentityCandidate.kind == IdentityCandidateKind(kind))
    total = int(
        (
            await db.execute(select(func.count(RaceIdentityCandidate.id)).where(*filters))
        ).scalar_one()
    )
    rows = (
        await db.execute(
            select(RaceIdentityCandidate)
            .where(*filters)
            .order_by(RaceIdentityCandidate.score.desc(), RaceIdentityCandidate.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return CandidatePage(
        items=[candidate_view(c) for c in rows], total=total, page=page, page_size=page_size
    )


# ---------------------------------------------------------------------------
# Decisiones y reversión
# ---------------------------------------------------------------------------


async def _load_candidate(db: AsyncSession, candidate_id: int) -> RaceIdentityCandidate:
    result = await db.execute(
        select(RaceIdentityCandidate)
        .where(RaceIdentityCandidate.id == candidate_id)
        .with_for_update()
    )
    cand = result.scalars().first()
    if cand is None:
        raise CandidateNotFound(f"candidato {candidate_id} no existe")
    return cand


async def _side_competitor(
    db: AsyncSession, record: Mapping[str, Any]
) -> Optional[RaceCompetitor]:
    """Competidor actual de un lado: por su firma (terna + discriminador), o
    por el id del snapshot."""
    triple = record_triple(record)
    result = await db.execute(
        select(RaceCompetitor)
        .join(RaceCompetitorSignature, RaceCompetitorSignature.competitor_id == RaceCompetitor.id)
        .where(
            RaceCompetitorSignature.normalized_name == triple[0],
            RaceCompetitorSignature.club_norm == triple[1],
            RaceCompetitorSignature.city_norm == triple[2],
            RaceCompetitorSignature.discriminator == record_discriminator(record),
        )
    )
    competitor = result.scalars().first()
    if competitor is None and record.get("competitor_id") is not None:
        result = await db.execute(
            select(RaceCompetitor).where(RaceCompetitor.id == record["competitor_id"])
        )
        competitor = result.scalars().first()
    return competitor


def _audit_meta(
    cand: RaceIdentityCandidate,
    left: Optional[RaceCompetitor],
    right: Optional[RaceCompetitor],
    results_moved: int,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"pair_hash": cand.pair_hash, "results_count": results_moved}
    if left is not None:
        meta["left_competitor_id"] = left.id
    if right is not None:
        meta["right_competitor_id"] = right.id
    return meta


async def decide(
    db: AsyncSession,
    candidate_id: int,
    answer: str,
    *,
    actor: User,
) -> DecisionOutcome:
    """Registra la decisión del coach sobre un candidato ``pending``.

    ``answer`` ∈ ``{"same_person", "different_people"}``. Si ambos lados ya
    son competidores confirmados y distintos, ``same_person`` los fusiona en
    el acto (firmas y resultados al competidor más antiguo; el vacío se
    borra si no tiene historial de enlace). Si un lado aún está en staging,
    el efecto llega en la ingesta (``IdentityResolver``).

    Par de la **misma terna** separado por categoría + ``different_people``:
    la firma ``''`` del competidor existente pasa a llevar el discriminador
    de su lado y, si el competidor ya mezclaba resultados de ambos lados, los
    del otro lado se mueven a un competidor nuevo con su propia firma
    (``linked_competitor_ambiguous`` si el competidor está vinculado). Las
    filas que lleguen después se reparten por categoría en el resolver. Solo hace
    ``flush``. Errores: ``CandidateNotFound``, ``CandidateNotPending``,
    ``IdentityDecisionConflict``, ``ValueError`` (respuesta inválida).
    """
    target = IdentityCandidateState(answer)
    if target == IdentityCandidateState.pending:
        raise ValueError("respuesta inválida")
    cand = await _load_candidate(db, candidate_id)
    if cand.state != IdentityCandidateState.pending:
        raise CandidateNotPending(f"candidato {candidate_id} ya decidido")

    left = await _side_competitor(db, cand.left_record or {})
    right = await _side_competitor(db, cand.right_record or {})
    both = left is not None and right is not None

    intra = record_triple(cand.left_record or {}) == record_triple(cand.right_record or {})
    split_plan: Optional[_IntraSplitPlan] = None
    if target == IdentityCandidateState.different_people and intra:
        split_plan = await _plan_intra_split(db, cand)
    elif target == IdentityCandidateState.different_people and both and left.id == right.id:
        raise IdentityDecisionConflict("already_same_competitor")

    merge = target == IdentityCandidateState.same_person and both and left.id != right.id
    plan: Optional[_MergePlan] = None
    moved: list[RaceResult] = list(split_plan.moved) if split_plan is not None else []
    if merge:
        keep, drop = (left, right) if left.id < right.id else (right, left)
        plan = await _plan_merge(db, keep, drop)
        moved = plan.moved

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.race_identity_candidate,
        entity_id=cand.id,
        actor=actor,
        club_id=None,
        changed_fields=["state"],
        diff={"state": (IdentityCandidateState.pending.value, target.value)},
        meta=_audit_meta(cand, left, right, len(moved)),
    )

    now = datetime.now(timezone.utc)
    cand.state = target
    cand.decided_by_user_id = actor.id
    cand.decided_at = now

    if plan is not None:
        drop_side = "left_record" if plan.drop is left else "right_record"
        await _merge(db, cand, plan, drop_side, actor)
    else:
        if split_plan is not None:
            _apply_intra_split(db, split_plan)
        await db.flush()

    logger.info(
        "race_identity_decided candidate_id=%s state=%s merged=%s results_moved=%d",
        cand.id,
        target.value,
        merge,
        len(moved),
    )
    return DecisionOutcome(
        candidate_id=cand.id, state=target.value, merged=merge, results_moved=len(moved)
    )


@dataclass
class _IntraSplitPlan:
    blank: Optional[RaceCompetitorSignature]
    keep_discriminator: str
    other: dict[str, Any]
    triple: Triple
    moved: list[RaceResult]


async def _plan_intra_split(db: AsyncSession, cand: RaceIdentityCandidate) -> _IntraSplitPlan:
    """Lee y valida lo que ``different_people`` necesita para un par de la
    misma terna. Todas las lecturas antes de encolar la auditoría."""
    left, right = cand.left_record or {}, cand.right_record or {}
    triple = record_triple(left)
    blank = (
        await db.execute(
            select(RaceCompetitorSignature).where(
                RaceCompetitorSignature.normalized_name == triple[0],
                RaceCompetitorSignature.club_norm == triple[1],
                RaceCompetitorSignature.city_norm == triple[2],
                RaceCompetitorSignature.discriminator == "",
            )
        )
    ).scalars().first()
    if blank is None:
        # Ninguna firma normal: o ambos lados ya tienen la suya, o todo está
        # en staging — el resolver separa por categoría en la ingesta.
        return _IntraSplitPlan(None, "", {}, triple, [])

    sides = [left, right]
    with_results = [s for s in sides if s.get(_RESULT_IDS_KEY)]
    if with_results:
        keep = min(with_results, key=lambda s: min(s[_RESULT_IDS_KEY]))
    else:
        owned = [s for s in sides if s.get("competitor_id") == blank.competitor_id]
        keep = owned[0] if owned else None
    if keep is None:
        return _IntraSplitPlan(None, "", {}, triple, [])
    other = right if keep is left else left

    moved: list[RaceResult] = []
    if other.get(_RESULT_IDS_KEY):
        owner = (
            await db.execute(select(RaceCompetitor).where(RaceCompetitor.id == blank.competitor_id))
        ).scalars().one()
        if owner.athlete_id is not None:
            raise IdentityDecisionConflict("linked_competitor_ambiguous")
        moved = list(
            (
                await db.execute(
                    select(RaceResult).where(
                        RaceResult.id.in_(other[_RESULT_IDS_KEY]),
                        RaceResult.competitor_id == blank.competitor_id,
                    )
                )
            ).scalars().all()
        )
    return _IntraSplitPlan(
        blank, record_discriminator(keep), dict(other), triple, moved
    )


def _apply_intra_split(db: AsyncSession, plan: _IntraSplitPlan) -> None:
    """Etiqueta la firma normal con el discriminador de su lado y, si el
    competidor mezclaba a las dos personas, parte los resultados del otro."""
    if plan.blank is None:
        return
    plan.blank.discriminator = plan.keep_discriminator
    if not plan.moved:
        return
    other = plan.other
    new_comp = RaceCompetitor(
        normalized_name=plan.triple[0],
        display_name=(other.get("name_printed") or plan.triple[0].title())[:160],
        club_text=other.get("club") or None,
        city_text=other.get("city") or None,
        sex=CompetitorSex(other["sex"]) if other.get("sex") in ("M", "F") else None,
    )
    db.add(new_comp)
    seasons = list(other.get("seasons") or []) or [0]
    db.add(RaceCompetitorSignature(
        competitor=new_comp,
        normalized_name=plan.triple[0],
        club_norm=plan.triple[1],
        city_norm=plan.triple[2],
        discriminator=record_discriminator(other),
        first_season=min(seasons),
        last_season=max(seasons),
    ))
    for r in plan.moved:
        r.competitor = new_comp


@dataclass
class _MergePlan:
    keep: RaceCompetitor
    drop: RaceCompetitor
    moved: list[RaceResult]
    keep_results: list[RaceResult]
    signatures: list[RaceCompetitorSignature]
    has_link_history: bool


async def _plan_merge(
    db: AsyncSession, keep: RaceCompetitor, drop: RaceCompetitor
) -> _MergePlan:
    """Lee todo lo que la fusión necesita y la valida ANTES de mutar nada.

    Todas las lecturas ocurren antes de encolar la auditoría: una lectura
    posterior dispararía un autoflush y la mutación de ``race_results``
    quedaría en un flush sin su fila de auditoría (detector ``AUDIT_STRICT``).
    """
    if (
        keep.athlete_id is not None
        and drop.athlete_id is not None
        and keep.athlete_id != drop.athlete_id
    ):
        raise IdentityDecisionConflict("linked_to_different_athletes")
    keep_results = list(
        (
            await db.execute(select(RaceResult).where(RaceResult.competitor_id == keep.id))
        ).scalars().all()
    )
    moved = list(
        (
            await db.execute(select(RaceResult).where(RaceResult.competitor_id == drop.id))
        ).scalars().all()
    )
    keep_events = {r.event_id for r in keep_results}
    if any(r.event_id in keep_events for r in moved):
        raise IdentityDecisionConflict("shared_valida")
    signatures = list(
        (
            await db.execute(
                select(RaceCompetitorSignature).where(
                    RaceCompetitorSignature.competitor_id == drop.id
                )
            )
        ).scalars().all()
    )
    has_link_history = (
        await db.execute(
            select(RaceCompetitorLinkAudit.id)
            .where(RaceCompetitorLinkAudit.competitor_id == drop.id)
            .limit(1)
        )
    ).first() is not None
    return _MergePlan(keep, drop, moved, keep_results, signatures, has_link_history)


async def _merge(
    db: AsyncSession,
    cand: RaceIdentityCandidate,
    plan: _MergePlan,
    drop_side: str,
    actor: User,
) -> None:
    """Fusión post-commit: firmas y resultados de ``drop`` pasan a ``keep``.

    Un único flush junto con la fila de auditoría ya encolada. El competidor
    vacío se borra después, con su propia fila de auditoría, salvo que tenga
    historial de enlace (FK RESTRICT de ``race_competitor_link_audit``: la
    auditoría manda y el registro queda vacío).
    """
    keep, drop = plan.keep, plan.drop
    for sig in plan.signatures:
        sig.competitor_id = keep.id
        sig.source_candidate_id = cand.id

    if keep.athlete_id is None and drop.athlete_id is not None:
        keep.athlete_id = drop.athlete_id
        keep.linked_at = drop.linked_at or datetime.now(timezone.utc)
        keep.linked_by_user_id = drop.linked_by_user_id or actor.id
        for r in plan.keep_results:
            if r.deleted_at is None:
                r.athlete_id = keep.athlete_id
        db.add(
            RaceCompetitorLinkAudit(
                competitor_id=keep.id,
                action=LinkAuditAction.link,
                previous_athlete_id=None,
                new_athlete_id=keep.athlete_id,
                results_propagated=len(plan.keep_results) + len(plan.moved),
                user_id=actor.id,
                created_at=datetime.now(timezone.utc),
            )
        )
    for r in plan.moved:
        r.competitor_id = keep.id
        if r.deleted_at is None:
            r.athlete_id = keep.athlete_id

    record = dict(getattr(cand, drop_side) or {})
    record[_ATTACHED_KEY] = sorted(r.id for r in plan.moved)
    setattr(cand, drop_side, record)
    await db.flush()

    if not plan.has_link_history:
        await record_audit(
            db,
            action=AuditAction.delete,
            entity_type=AuditEntityType.race_competitor,
            entity_id=drop.id,
            actor=actor,
            club_id=None,
            meta={"related_entity_id": keep.id, "pair_hash": cand.pair_hash},
        )
        db.expunge(drop)
        await db.execute(delete(RaceCompetitor).where(RaceCompetitor.id == drop.id))
        await db.flush()


async def reverse(
    db: AsyncSession,
    candidate_id: int,
    *,
    actor: User,
) -> ReversalOutcome:
    """Devuelve un candidato decidido a ``pending`` y deshace su efecto
    (contrato §Reversal semantics).

    - ``same_person`` con efecto ya confirmado: las firmas con
      ``source_candidate_id = id`` pasan a un competidor nuevo junto con los
      resultados que entraron bajo ellas. Si el competidor original está
      vinculado, el nuevo queda sin vincular y esos resultados pierden su
      ``athlete_id`` (fila en ``race_competitor_link_audit``).
    - ``different_people``: los competidores siguen separados; solo vuelve a
      la cola.

    Solo hace ``flush``. Errores: ``CandidateNotFound``,
    ``CandidateNotDecided``.
    """
    cand = await _load_candidate(db, candidate_id)
    previous = IdentityCandidateState(cand.state)
    if previous == IdentityCandidateState.pending:
        raise CandidateNotDecided(f"candidato {candidate_id} está pendiente")

    signatures: list[RaceCompetitorSignature] = []
    attached: list[int] = []
    if previous == IdentityCandidateState.same_person:
        signatures = list(
            (
                await db.execute(
                    select(RaceCompetitorSignature).where(
                        RaceCompetitorSignature.source_candidate_id == cand.id
                    )
                )
            ).scalars().all()
        )
        for side in (cand.left_record or {}, cand.right_record or {}):
            attached.extend(side.get(_ATTACHED_KEY) or [])

    left = await _side_competitor(db, cand.left_record or {})
    right = await _side_competitor(db, cand.right_record or {})

    # Par de la misma terna: si la decisión solo etiquetó la única firma (no
    # llegó a partir a nadie), la etiqueta se quita para no dejar la terna
    # separada sin decisión que la respalde. Si ya hay dos firmas, siguen
    # separados hasta una decisión ``same_person`` (contrato).
    relabel: Optional[RaceCompetitorSignature] = None
    triple = record_triple(cand.left_record or {})
    if (
        previous == IdentityCandidateState.different_people
        and triple == record_triple(cand.right_record or {})
    ):
        triple_sigs = (
            await db.execute(
                select(RaceCompetitorSignature).where(
                    RaceCompetitorSignature.normalized_name == triple[0],
                    RaceCompetitorSignature.club_norm == triple[1],
                    RaceCompetitorSignature.city_norm == triple[2],
                )
            )
        ).scalars().all()
        if len(triple_sigs) == 1 and triple_sigs[0].discriminator:
            relabel = triple_sigs[0]

    split = bool(signatures or attached)
    original: Optional[RaceCompetitor] = None
    moved: list[RaceResult] = []
    if split:
        owner_id = signatures[0].competitor_id if signatures else None
        if owner_id is None:
            owner_id = (
                await db.execute(select(RaceResult.competitor_id).where(RaceResult.id == attached[0]))
            ).scalar_one_or_none()
        if owner_id is not None:
            original = (
                await db.execute(select(RaceCompetitor).where(RaceCompetitor.id == owner_id))
            ).scalars().first()
        if attached and owner_id is not None:
            moved = list(
                (
                    await db.execute(
                        select(RaceResult).where(
                            RaceResult.id.in_(attached),
                            RaceResult.competitor_id == owner_id,
                        )
                    )
                ).scalars().all()
            )

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.race_identity_candidate,
        entity_id=cand.id,
        actor=actor,
        club_id=None,
        changed_fields=["state"],
        diff={"state": (previous.value, IdentityCandidateState.pending.value)},
        meta=_audit_meta(cand, left, right, len(moved)),
    )

    links_cleared = 0
    if split and original is not None:
        moved_triples = {
            (s.normalized_name, s.club_norm, s.city_norm) for s in signatures
        }
        side = _moved_side(cand, moved_triples)
        new_comp = RaceCompetitor(
            normalized_name=side.get("normalized_name") or original.normalized_name,
            display_name=(side.get("name_printed") or original.display_name)[:160],
            club_text=(side.get("club") or None),
            city_text=(side.get("city") or None),
            sex=CompetitorSex(side["sex"]) if side.get("sex") else original.sex,
        )
        db.add(new_comp)
        for sig in signatures:
            sig.competitor = new_comp
            sig.source_candidate_id = None
        for r in moved:
            r.competitor = new_comp
            if r.athlete_id is not None:
                r.athlete_id = None
                links_cleared += 1
        if original.athlete_id is not None:
            db.add(
                RaceCompetitorLinkAudit(
                    competitor=new_comp,
                    action=LinkAuditAction.unlink,
                    previous_athlete_id=original.athlete_id,
                    new_athlete_id=None,
                    results_propagated=links_cleared,
                    user_id=actor.id,
                    created_at=datetime.now(timezone.utc),
                )
            )

    if relabel is not None:
        relabel.discriminator = ""
    for side_name in ("left_record", "right_record"):
        record = dict(getattr(cand, side_name) or {})
        if _ATTACHED_KEY in record:
            record.pop(_ATTACHED_KEY)
            setattr(cand, side_name, record)
    cand.state = IdentityCandidateState.pending
    cand.reversed_by_user_id = actor.id
    cand.reversed_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "race_identity_reversed candidate_id=%s previous=%s split=%s results_moved=%d "
        "links_cleared=%d",
        cand.id,
        previous.value,
        split,
        len(moved),
        links_cleared,
    )
    return ReversalOutcome(
        candidate_id=cand.id,
        state=IdentityCandidateState.pending.value,
        split=split and original is not None,
        results_moved=len(moved),
        links_cleared=links_cleared,
    )


def _moved_side(cand: RaceIdentityCandidate, moved_triples: set[Triple]) -> dict[str, Any]:
    """El lado del par cuya terna fue adjuntada por la decisión."""
    for side in (cand.left_record or {}, cand.right_record or {}):
        if record_triple(side) in moved_triples or side.get(_ATTACHED_KEY):
            return side
    return cand.right_record or {}


# ---------------------------------------------------------------------------
# Registro de resultados adjuntados en la ingesta
# ---------------------------------------------------------------------------


async def record_attached_results(
    db: AsyncSession,
    attachments: Mapping[int, Sequence[tuple[Triple, int]]],
) -> None:
    """Anota en el candidato los ``race_results.id`` que entraron bajo una
    firma adjuntada por su decisión ``same_person`` — ``{candidate_id:
    [(terna, result_id), ...]}``. Es lo que hace exacta la reversión
    posterior. Lo llama el ingestor antes de su commit."""
    for candidate_id, entries in attachments.items():
        if not entries:
            continue
        cand = (
            await db.execute(
                select(RaceIdentityCandidate).where(RaceIdentityCandidate.id == candidate_id)
            )
        ).scalars().first()
        if cand is None:
            continue
        for side_name in ("left_record", "right_record"):
            record = dict(getattr(cand, side_name) or {})
            triple = record_triple(record)
            ids = [rid for t, rid in entries if t == triple]
            if not ids:
                continue
            record[_ATTACHED_KEY] = sorted(set(record.get(_ATTACHED_KEY) or []) | set(ids))
            setattr(cand, side_name, record)
