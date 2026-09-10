"""Seed script — crea datos iniciales para desarrollo.

Uso:
    cd backend
    python -m scripts.seed

Requiere que las tablas ya existan (alembic upgrade head).
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

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
from app.models.anthropometry import AnthropometricRecord
from app.models.growth import GrowthSource
from app.models.parental_consent import ParentalConsent
from app.models.privacy_policy import PrivacyPolicy
from app.services.auth import hash_password
from app.services.category import compute_age_decimal
from app.services.growth import calculate_growth_percentiles
from app.services.phv import calculate_mirwald_offset


# Mediciones sintéticas del atleta demo (feature 040). Valores inventados y
# plausibles para un niño de ~11-12 años; no corresponden a ninguna persona.
# Tres registros separados por 4-5 meses para que el tab Crecimiento, la curva
# y la vista de familia tengan historial (velocidad, próxima medición) en el
# stack de desarrollo / e2e sin depender de datos reales.
DEMO_ANTHROPOMETRY = [
    # (fecha, peso kg, talla de pie cm, talla sentado cm, envergadura cm)
    # Todas anteriores al 2026-04-14 (fecha que registra `e2e/anthropometry.spec.ts`
    # con talla 155.0) para que esa medición quede como la más reciente y la
    # velocidad calculada siga siendo positiva y plausible.
    (date(2025, 6, 15), "40.00", "150.0", "76.5", "151.0"),
    (date(2025, 10, 15), "41.00", "152.0", "77.3", "153.0"),
    (date(2026, 2, 15), "42.00", "154.0", "78.0", "155.0"),
]

# La OMS no publica peso/edad por encima de los 10 años (misma regla que
# ``app.routers.anthropometry.WEIGHT_AGE_MAX_MONTHS``).
_WEIGHT_AGE_MAX_MONTHS = 120.5


async def seed_demo_anthropometry(
    session: AsyncSession, athlete: Athlete, evaluator: User
) -> int:
    """Crea las mediciones demo replicando los cálculos del endpoint POST."""
    created = 0
    for eval_date, weight, height, sitting, arm_span in DEMO_ANTHROPOMETRY:
        age = compute_age_decimal(athlete.birth_date, eval_date)
        phv = calculate_mirwald_offset(
            sex=athlete.sex.value,
            age=age,
            weight=float(weight),
            standing_height=float(height),
            sitting_height=float(sitting),
        )
        age_months = age * 12
        try:
            growth = await calculate_growth_percentiles(
                db=session,
                weight_kg=float(weight),
                standing_height_cm=float(height),
                sex=athlete.sex.value,
                age_months=age_months,
                source=GrowthSource.WHO,
            )
        except Exception:  # noqa: BLE001 — tabla LMS ausente: se siembra sin percentiles
            growth = None
        if growth is not None and growth.height_z_score is None and growth.bmi_z_score is None:
            growth = None
        weight_in_range = age_months <= _WEIGHT_AGE_MAX_MONTHS
        bmi_value = float(weight) / (float(height) / 100) ** 2

        session.add(
            AnthropometricRecord(
                athlete_id=athlete.id,
                evaluation_date=eval_date,
                weight_kg=Decimal(weight),
                standing_height_cm=Decimal(height),
                arm_span_cm=Decimal(arm_span),
                sitting_height_cm=Decimal(sitting),
                leg_length_cm=phv["leg_length_cm"],
                leg_sitting_ratio=phv["leg_sitting_ratio"],
                maturity_offset=phv["maturity_offset"],
                age_at_phv=phv["age_at_phv"],
                maturation_status=phv["maturation_status"],
                training_implications=phv["training_implications"],
                evaluated_by=evaluator.id,
                height_z_score=growth.height_z_score if growth else None,
                height_percentile=growth.height_percentile if growth else None,
                bmi=Decimal(str(round(bmi_value, 2))),
                bmi_z_score=growth.bmi_z_score if growth else None,
                bmi_percentile=growth.bmi_percentile if growth else None,
                weight_z_score=growth.weight_z_score if growth and weight_in_range else None,
                weight_percentile=(
                    growth.weight_percentile if growth and weight_in_range else None
                ),
                nutritional_status=growth.nutritional_status_bmi if growth else None,
                growth_source=GrowthSource.WHO,
            )
        )
        created += 1
    await session.flush()
    return created


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

    # --- Segundo coach de prueba (feature 041 — gobernanza multi-coach) ---
    coach2 = User(
        email="entrenador2@trochyruta.com",
        hashed_password=hash_password("Coach2026!"),
        first_name="Beto",
        last_name="Coach",
        phone="3007654321",
        role=UserRole.coach,
        can_login=True,
        created_by=admin.id,
    )
    session.add(coach2)
    await session.flush()

    session.add(
        ClubMember(
            club_id=club.id,
            user_id=coach2.id,
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

    # --- Mediciones antropométricas demo del primer atleta ---
    demo_records = 0
    if first_athlete is not None:
        demo_records = await seed_demo_anthropometry(session, first_athlete, coach)

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
    print(f"  Mediciones demo: {demo_records} creadas")
    print(f"  Padre: {parent.email} / Parent2026!")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
