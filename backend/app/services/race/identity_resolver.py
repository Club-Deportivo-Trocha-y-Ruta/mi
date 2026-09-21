"""Resolución de identidad en la ingesta (feature 044, US4 — research R-06).

Reemplaza el upsert por ``normalized_name`` que tenía el ingestor. Ese upsert
fallaba en las dos direcciones: fusionaba en silencio a dos homónimos y
partía en dos a una misma persona impresa con y sin segundo apellido.

``IdentityResolver.resolve`` sigue la tabla del contrato
(``contracts/identity-review-api.md`` §Resolver), en este orden:

1. **Firma exacta** ``(normalized_name, club_norm, city_norm)`` → su
   competidor. Ensancha ``first_season``/``last_season``. Si la terna está
   **separada por categoría** (varias firmas con ``discriminator`` o una
   decisión ``different_people`` entre dos registros de la misma terna), se
   elige la única firma cuyo discriminador es compatible con la categoría de
   la fila; si no hay ninguna o hay varias de personas distintas →
   ``IdentityUnresolved``. Ver "Discriminador" abajo.
2. **Decisión ``same_person``** sobre un candidato que involucra la terna →
   el competidor decidido + una firma nueva con ``source_candidate_id`` (es
   lo que permite revertir la decisión con exactitud).
3. **Decisión ``different_people``** → el competidor del otro lado queda
   excluido de la búsqueda por nombre (paso 5), lo que termina en un
   competidor nuevo.
4. **Candidato pendiente** que involucra la terna → ``IdentityUnresolved``.
5. **Por nombre**: ninguno → competidor nuevo + firma; uno → se adjunta +
   firma; varios sin desempate → ``IdentityUnresolved``.

``IdentityUnresolved`` es una guarda de clase 500: con el candado de commit
(``409 identity_review_pending``) no debería alcanzarse nunca. En ``strict=False``
(dry-run) no se lanza: se crea un competidor provisional, que el rollback del
dry-run descarta, y el ingestor lo reporta como advertencia.

Concurrencia: la firma nueva se inserta dentro de un SAVEPOINT. Si otra
ingesta insertó la misma terna entre la lectura y la escritura, el UNIQUE
``uq_race_competitor_signatures_identity`` rechaza la segunda, el SAVEPOINT se
deshace (incluido el competidor recién creado) y se reusa el competidor dueño
de la firma ganadora — releído con ``FOR UPDATE`` para ver la fila confirmada
aunque el snapshot de la transacción sea anterior (InnoDB REPEATABLE READ).

Discriminador (decisión del dueño 2026-09-21, "separar por categoría")
-----------------------------------------------------------------------
Dos personas con idéntico nombre, club y ciudad (padre e hijo del mismo club)
solo se distinguen por su categoría. ``category_discriminator`` fija la regla:
``"<sexo>:<edad_min>-<edad_max>@<temporada>"`` — sexo ``M``/``F``/``X``
(mixta) y rango de edad **de la fila del catálogo** (no del encabezado
impreso, así un renombre no lo cambia), más la temporada en que se observó.
Una fila es compatible con un discriminador si el sexo no choca y su rango de
edad se solapa con el rango esperado para su temporada: el rango del
discriminador desplazado por los años transcurridos, con
``AGE_TOLERANCE_YEARS`` de holgura a cada lado (los cortes de categoría son
por año de nacimiento). Un niño de Infantil A en 2025 sigue siendo compatible
con Infantil B en 2026; un Master A nunca lo es con un Infantil.

Privacidad: ningún log ni mensaje de excepción lleva nombre, club ni ciudad —
solo ids y conteos.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_identity_candidate import (
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.services.race.normalizer import normalize_club, normalize_name

logger = logging.getLogger(__name__)


#: Longitudes de las columnas de ``race_competitor_signatures`` — la terna se
#: trunca igual en todos los caminos para que una misma forma impresa
#: produzca siempre la misma clave.
_NAME_MAX = 160
_CLUB_MAX = 150
_CITY_MAX = 100

Triple = tuple[str, str, str]

#: Holgura, en años, del rango de edad esperado de un discriminador.
AGE_TOLERANCE_YEARS = 1

_SEX_CODES = {"M": "M", "F": "F", "MIXED": "X"}
_INF = 10_000


def band_discriminator(
    sex: str | None, age_min: int | None, age_max: int | None, season: int
) -> str:
    """``"<sexo>:<min>-<max>@<temporada>"``; bordes abiertos quedan vacíos."""
    code = _SEX_CODES.get(sex or "", "X")
    lo = "" if age_min is None else str(age_min)
    hi = "" if age_max is None else str(age_max)
    return f"{code}:{lo}-{hi}@{season}"[:32]


def category_discriminator(category: Any, season: int) -> str:
    """Discriminador de una fila del catálogo ``RaceCategory`` en una temporada."""
    sex = getattr(category.sex, "value", category.sex)
    return band_discriminator(sex, category.age_min, category.age_max, season)


def discriminator_compatible(
    discriminator: str,
    sex: str | None,
    age_min: int | None,
    age_max: int | None,
    season: int,
) -> bool:
    """¿Puede la persona de ``discriminator`` correr en esta categoría en
    ``season``? Ver la regla en el docstring del módulo."""
    try:
        d_sex, rest = discriminator.split(":", 1)
        band, ref = rest.split("@", 1)
        lo_s, hi_s = band.split("-", 1)
        ref_season = int(ref)
    except ValueError:
        return False
    row_sex = _SEX_CODES.get(sex or "", "X")
    if d_sex != "X" and row_sex != "X" and d_sex != row_sex:
        return False
    shift = season - ref_season
    exp_lo = (int(lo_s) if lo_s else 0) + shift - AGE_TOLERANCE_YEARS
    exp_hi = (int(hi_s) + shift + AGE_TOLERANCE_YEARS) if hi_s else _INF
    row_lo = age_min if age_min is not None else 0
    row_hi = age_max if age_max is not None else _INF
    return row_lo <= exp_hi and exp_lo <= row_hi


def signature_triple(name: str, club: str | None, city: str | None) -> Triple:
    """Terna normalizada ``(normalized_name, club_norm, city_norm)``.

    La ciudad usa la misma normalización que el club (placeholders → ``''``),
    como fija ``data-model.md`` §3.
    """
    return (
        normalize_name(name)[:_NAME_MAX],
        normalize_club(club or "")[:_CLUB_MAX],
        normalize_club(city or "")[:_CITY_MAX],
    )


def record_discriminator(record: dict) -> str:
    """Discriminador de un snapshot (``''`` si no fue separado)."""
    return record.get("discriminator") or ""


def record_triple(record: dict) -> Triple:
    """Terna de un snapshot de candidato (``left_record`` / ``right_record``)."""
    return (
        record.get("normalized_name") or "",
        record.get("club_norm") or "",
        record.get("city_norm") or "",
    )


class IdentityUnresolved(RuntimeError):
    """Una fila no tiene resolución de identidad sin intervención del coach.

    Guarda de clase 500: después del candado de commit no debería ocurrir.
    El mensaje lleva solo un motivo y conteos, nunca nombres.
    """

    def __init__(self, reason: str, *, competitors: int = 0) -> None:
        super().__init__(
            f"identidad sin resolver: motivo={reason} competidores={competitors}"
        )
        self.reason = reason
        self.competitors = competitors


class ResolutionBranch(str, enum.Enum):
    """Rama de la tabla del contrato que resolvió la fila."""

    signature_hit = "signature_hit"
    name_attach = "name_attach"
    decision_same_person = "decision_same_person"
    decision_different_people = "decision_different_people"
    new_competitor = "new_competitor"
    provisional = "provisional"


@dataclass(frozen=True)
class Resolution:
    """Resultado de ``IdentityResolver.resolve``.

    ``source_candidate_id`` es el candidato cuya decisión ``same_person``
    adjuntó la firma usada (en esta llamada o en una anterior); el ingestor
    lo usa para anotar los resultados que una reversión debe mover.
    """

    competitor: RaceCompetitor
    created: bool
    branch: ResolutionBranch
    source_candidate_id: Optional[int] = None


@dataclass(frozen=True)
class _DecisionHit:
    candidate_id: int
    state: IdentityCandidateState
    other_triple: Triple
    other_competitor_id: Optional[int]
    this_discriminator: str = ""
    other_discriminator: str = ""


class IdentityResolver:
    """Resuelve filas impresas a ``RaceCompetitor`` dentro de la transacción
    del ingestor. Una instancia por ingesta: cachea el índice de candidatos.
    """

    def __init__(self, db: AsyncSession, *, strict: bool = True) -> None:
        self.db = db
        self.strict = strict
        self._decisions: Optional[dict[Triple, list[_DecisionHit]]] = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def resolve(
        self,
        *,
        name: str,
        club: str | None,
        city: str | None,
        season: int,
        sex: CompetitorSex | None = None,
        category: Any = None,
    ) -> Resolution:
        """Resuelve una fila impresa. Ver la tabla del docstring del módulo.

        ``category`` (``RaceCategory`` de la fila) solo se usa cuando la terna
        está separada por categoría; sin ella, una terna separada no se
        resuelve."""
        triple = signature_triple(name, club, city)
        if not triple[0]:
            raise ValueError("nombre vacío tras normalizar")

        # 1. Firma exacta — o, si la terna está separada, por discriminador.
        signatures = await self._signatures_for(triple)
        discriminators = {s.discriminator for s in signatures if s.discriminator}
        discriminators |= await self._intra_discriminators(triple)
        if discriminators:
            return await self._resolve_by_discriminator(
                triple, signatures, discriminators, season, category,
                name=name, club=club, city=city, sex=sex,
            )
        signature = next((s for s in signatures if not s.discriminator), None)
        if signature is not None:
            _widen(signature, season)
            competitor = await self._competitor_by_id(signature.competitor_id)
            return Resolution(
                competitor=competitor,
                created=False,
                branch=ResolutionBranch.signature_hit,
                source_candidate_id=signature.source_candidate_id,
            )

        # 2-4. Decisiones del coach sobre esta terna.
        same_targets: dict[int, int] = {}  # competitor_id -> candidate_id
        excluded: set[int] = set()
        pending = False
        for hit in await self._decisions_for(triple):
            if hit.other_triple == triple:
                continue  # misma terna: resuelto por discriminador (paso 1)
            if hit.state == IdentityCandidateState.pending:
                pending = True
                continue
            other_id = await self._resolve_other_side(hit)
            if hit.state == IdentityCandidateState.same_person:
                if other_id is not None:
                    same_targets.setdefault(other_id, hit.candidate_id)
            elif other_id is not None:
                excluded.add(other_id)

        if len(same_targets) > 1 or set(same_targets) & excluded:
            return await self._unresolved(
                "decisiones_contradictorias", len(same_targets), triple, season, name, club, city, sex
            )
        if same_targets:
            (competitor_id, candidate_id), = same_targets.items()
            return await self._attach(
                competitor_id,
                triple,
                season,
                source_candidate_id=candidate_id,
                branch=ResolutionBranch.decision_same_person,
            )
        if pending:
            return await self._unresolved(
                "candidato_pendiente", 0, triple, season, name, club, city, sex
            )

        # 5. Por nombre.
        by_name = [
            c for c in await self._competitors_by_name(triple[0]) if c.id not in excluded
        ]
        if len(by_name) > 1:
            return await self._unresolved(
                "varios_competidores", len(by_name), triple, season, name, club, city, sex
            )
        if len(by_name) == 1:
            return await self._attach(
                by_name[0].id,
                triple,
                season,
                source_candidate_id=None,
                branch=ResolutionBranch.name_attach,
            )
        return await self._create(
            triple,
            season,
            name=name,
            club=club,
            city=city,
            sex=sex,
            branch=(
                ResolutionBranch.decision_different_people
                if excluded
                else ResolutionBranch.new_competitor
            ),
        )

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------

    async def _signatures_for(self, triple: Triple) -> list[RaceCompetitorSignature]:
        """Todas las firmas de la terna, con cualquier discriminador."""
        result = await self.db.execute(
            select(RaceCompetitorSignature).where(
                RaceCompetitorSignature.normalized_name == triple[0],
                RaceCompetitorSignature.club_norm == triple[1],
                RaceCompetitorSignature.city_norm == triple[2],
            )
        )
        return sorted(result.scalars().all(), key=lambda s: (s.discriminator or "", s.id or 0))

    async def _find_signature(
        self, triple: Triple, discriminator: str = "", *, for_update: bool = False
    ) -> Optional[RaceCompetitorSignature]:
        stmt = select(RaceCompetitorSignature).where(
            RaceCompetitorSignature.normalized_name == triple[0],
            RaceCompetitorSignature.club_norm == triple[1],
            RaceCompetitorSignature.city_norm == triple[2],
            RaceCompetitorSignature.discriminator == discriminator,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _competitor_by_id(self, competitor_id: int) -> RaceCompetitor:
        result = await self.db.execute(
            select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
        )
        competitor = result.scalars().first()
        if competitor is None:
            raise IdentityUnresolved("competidor_inexistente")
        return competitor

    async def _competitors_by_name(self, normalized: str) -> list[RaceCompetitor]:
        result = await self.db.execute(
            select(RaceCompetitor).where(RaceCompetitor.normalized_name == normalized)
        )
        return sorted(result.scalars().all(), key=lambda c: c.id)

    async def _decisions_for(self, triple: Triple) -> list[_DecisionHit]:
        if self._decisions is None:
            result = await self.db.execute(select(RaceIdentityCandidate))
            index: dict[Triple, list[_DecisionHit]] = {}
            for cand in result.scalars().all():
                left, right = cand.left_record or {}, cand.right_record or {}
                for this, other in ((left, right), (right, left)):
                    index.setdefault(record_triple(this), []).append(
                        _DecisionHit(
                            candidate_id=cand.id,
                            state=IdentityCandidateState(cand.state),
                            other_triple=record_triple(other),
                            other_competitor_id=other.get("competitor_id"),
                            this_discriminator=record_discriminator(this),
                            other_discriminator=record_discriminator(other),
                        )
                    )
            self._decisions = index
        return self._decisions.get(triple, [])

    async def _intra_discriminators(self, triple: Triple) -> set[str]:
        """Discriminadores de las decisiones ``different_people`` entre dos
        registros de esta misma terna (homónimos separados por categoría)."""
        found: set[str] = set()
        for hit in await self._decisions_for(triple):
            if (
                hit.other_triple == triple
                and hit.state == IdentityCandidateState.different_people
            ):
                found |= {hit.this_discriminator, hit.other_discriminator}
        found.discard("")
        return found

    async def _resolve_other_side(self, hit: _DecisionHit) -> Optional[int]:
        """Competidor actual del otro lado del par: primero por su firma (la
        fuente de verdad), luego por el id del snapshot si aún existe."""
        signature = await self._find_signature(hit.other_triple, hit.other_discriminator)
        if signature is not None:
            return signature.competitor_id
        if hit.other_competitor_id is not None:
            result = await self.db.execute(
                select(RaceCompetitor).where(RaceCompetitor.id == hit.other_competitor_id)
            )
            if result.scalars().first() is not None:
                return hit.other_competitor_id
        return None

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------

    async def _resolve_by_discriminator(
        self,
        triple: Triple,
        signatures: list[RaceCompetitorSignature],
        discriminators: set[str],
        season: int,
        category: Any,
        *,
        name: str,
        club: str | None,
        city: str | None,
        sex: CompetitorSex | None,
    ) -> Resolution:
        """Terna separada por categoría: la única firma compatible con la
        categoría de la fila. Si el discriminador compatible viene de una
        decisión y aún no tiene firma, se crea el competidor de ese lado."""
        if category is None:
            return await self._unresolved(
                "terna_separada_sin_categoria", 0, triple, season, name, club, city, sex
            )
        row_sex = getattr(category.sex, "value", category.sex)
        compatible = sorted(
            d
            for d in discriminators
            if discriminator_compatible(d, row_sex, category.age_min, category.age_max, season)
        )
        by_disc = {s.discriminator: s for s in signatures}
        owners = {by_disc[d].competitor_id for d in compatible if d in by_disc}
        unique_person = len(compatible) == 1 or (
            len(owners) == 1 and all(d in by_disc for d in compatible)
        )
        if not compatible or not unique_person:
            return await self._unresolved(
                "discriminador_ambiguo" if compatible else "discriminador_incompatible",
                len(compatible),
                triple, season, name, club, city, sex,
            )
        chosen = compatible[0]
        signature = by_disc.get(chosen)
        if signature is not None:
            _widen(signature, season)
            competitor = await self._competitor_by_id(signature.competitor_id)
            return Resolution(
                competitor=competitor,
                created=False,
                branch=ResolutionBranch.signature_hit,
                source_candidate_id=signature.source_candidate_id,
            )
        return await self._create(
            triple,
            season,
            name=name,
            club=club,
            city=city,
            sex=sex,
            branch=ResolutionBranch.decision_different_people,
            discriminator=chosen,
        )

    async def _attach(
        self,
        competitor_id: int,
        triple: Triple,
        season: int,
        *,
        source_candidate_id: Optional[int],
        branch: ResolutionBranch,
    ) -> Resolution:
        try:
            async with self.db.begin_nested():
                self.db.add(
                    RaceCompetitorSignature(
                        competitor_id=competitor_id,
                        normalized_name=triple[0],
                        club_norm=triple[1],
                        city_norm=triple[2],
                        first_season=season,
                        last_season=season,
                        source_candidate_id=source_candidate_id,
                    )
                )
                await self.db.flush()
        except IntegrityError:
            return await self._reuse_concurrent(triple, season)
        competitor = await self._competitor_by_id(competitor_id)
        return Resolution(
            competitor=competitor,
            created=False,
            branch=branch,
            source_candidate_id=source_candidate_id,
        )

    async def _create(
        self,
        triple: Triple,
        season: int,
        *,
        name: str,
        club: str | None,
        city: str | None,
        sex: CompetitorSex | None,
        branch: ResolutionBranch,
        discriminator: str = "",
    ) -> Resolution:
        competitor = RaceCompetitor(
            normalized_name=triple[0],
            display_name=name.strip()[:_NAME_MAX],
            club_text=(club or None) and club[:150],
            city_text=(city or None) and city[:_CITY_MAX],
            sex=sex,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(competitor)
                await self.db.flush()
                self.db.add(
                    RaceCompetitorSignature(
                        competitor_id=competitor.id,
                        normalized_name=triple[0],
                        club_norm=triple[1],
                        city_norm=triple[2],
                        discriminator=discriminator,
                        first_season=season,
                        last_season=season,
                    )
                )
                await self.db.flush()
        except IntegrityError:
            return await self._reuse_concurrent(triple, season, discriminator)
        return Resolution(competitor=competitor, created=True, branch=branch)

    async def _reuse_concurrent(
        self, triple: Triple, season: int, discriminator: str = ""
    ) -> Resolution:
        """Otra transacción ganó la carrera por la misma terna: se reusa su
        competidor. Lectura con bloqueo para ver la fila ya confirmada."""
        signature = await self._find_signature(triple, discriminator, for_update=True)
        if signature is None:
            raise IdentityUnresolved("colision_sin_firma")
        _widen(signature, season)
        logger.info(
            "race_identity_signature_race_lost competitor_id=%s", signature.competitor_id
        )
        competitor = await self._competitor_by_id(signature.competitor_id)
        return Resolution(
            competitor=competitor,
            created=False,
            branch=ResolutionBranch.signature_hit,
            source_candidate_id=signature.source_candidate_id,
        )

    async def _unresolved(
        self,
        reason: str,
        competitors: int,
        triple: Triple,
        season: int,
        name: str,
        club: str | None,
        city: str | None,
        sex: CompetitorSex | None,
    ) -> Resolution:
        if self.strict:
            logger.error(
                "race_identity_unresolved reason=%s competitors=%d", reason, competitors
            )
            raise IdentityUnresolved(reason, competitors=competitors)
        # Dry-run: competidor provisional sin firma — el rollback lo descarta.
        competitor = RaceCompetitor(
            normalized_name=triple[0],
            display_name=name.strip()[:_NAME_MAX],
            club_text=(club or None) and club[:150],
            city_text=(city or None) and city[:_CITY_MAX],
            sex=sex,
        )
        self.db.add(competitor)
        await self.db.flush()
        return Resolution(
            competitor=competitor, created=True, branch=ResolutionBranch.provisional
        )


def _widen(signature: RaceCompetitorSignature, season: int) -> None:
    if season < signature.first_season:
        signature.first_season = season
    if season > signature.last_season:
        signature.last_season = season
