"""Seed script — crea datos iniciales para desarrollo.

Uso:
    cd backend
    python -m scripts.seed

Requiere que las tablas ya existan (alembic upgrade head).
"""

import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models import (
    User,
    UserRole,
    Club,
    ClubMember,
    ClubRole,
    Athlete,
    Sex,
)
from app.models.athlete import ParentAthlete, FamilyRelationship
from app.models.parental_consent import ParentalConsent
from app.models.privacy_policy import PrivacyPolicy
from app.services.auth import hash_password


async def seed(session: AsyncSession) -> None:
    # Verificar si ya hay datos
    existing = await session.execute(select(Club).limit(1))
    if existing.scalar_one_or_none():
        print("La base de datos ya tiene datos. Seed omitido.")
        return

    # --- Club ---
    club = Club(
        name="Club Deportivo Trocha y Ruta",
        code="trocha-y-ruta",
        location="Yumbo, Valle del Cauca",
    )
    session.add(club)
    await session.flush()

    # --- Admin ---
    admin = User(
        email="admin@trochyruta.com",
        hashed_password=hash_password("Admin2026!"),
        first_name="Administrador",
        last_name="Trocha",
        role=UserRole.admin,
        can_login=True,
    )
    session.add(admin)
    await session.flush()

    # Admin como miembro del club
    session.add(
        ClubMember(
            club_id=club.id,
            user_id=admin.id,
            role_in_club=ClubRole.admin,
        )
    )

    # --- Coach de prueba ---
    coach = User(
        email="entrenador@trochyruta.com",
        hashed_password=hash_password("Coach2026!"),
        first_name="Juan",
        last_name="Diaz",
        phone="3001234567",
        role=UserRole.coach,
        can_login=True,
        created_by=admin.id,
    )
    session.add(coach)
    await session.flush()

    session.add(
        ClubMember(
            club_id=club.id,
            user_id=coach.id,
            role_in_club=ClubRole.coach,
        )
    )

    # --- Atletas de ejemplo ---
    athletes_data = [
        {
            "first_name": "Santiago",
            "last_name": "Lopez",
            "birth_date": date(2014, 3, 15),
            "sex": Sex.M,
            "club_join_date": date(2024, 3, 15),  # ~2 años en el club
        }
    ]

    first_athlete = None
    for i, data in enumerate(athletes_data):
        # Crear user con role=athlete, can_login=false
        athlete_user = User(
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=UserRole.athlete,
            can_login=False,
            created_by=coach.id,
        )
        session.add(athlete_user)
        await session.flush()

        # Crear perfil de atleta
        athlete = Athlete(
            user_id=athlete_user.id,
            first_name=data["first_name"],
            last_name=data["last_name"],
            birth_date=data["birth_date"],
            sex=data["sex"],
            club_join_date=data["club_join_date"],
            club_id=club.id,
            created_by=coach.id,
        )
        session.add(athlete)
        await session.flush()

        if i == 0:
            first_athlete = athlete  # guardar referencia al primero

        # Registrar como miembro del club
        session.add(
            ClubMember(
                club_id=club.id,
                user_id=athlete_user.id,
                role_in_club=ClubRole.athlete,
            )
        )

    # --- Padre de prueba ---
    parent = User(
        email="padre@trochayruta.com",
        hashed_password=hash_password("Parent2026!"),
        first_name="Carlos",
        last_name="Garcia",
        phone="3009876543",
        role=UserRole.parent,
        can_login=True,
        created_by=coach.id,
    )
    session.add(parent)
    await session.flush()

    session.add(
        ClubMember(
            club_id=club.id,
            user_id=parent.id,
            role_in_club=ClubRole.parent,
        )
    )
    await session.flush()

    # Vincular padre con Santiago Lopez (primer atleta del seed)
    if first_athlete is not None:
        session.add(
            ParentAthlete(
                parent_id=parent.id,
                athlete_id=first_athlete.id,
                relationship_type=FamilyRelationship.padre,
            )
        )
        await session.flush()

        # Consentimiento parental para entorno dev: incluye third_party_sharing=True
        # para que las pruebas E2E del módulo de IA puedan ejecutarse sin que
        # el gate de Ley 1581/2012 las bloquee.
        active_policy_stmt = (
            select(PrivacyPolicy)
            .where(PrivacyPolicy.deprecated_at.is_(None))
            .order_by(PrivacyPolicy.effective_date.desc())
            .limit(1)
        )
        active_policy = (await session.execute(active_policy_stmt)).scalar_one_or_none()
        if active_policy is not None:
            session.add(
                ParentalConsent(
                    parent_user_id=parent.id,
                    athlete_id=first_athlete.id,
                    consent_version=active_policy.version,
                    policy_id=active_policy.id,
                    consented_at=datetime.now(timezone.utc),
                    consent_method="dev_seed",
                    data_collection=True,
                    training_tracking=True,
                    anthropometry=True,
                    third_party_sharing=True,
                )
            )
            await session.flush()

    await session.commit()
    print("Seed completado:")
    print(f"  Club: {club.name} ({club.code})")
    print(f"  Admin: {admin.email} / Admin2026!")
    print(f"  Coach: {coach.email} / Coach2026!")
    print(f"  Atletas: {len(athletes_data)} creados")
    print(f"  Padre: {parent.email} / Parent2026!")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
