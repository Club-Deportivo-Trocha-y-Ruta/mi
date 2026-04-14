"""Seed script — crea datos iniciales para desarrollo.

Uso:
    cd backend
    python -m scripts.seed

Requiere que las tablas ya existan (alembic upgrade head).
"""

import asyncio
from datetime import date

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
        location="Cali, Valle del Cauca",
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
        },
        {
            "first_name": "Valentina",
            "last_name": "Martinez",
            "birth_date": date(2013, 7, 22),
            "sex": Sex.F,
            "club_join_date": date(2023, 4, 1),  # ~3 años en el club
        },
        {
            "first_name": "Miguel",
            "last_name": "Ramirez",
            "birth_date": date(2012, 11, 5),
            "sex": Sex.M,
            "club_join_date": date(2025, 4, 1),  # ~1 año en el club
        },
        {
            "first_name": "Isabella",
            "last_name": "Garcia",
            "birth_date": date(2015, 1, 30),
            "sex": Sex.F,
            "club_join_date": date(2025, 4, 1),  # ~1 año en el club
        },
        {
            "first_name": "Andres",
            "last_name": "Caicedo",
            "birth_date": date(2011, 9, 12),
            "sex": Sex.M,
            "club_join_date": date(2022, 4, 1),  # ~4 años en el club
        },
    ]

    for data in athletes_data:
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

        # Registrar como miembro del club
        session.add(
            ClubMember(
                club_id=club.id,
                user_id=athlete_user.id,
                role_in_club=ClubRole.athlete,
            )
        )

    await session.commit()
    print("Seed completado:")
    print(f"  Club: {club.name} ({club.code})")
    print(f"  Admin: {admin.email} / Admin2026!")
    print(f"  Coach: {coach.email} / Coach2026!")
    print(f"  Atletas: {len(athletes_data)} creados")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
