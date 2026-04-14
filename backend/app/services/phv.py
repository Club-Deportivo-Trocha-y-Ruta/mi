def calculate_mirwald_offset(
    sex: str,
    age: float,
    weight: float,
    standing_height: float,
    sitting_height: float,
) -> dict:
    """Calcula el Maturity Offset usando la formula Mirwald (2002)."""
    leg_length = standing_height - sitting_height
    ratio = leg_length / sitting_height

    if sex == "M":
        mo = (
            -9.236
            + 0.0002708 * (leg_length * sitting_height)
            - 0.001663 * (age * leg_length)
            + 0.007216 * (age * sitting_height)
            + 0.02292 * (weight / standing_height * 100)
        )
    else:  # F
        mo = (
            -9.376
            + 0.0001882 * (leg_length * sitting_height)
            + 0.0022 * (age * leg_length)
            + 0.005841 * (age * sitting_height)
            - 0.002658 * (age * weight)
            + 0.07693 * (weight / standing_height * 100)
        )

    age_at_phv = age - mo

    if mo < -1.0:
        status = "Pre-PHV"
        implications = (
            "Habilidades, juego, coordinacion. "
            "Fuerza solo peso corporal. Sin intervalos estructurados."
        )
    elif mo > 1.0:
        status = "Post-PHV"
        implications = (
            "Puede iniciar fuerza progresiva. "
            "Entrenamiento mas estructurado permitido."
        )
    else:
        status = "Circa-PHV"
        implications = (
            "EN ESTIRON: reducir volumen repetitivo. "
            "Revisar bici cada 4-6 sem. Vigilar Osgood-Schlatter."
        )

    return {
        "leg_length_cm": round(leg_length, 1),
        "leg_sitting_ratio": round(ratio, 4),
        "maturity_offset": round(mo, 2),
        "age_at_phv": round(age_at_phv, 2),
        "maturation_status": status,
        "training_implications": implications,
    }
