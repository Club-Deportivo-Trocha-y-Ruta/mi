"""Pseudonimización determinista para el módulo agentico race (F4 §4.2 nodo 3).

Diseño:
- Hash SHA-256 (``athlete_id::salt``) → primer byte selecciona color,
  segundo byte selecciona animal. 30 colores × 30 animales = 900
  pseudónimos posibles → colisiones improbables para un club ≤50 atletas.
- Pseudónimo estable por ``(athlete_id, salt)`` — si el salt cambia, el
  pseudónimo cambia (rotación periódica posible). El salt default vive
  en ``app.config.settings.race_anonymizer_salt`` (TODO F5) o en una
  constante interna ``_DEFAULT_SALT``.
- Adjetivo en mayúsculas inicial, animal capitalizado → "AzulZorro",
  "VerdePuma", etc. Fácil de leer para el coach al verificar drafts.

Privacidad:
- El mapping pseudónimo → id real se persiste en
  ``anonymization_mappings`` (tabla F0) y SE MANTIENE en el state del
  grafo para que el nodo final ``rehydrate_names`` revierta. Pero NUNCA
  se serializa hacia el LLM ni se incluye en eventos.
"""

from __future__ import annotations

import hashlib

# 30 colores en español (sin tildes para evitar issues en logs/CLI).
COLORS: list[str] = [
    "Azul",
    "Rojo",
    "Verde",
    "Negro",
    "Blanco",
    "Gris",
    "Amarillo",
    "Naranja",
    "Violeta",
    "Rosado",
    "Cafe",
    "Dorado",
    "Plateado",
    "Bronce",
    "Cobre",
    "Esmeralda",
    "Carmesi",
    "Indigo",
    "Magenta",
    "Cian",
    "Ocre",
    "Coral",
    "Ambar",
    "Beige",
    "Lila",
    "Turquesa",
    "Marfil",
    "Granate",
    "Salmon",
    "Mostaza",
]

# 30 animales (todos en MTB / outdoor — temática deportiva).
ANIMALS: list[str] = [
    "Zorro",
    "Puma",
    "Aguila",
    "Halcon",
    "Lobo",
    "Tigre",
    "Leon",
    "Jaguar",
    "Cobra",
    "Tiburon",
    "Lince",
    "Pantera",
    "Buho",
    "Condor",
    "Ciervo",
    "Antilope",
    "Bisonte",
    "Caribu",
    "Coyote",
    "Hurón",
    "Llama",
    "Vicuna",
    "Onza",
    "Visón",
    "Yak",
    "Berraco",
    "Caiman",
    "Garza",
    "Ibis",
    "Quetzal",
]

assert len(COLORS) == 30, "COLORS debe tener 30 elementos"
assert len(ANIMALS) == 30, "ANIMALS debe tener 30 elementos"

_DEFAULT_SALT = "tyr-race-v2"


def make_pseudonym(athlete_id: int, salt: str = _DEFAULT_SALT) -> str:
    """Genera un pseudónimo estable a partir de ``athlete_id``.

    Args:
        athlete_id: PK del atleta.
        salt: salt para mezclar — cambia el pseudónimo si rota.

    Returns:
        String formato ``"ColorAnimal"`` (ej. ``"AzulZorro"``).
        Estable: misma input → misma salida.

    Notas:
        - Usa SHA-256 truncado (primeros 4 bytes) para selección
          determinística. SHA-256 sin secreto está bien aquí: el
          objetivo no es secret-keeping (eso es responsabilidad del
          ``salt`` y de no exponer el mapping) sino estabilidad +
          distribución uniforme.
    """
    raw = f"{athlete_id}::{salt}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    color = COLORS[digest[0] % len(COLORS)]
    animal = ANIMALS[digest[1] % len(ANIMALS)]
    return f"{color}{animal}"


__all__ = ["COLORS", "ANIMALS", "make_pseudonym"]
