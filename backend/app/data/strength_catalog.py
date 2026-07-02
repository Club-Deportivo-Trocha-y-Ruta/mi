"""
Seed payload for the Strength Training Exercise Library (Feature 021).

Mirrors the shape/convention of `backend/app/data/technique_catalog.py`
(Feature 018): a pure-data module (no DB imports, no side-effects) consumed
by the idempotent Alembic data migration (`a7b8c9d0e1f2_strength_training_library.py`,
research.md D7).

Content basis: research.md D1 (RT4T 5-category movement taxonomy, ASCA
age-banded dosing — 10-12 bodyweight only / 13-15 bodyweight + bands +
light dumbbells). All exercises are original text/ASCII authored for this
catalog — no copied material.

Hard exclusions (FR-019): no clean, snatch, deadlift, back-squat, and no
1RM / max-strength testing protocol anywhere in this file.

Distribution commitment (data-model.md "Seed", SC-007): every non-empty
facet combination of (equipment × age_band × movement_category) has at
least one exercise —
  sin_equipo × 10-12  → all 5 categories
  sin_equipo × 13-15  → all 5 categories
  equipo_gym × 13-15  → all 5 categories
  equipo_gym × 10-12  → intentionally EMPTY (club rule: no bodyweight-only
                         exercise is tagged equipo_gym, and no gym-equipment
                         exercise is offered to the 10-12 band). The UI
                         renders an empty state for this combination.

Field notes (parallel to technique_catalog.py EXERCISES):
  equipment            : "sin_equipo" | "equipo_gym" (EquipmentKind)
  equipment_detail      : short Spanish text naming the specific prop when
                           equipment == "equipo_gym" (e.g. "banda elástica");
                           None for sin_equipo entries.
  movement_category     : one of the 5 MovementCategory values
  suggested_duration_min: default per-entry minutes used for the block
                           running-total indicator (data-model.md §Validation 1)
  suggested_reps        : free text, e.g. "2x10-15" (honors RM ranges without
                           prescribing absolute load, per research.md D1)
  age_bands             : list containing "10-12" and/or "13-15"
  common_errors         : newline-separated list of frequent execution faults
  illustration_ascii    : original ASCII diagram authored for this catalog
  illustration_alt      : plain-language Spanish description for screen readers
"""

EXERCISES: list[dict] = [
    # ── 1 ──────────────────────────────────────────────────────────────────
    {
        "slug": "plancha-frontal",
        "name": "Plancha frontal",
        "summary": (
            "Sostener el cuerpo en línea recta apoyado en antebrazos y puntas de "
            "los pies; activa el core sin mover la columna."
        ),
        "how_to": (
            "1. Apoya los antebrazos en el piso, codos bajo los hombros.\n"
            "2. Extiende las piernas apoyando solo las puntas de los pies.\n"
            "3. Forma una línea recta entre hombros, cadera y talones — sin "
            "hundir ni levantar la cadera.\n"
            "4. Aprieta glúteos y abdomen, respira normal, sostén el tiempo indicado.\n"
            "5. Baja controlado apoyando rodillas al terminar."
        ),
        "common_errors": (
            "Cadera hundida hacia el piso (lumbar sobrecargada).\n"
            "Cadera muy elevada (pierde tensión de core).\n"
            "Aguantar la respiración en vez de respirar normal.\n"
            "Cabeza colgando — mirar un punto fijo en el piso, cuello neutro."
        ),
        "illustration_ascii": (
            "   o   <- cabeza neutra\n"
            " /===\\  <- torso recto (hombro-cadera-talón alineados)\n"
            "  | |\n"
            " _|_|__\n"
            "//    \\\\ <- antebrazos y puntas de pie apoyados"
        ),
        "illustration_alt": (
            "Figura lateral de una persona apoyada sobre los antebrazos y las "
            "puntas de los pies, con el cuerpo formando una línea recta desde "
            "los hombros hasta los talones, sin hundir ni levantar la cadera."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 4,
        "suggested_reps": "3x20-30 seg",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 2 ──────────────────────────────────────────────────────────────────
    {
        "slug": "plancha-lateral",
        "name": "Plancha lateral",
        "summary": (
            "Sostener el cuerpo de lado apoyado en un antebrazo; fortalece los "
            "oblicuos y la estabilidad de cadera."
        ),
        "how_to": (
            "1. Acuéstate de lado, apoya el antebrazo bajo el hombro.\n"
            "2. Apila los pies uno sobre el otro (o el de arriba adelantado "
            "para más equilibrio).\n"
            "3. Levanta la cadera del piso formando una línea recta cabeza-pies.\n"
            "4. Sostén el tiempo indicado sin dejar caer la cadera.\n"
            "5. Baja controlado, cambia de lado."
        ),
        "common_errors": (
            "Cadera cayendo hacia el piso.\n"
            "Hombro de apoyo hundido en vez de activo.\n"
            "Rotar el torso hacia adelante o atrás.\n"
            "Contener la respiración."
        ),
        "illustration_ascii": (
            "      o\n"
            "    / |\n"
            "   /==|===  <- línea recta cabeza a pies, de lado\n"
            "  |   |\n"
            "  ▲   ▲\n"
            " antebrazo y pies apilados"
        ),
        "illustration_alt": (
            "Figura de una persona apoyada de lado sobre un antebrazo, con los "
            "pies apilados y la cadera levantada, formando una línea recta "
            "desde la cabeza hasta los pies."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 4,
        "suggested_reps": "2x15-20 seg por lado",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 3 ──────────────────────────────────────────────────────────────────
    {
        "slug": "bird-dog",
        "name": "Bird-dog (perro de caza)",
        "summary": (
            "Desde cuadrupedia, extender brazo y pierna opuestos manteniendo la "
            "espalda quieta; entrena estabilidad y control lumbo-pélvico."
        ),
        "how_to": (
            "1. Apóyate en manos y rodillas, manos bajo hombros, rodillas bajo cadera.\n"
            "2. Extiende el brazo derecho al frente y la pierna izquierda atrás "
            "al mismo tiempo, en línea con el torso.\n"
            "3. Mantén la espalda plana, sin rotar la cadera ni los hombros.\n"
            "4. Sostén 2-3 segundos, regresa controlado.\n"
            "5. Alterna con el lado contrario (brazo izquierdo - pierna derecha)."
        ),
        "common_errors": (
            "Rotar la cadera al levantar la pierna.\n"
            "Arquear la lumbar en vez de mantenerla neutra.\n"
            "Levantar el brazo o la pierna más alto que el torso.\n"
            "Ir muy rápido — el control importa más que la velocidad."
        ),
        "illustration_ascii": (
            "  brazo →   o   ← mirada al piso\n"
            "        \\ /=\\\n"
            "         X   \\\n"
            "        / \\   \\\n"
            "       ▲   ▲   ← pierna extendida atrás\n"
            "     mano  rodilla apoyada"
        ),
        "illustration_alt": (
            "Figura en cuadrupedia (manos y rodillas apoyadas) extendiendo el "
            "brazo derecho hacia adelante y la pierna izquierda hacia atrás, "
            "manteniendo la espalda plana y horizontal."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 5,
        "suggested_reps": "2x8-10 por lado",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 4 ──────────────────────────────────────────────────────────────────
    {
        "slug": "puente-de-gluteo",
        "name": "Puente de glúteo",
        "summary": (
            "Acostado boca arriba, elevar la cadera apretando glúteos; activa "
            "la cadena posterior sin carga en la espalda."
        ),
        "how_to": (
            "1. Acuéstate boca arriba, rodillas dobladas, pies apoyados cerca "
            "de la cadera, brazos a los lados.\n"
            "2. Aprieta glúteos y empuja los talones para levantar la cadera "
            "hasta formar una línea recta rodillas-cadera-hombros.\n"
            "3. Sostén 1-2 segundos arriba, sin arquear la lumbar de más.\n"
            "4. Baja controlado sin dejar caer la cadera de golpe."
        ),
        "common_errors": (
            "Arquear demasiado la zona lumbar (hiperextensión).\n"
            "Empujar con la espalda en vez de con los glúteos.\n"
            "Pies muy alejados o muy cerca de la cadera.\n"
            "Subir rápido y de golpe en vez de controlado."
        ),
        "illustration_ascii": (
            "      ___\n"
            "     /   \\  <- cadera elevada\n"
            "  o_/     \\_o\n"
            "  hombro   pie apoyado\n"
            "  (apoyo en el piso)"
        ),
        "illustration_alt": (
            "Figura acostada boca arriba con rodillas flexionadas y pies "
            "apoyados en el piso, con la cadera levantada formando una línea "
            "recta entre las rodillas, la cadera y los hombros."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_bilateral",
        "suggested_duration_min": 4,
        "suggested_reps": "3x12-15",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 5 ──────────────────────────────────────────────────────────────────
    {
        "slug": "sentadilla-peso-corporal",
        "name": "Sentadilla con peso corporal",
        "summary": (
            "Flexionar cadera y rodillas hasta bajar el glúteo como si te "
            "fueras a sentar, solo con el propio peso; base de toda la fuerza "
            "de piernas."
        ),
        "how_to": (
            "1. Pies al ancho de los hombros, puntas ligeramente hacia afuera.\n"
            "2. Baja la cadera hacia atrás y abajo, como sentándote en una silla.\n"
            "3. Mantén el pecho arriba y las rodillas alineadas con los pies "
            "(no las dejes caer hacia adentro).\n"
            "4. Baja hasta donde puedas mantener buena técnica (idealmente "
            "muslos paralelos al piso).\n"
            "5. Empuja el piso con toda la planta del pie para subir."
        ),
        "common_errors": (
            "Rodillas colapsando hacia adentro.\n"
            "Talones se despegan del piso.\n"
            "Espalda redondeada en vez de pecho arriba.\n"
            "Bajar solo un poco (rango incompleto) por miedo o falta de movilidad."
        ),
        "illustration_ascii": (
            "   o        o\n"
            "  /|\\      /|\\\n"
            "  / \\  ->  |=|   <- cadera baja, rodillas sobre pies\n"
            " /   \\    _| |_\n"
            "de pie    en sentadilla"
        ),
        "illustration_alt": (
            "Dos posiciones lado a lado: de pie con piernas extendidas, y en "
            "sentadilla con cadera baja, rodillas flexionadas alineadas con "
            "los pies y pecho erguido."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_bilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "3x10-15",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 6 ──────────────────────────────────────────────────────────────────
    {
        "slug": "wall-sit",
        "name": "Sentadilla isométrica en pared (wall sit)",
        "summary": (
            "Sostener la posición de sentadilla con la espalda apoyada en la "
            "pared, sin moverse; entrena resistencia isométrica de piernas."
        ),
        "how_to": (
            "1. Apoya la espalda plana contra una pared.\n"
            "2. Camina los pies hacia adelante y baja hasta que las rodillas "
            "formen ~90°, muslos paralelos al piso.\n"
            "3. Mantén las rodillas alineadas con los tobillos (no más "
            "adelante que la punta del pie).\n"
            "4. Sostén la posición el tiempo indicado, respirando normal.\n"
            "5. Sube deslizando la espalda por la pared."
        ),
        "common_errors": (
            "Rodillas más adelante que los pies (sobrecarga la rodilla).\n"
            "Espalda despegada de la pared.\n"
            "Bajar demasiado poco (ángulo muy abierto, poco estímulo).\n"
            "Aguantar la respiración en vez de respirar normal."
        ),
        "illustration_ascii": (
            "|o           <- espalda apoyada en la pared\n"
            "||\\\n"
            "|| \\____     <- muslos paralelos al piso, 90°\n"
            "||  |   |\n"
            "|| _|   |_\n"
            "pared   pies adelantados"
        ),
        "illustration_alt": (
            "Figura con la espalda apoyada contra una pared, en posición de "
            "sentadilla sostenida con las rodillas dobladas a 90 grados y los "
            "pies adelantados respecto al cuerpo."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_bilateral",
        "suggested_duration_min": 4,
        "suggested_reps": "3x20-40 seg",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 7 ──────────────────────────────────────────────────────────────────
    {
        "slug": "zancada-estatica",
        "name": "Zancada estática (split squat)",
        "summary": (
            "Dar un paso largo hacia adelante y bajar en línea recta entre "
            "las dos piernas; trabaja cada pierna por separado."
        ),
        "how_to": (
            "1. Da un paso largo hacia adelante con una pierna.\n"
            "2. Baja el cuerpo en línea recta hasta que ambas rodillas formen "
            "~90° (la rodilla de atrás casi toca el piso).\n"
            "3. Mantén el torso erguido y el peso repartido entre ambas piernas.\n"
            "4. Empuja con la pierna de adelante para subir.\n"
            "5. Completa las repeticiones de un lado antes de cambiar."
        ),
        "common_errors": (
            "Rodilla de adelante se adelanta mucho más allá de la punta del pie.\n"
            "Torso inclinado hacia adelante en vez de erguido.\n"
            "Paso demasiado corto (poca amplitud de movimiento).\n"
            "Perder el equilibrio lateral — mirar un punto fijo al frente ayuda."
        ),
        "illustration_ascii": (
            "    o\n"
            "   /|\\\n"
            "   / |\n"
            "  /  |\n"
            " ▲   |\\\n"
            "pie   ▲  <- rodilla trasera casi al piso\n"
            "atrás pie adelante"
        ),
        "illustration_alt": (
            "Figura en posición de zancada con un pie muy adelantado y el "
            "otro atrás, ambas rodillas flexionadas cerca de 90 grados y el "
            "torso erguido."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_unilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "2x8-10 por lado",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 8 ──────────────────────────────────────────────────────────────────
    {
        "slug": "step-up-banco-bajo",
        "name": "Step-up en banco bajo",
        "summary": (
            "Subir a un banco o escalón bajo con una sola pierna, controlando "
            "la bajada; entrena fuerza unilateral funcional."
        ),
        "how_to": (
            "1. Coloca un pie completo sobre un banco o escalón bajo y estable.\n"
            "2. Empuja principalmente con esa pierna (evita impulsarte con la "
            "de atrás) para subir el cuerpo completo.\n"
            "3. Extiende la cadera arriba sin bloquear de golpe la rodilla.\n"
            "4. Baja controlado con la misma pierna, sin dejarte caer.\n"
            "5. Completa las repeticiones de un lado antes de cambiar."
        ),
        "common_errors": (
            "Impulsarse con la pierna de atrás en vez de empujar con la de arriba.\n"
            "Banco demasiado alto para el nivel del deportista.\n"
            "Bajar de golpe sin control.\n"
            "Rodilla de apoyo colapsando hacia adentro."
        ),
        "illustration_ascii": (
            "      o\n"
            "     /|\n"
            "    / |\n"
            " ___▲_|___\n"
            "|  pie   |  <- banco bajo y estable\n"
            "|________|"
        ),
        "illustration_alt": (
            "Figura subiendo un banco bajo apoyando un pie completo encima y "
            "empujando con esa pierna para elevar todo el cuerpo, con la otra "
            "pierna relajada en el aire."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_unilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "2x8-10 por lado",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 9 ──────────────────────────────────────────────────────────────────
    {
        "slug": "flexion-de-brazos-inclinada",
        "name": "Flexión de brazos inclinada (contra banco o pared)",
        "summary": (
            "Flexión de pecho con las manos apoyadas en una superficie "
            "elevada (banco/pared), reduciendo la carga para dominar la técnica."
        ),
        "how_to": (
            "1. Apoya las manos en un banco, baranda o pared, un poco más "
            "abiertas que los hombros.\n"
            "2. Da pasos atrás hasta que el cuerpo quede en línea recta "
            "(cabeza-cadera-talones).\n"
            "3. Flexiona los codos bajando el pecho hacia la superficie, "
            "codos cerca del cuerpo (no abiertos en cruz).\n"
            "4. Empuja para volver a extender los brazos sin perder la línea "
            "recta del cuerpo."
        ),
        "common_errors": (
            "Cadera hundida o muy elevada durante el movimiento.\n"
            "Codos completamente abiertos hacia los lados.\n"
            "Superficie demasiado baja para el nivel actual (aumenta demasiado la carga).\n"
            "Rango de movimiento muy corto."
        ),
        "illustration_ascii": (
            "        ___________\n"
            "       /  banco/pared\n"
            "  o___/\n"
            "  |  /  <- torso recto e inclinado\n"
            " / \\/\n"
            "pies apoyados en el piso"
        ),
        "illustration_alt": (
            "Figura apoyando las manos en un banco o pared, con el cuerpo "
            "inclinado y en línea recta desde la cabeza hasta los talones, "
            "realizando una flexión de brazos con menor carga que en el piso."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "empuje_superior",
        "suggested_duration_min": 5,
        "suggested_reps": "3x8-12",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 10 ─────────────────────────────────────────────────────────────────
    {
        "slug": "remo-invertido-barra-baja",
        "name": "Remo invertido en barra baja",
        "summary": (
            "Colgarse de una barra baja o pasamanos con el cuerpo inclinado y "
            "jalar el pecho hacia la barra; introduce el patrón de tracción "
            "sin necesitar dominadas completas."
        ),
        "how_to": (
            "1. Ubica una barra baja o pasamanos estable a la altura de la cadera.\n"
            "2. Agárrala con las manos al ancho de los hombros y camina los "
            "pies hacia adelante hasta quedar inclinado, cuerpo en línea recta.\n"
            "3. Jala el pecho hacia la barra llevando los codos hacia atrás, "
            "sin balancear el cuerpo.\n"
            "4. Baja controlado hasta extender los brazos.\n"
            "5. Para hacerlo más fácil, camina los pies más cerca de la barra "
            "(cuerpo más vertical)."
        ),
        "common_errors": (
            "Balancear el cuerpo para tomar impulso en vez de jalar con la espalda.\n"
            "Cadera hundida durante el jalón.\n"
            "Barra o pasamanos inestable — verificar firmeza antes de usar.\n"
            "Rango de movimiento incompleto (no llegar a extender los brazos abajo)."
        ),
        "illustration_ascii": (
            "======= <- barra fija baja\n"
            "  ||\n"
            "  o\\\n"
            "   \\ \\\n"
            "    \\ \\   <- cuerpo recto e inclinado\n"
            "     ▲ ▲\n"
            "    pies apoyados en el piso"
        ),
        "illustration_alt": (
            "Figura colgada de una barra baja con el cuerpo inclinado hacia "
            "atrás y los pies apoyados en el piso, jalando el pecho hacia la "
            "barra con los codos hacia atrás."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "traccion_superior",
        "suggested_duration_min": 5,
        "suggested_reps": "3x6-10",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 11 ─────────────────────────────────────────────────────────────────
    {
        "slug": "flexion-de-rodillas-progresiva",
        "name": "Flexión de brazos apoyada en rodillas (progresión)",
        "summary": (
            "Flexión de pecho apoyando rodillas en el piso; progresión hacia "
            "la flexión completa para deportistas de 13-15 con buena base."
        ),
        "how_to": (
            "1. Apoya manos y rodillas en el piso, manos un poco más abiertas "
            "que los hombros.\n"
            "2. Mantén una línea recta entre hombros, cadera y rodillas "
            "(sin doblar por la cintura).\n"
            "3. Flexiona los codos bajando el pecho cerca del piso, codos "
            "cerca del cuerpo.\n"
            "4. Empuja para extender los brazos sin perder la línea recta.\n"
            "5. Cuando domines 3x12 con buena técnica, progresa a la flexión "
            "de brazos completa (piernas extendidas)."
        ),
        "common_errors": (
            "Doblar la cadera hacia arriba o hacia abajo en el punto de apoyo de rodillas.\n"
            "Codos completamente abiertos en cruz.\n"
            "Bajar solo un poco (rango incompleto).\n"
            "Progresar a la versión completa antes de dominar la técnica aquí."
        ),
        "illustration_ascii": (
            "  o___\n"
            "  |   \\\n"
            "  |    \\  <- torso recto, apoyo en rodillas\n"
            " _|_    \\\n"
            "manos   rodilla apoyada"
        ),
        "illustration_alt": (
            "Figura apoyada en manos y rodillas realizando una flexión de "
            "brazos, con el torso en línea recta desde los hombros hasta las "
            "rodillas."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "empuje_superior",
        "suggested_duration_min": 5,
        "suggested_reps": "3x10-12",
        "age_bands": ["13-15"],
    },
    # ── 12 ─────────────────────────────────────────────────────────────────
    {
        "slug": "mountain-climber-plancha-dinamica",
        "name": "Escalador (mountain climber) en plancha",
        "summary": (
            "Desde posición de plancha, llevar rodillas al pecho alternando "
            "rápido; combina core y control de ritmo respiratorio."
        ),
        "how_to": (
            "1. Toma la posición de plancha alta (manos bajo hombros, cuerpo recto).\n"
            "2. Lleva una rodilla hacia el pecho manteniendo la cadera estable.\n"
            "3. Regresa esa pierna y repite con la contraria, alternando con "
            "ritmo controlado.\n"
            "4. Mantén los hombros quietos sobre las manos durante todo el movimiento.\n"
            "5. Ajusta la velocidad al nivel: primero técnica lenta, luego más rápido."
        ),
        "common_errors": (
            "Cadera subiendo demasiado alto (se pierde la posición de plancha).\n"
            "Ir tan rápido que se pierde el control de la técnica.\n"
            "Hombros balanceándose de lado a lado.\n"
            "Contener la respiración en vez de mantener un ritmo constante."
        ),
        "illustration_ascii": (
            "   o\n"
            " /===\\\n"
            "  |  \\\\\n"
            "  |   \\\\__  <- rodilla llevada al pecho\n"
            " manos  pie que avanza"
        ),
        "illustration_alt": (
            "Figura en posición de plancha alta llevando una rodilla hacia el "
            "pecho de forma alternada, manteniendo los hombros estables sobre "
            "las manos."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 4,
        "suggested_reps": "3x20-30 seg",
        "age_bands": ["13-15"],
    },
    # ── 13 ─────────────────────────────────────────────────────────────────
    {
        "slug": "superman-remo",
        "name": "Superman con remo",
        "summary": (
            "Acostado boca abajo, levantar pecho y piernas y simular un jalón "
            "de remo; activa toda la cadena posterior sin equipo."
        ),
        "how_to": (
            "1. Acuéstate boca abajo, brazos extendidos al frente, piernas "
            "extendidas y juntas.\n"
            "2. Levanta pecho, brazos y piernas del piso al mismo tiempo, "
            "mirando hacia abajo (cuello neutro).\n"
            "3. Desde arriba, flexiona los codos llevándolos hacia atrás "
            "como si remaras (jalón de remo).\n"
            "4. Regresa los brazos al frente y baja controlado.\n"
            "5. Mantén el movimiento lento y controlado, sin usar impulso."
        ),
        "common_errors": (
            "Levantar el cuello en vez de mantenerlo neutro (mirar el piso).\n"
            "Usar impulso/rebote en vez de control muscular.\n"
            "Piernas quedándose en el piso mientras solo sube el torso.\n"
            "Rango de movimiento del remo muy pequeño."
        ),
        "illustration_ascii": (
            "  \\o/    <- brazos y piernas elevados\n"
            "   |\n"
            "  /=\\\n"
            " /   \\   <- solo el abdomen toca el piso\n"
            "‾‾‾‾‾‾‾‾"
        ),
        "illustration_alt": (
            "Figura acostada boca abajo con brazos y piernas elevados del "
            "piso simultáneamente, flexionando los codos hacia atrás como si "
            "remara."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "traccion_superior",
        "suggested_duration_min": 4,
        "suggested_reps": "3x10-12",
        "age_bands": ["10-12"],
    },
    # ── 14 ─────────────────────────────────────────────────────────────────
    {
        "slug": "sentadilla-goblet-mancuerna-ligera",
        "name": "Sentadilla goblet con mancuerna ligera",
        "summary": (
            "Sentadilla sosteniendo una mancuerna ligera contra el pecho; el "
            "peso al frente ayuda a mantener el torso erguido."
        ),
        "how_to": (
            "1. Sostén una mancuerna ligera verticalmente contra el pecho con "
            "ambas manos.\n"
            "2. Pies al ancho de los hombros, puntas ligeramente hacia afuera.\n"
            "3. Baja la cadera hacia atrás y abajo manteniendo el pecho "
            "arriba y los codos apuntando al piso.\n"
            "4. Baja hasta donde la técnica se mantenga sólida (idealmente "
            "muslos paralelos al piso).\n"
            "5. Empuja el piso con toda la planta del pie para subir."
        ),
        "common_errors": (
            "Rodillas colapsando hacia adentro.\n"
            "Mancuerna alejándose del pecho (pierde el efecto de contrapeso).\n"
            "Espalda redondeada en vez de pecho arriba.\n"
            "Elegir un peso demasiado alto para la técnica actual."
        ),
        "illustration_ascii": (
            "   o\n"
            "  /█\\   <- mancuerna sostenida contra el pecho\n"
            "  | |\n"
            " _| |_  <- cadera baja, rodillas sobre pies\n"
            "en sentadilla"
        ),
        "illustration_alt": (
            "Figura en posición de sentadilla sosteniendo una mancuerna "
            "ligera verticalmente contra el pecho con ambas manos, codos "
            "apuntando hacia el piso."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "mancuerna ligera",
        "movement_category": "inferior_bilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "3x8-15",
        "age_bands": ["13-15"],
    },
    # ── 15 ─────────────────────────────────────────────────────────────────
    {
        "slug": "zancada-con-mancuernas-ligeras",
        "name": "Zancada con mancuernas ligeras",
        "summary": (
            "Zancada estática sosteniendo una mancuerna ligera en cada mano; "
            "añade carga controlada al patrón unilateral."
        ),
        "how_to": (
            "1. Sostén una mancuerna ligera en cada mano, brazos relajados a "
            "los lados.\n"
            "2. Da un paso largo hacia adelante con una pierna.\n"
            "3. Baja el cuerpo en línea recta hasta que ambas rodillas formen "
            "~90° (la rodilla de atrás casi toca el piso).\n"
            "4. Mantén el torso erguido durante todo el movimiento.\n"
            "5. Empuja con la pierna de adelante para subir; completa las "
            "repeticiones de un lado antes de cambiar."
        ),
        "common_errors": (
            "Rodilla de adelante se adelanta mucho más allá de la punta del pie.\n"
            "Torso inclinado hacia adelante por el peso de las mancuernas.\n"
            "Elegir un peso que haga perder el equilibrio.\n"
            "Paso demasiado corto."
        ),
        "illustration_ascii": (
            "   o\n"
            " █/|\\█  <- mancuernas a los lados\n"
            "  / |\n"
            " /  |\n"
            "▲   |\\\n"
            "pie  ▲  <- rodilla trasera casi al piso\n"
            "atrás pie adelante"
        ),
        "illustration_alt": (
            "Figura en posición de zancada sosteniendo una mancuerna ligera "
            "en cada mano a los lados del cuerpo, ambas rodillas flexionadas "
            "cerca de 90 grados."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "mancuernas ligeras",
        "movement_category": "inferior_unilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "3x8-12 por lado",
        "age_bands": ["13-15"],
    },
    # ── 16 ─────────────────────────────────────────────────────────────────
    {
        "slug": "press-de-hombro-con-mancuernas",
        "name": "Press de hombro con mancuernas ligeras",
        "summary": (
            "Empujar dos mancuernas ligeras desde los hombros hacia arriba; "
            "introduce el patrón de empuje vertical con carga controlada."
        ),
        "how_to": (
            "1. Siéntate o párate con buena postura, mancuernas ligeras a "
            "la altura de los hombros, palmas al frente.\n"
            "2. Empuja las mancuernas hacia arriba hasta casi extender los "
            "codos, sin arquear la espalda baja.\n"
            "3. Baja controlado hasta que las mancuernas vuelvan a la altura "
            "de los hombros.\n"
            "4. Mantén el abdomen activo durante todo el recorrido.\n"
            "5. Usa el peso más liviano posible mientras se aprende la técnica."
        ),
        "common_errors": (
            "Arquear la espalda baja para ayudar a empujar el peso.\n"
            "Bloquear los codos de golpe arriba.\n"
            "Elegir un peso demasiado alto para la técnica actual.\n"
            "Bajar las mancuernas más allá de la línea de los hombros sin control."
        ),
        "illustration_ascii": (
            "  █   █   <- mancuernas arriba, brazos casi extendidos\n"
            "   \\ /\n"
            "    o\n"
            "   /=\\\n"
            "   | |    <- torso erguido, abdomen activo"
        ),
        "illustration_alt": (
            "Figura sentada o de pie empujando una mancuerna ligera con cada "
            "mano desde la altura de los hombros hacia arriba, manteniendo "
            "el torso erguido."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "mancuernas ligeras",
        "movement_category": "empuje_superior",
        "suggested_duration_min": 5,
        "suggested_reps": "3x8-12",
        "age_bands": ["13-15"],
    },
    # ── 17 ─────────────────────────────────────────────────────────────────
    {
        "slug": "remo-con-banda-elastica",
        "name": "Remo sentado con banda elástica",
        "summary": (
            "Sentado con las piernas extendidas, jalar una banda elástica "
            "anclada al frente llevando los codos atrás; patrón de tracción "
            "horizontal con resistencia progresiva."
        ),
        "how_to": (
            "1. Siéntate con las piernas extendidas, banda elástica anclada "
            "frente a los pies o a un punto fijo estable.\n"
            "2. Sostén los extremos de la banda con los brazos extendidos "
            "al frente, torso erguido.\n"
            "3. Jala la banda llevando los codos hacia atrás, juntando los "
            "omóplatos, sin mover el torso hacia atrás.\n"
            "4. Regresa controlado hasta extender los brazos de nuevo.\n"
            "5. Mantén la espalda recta durante todo el movimiento."
        ),
        "common_errors": (
            "Balancear el torso hacia atrás para ayudar a jalar.\n"
            "Encoger los hombros hacia las orejas en vez de juntar omóplatos.\n"
            "Anclaje de la banda inestable — verificar firmeza antes de usar.\n"
            "Rango de movimiento incompleto."
        ),
        "illustration_ascii": (
            "≈≈≈≈●  <- banda anclada al frente\n"
            "     \\\n"
            "      o\n"
            "     /=\\   <- torso erguido, codos hacia atrás\n"
            "    /   \\"
        ),
        "illustration_alt": (
            "Figura sentada con las piernas extendidas, jalando una banda "
            "elástica anclada al frente, llevando los codos hacia atrás y "
            "juntando los omóplatos."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "banda elástica",
        "movement_category": "traccion_superior",
        "suggested_duration_min": 5,
        "suggested_reps": "3x10-15",
        "age_bands": ["13-15"],
    },
    # ── 18 ─────────────────────────────────────────────────────────────────
    {
        "slug": "plancha-anti-rotacion-con-banda",
        "name": "Plancha con anti-rotación (banda elástica)",
        "summary": (
            "En plancha alta, jalar una banda elástica anclada al lado sin "
            "dejar que el torso rote; entrena el core para resistir fuerzas "
            "laterales."
        ),
        "how_to": (
            "1. Ancla una banda elástica a un punto fijo a la altura del pecho.\n"
            "2. Toma la posición de plancha alta, de lado al anclaje, "
            "sosteniendo la banda con la mano más alejada.\n"
            "3. Jala la banda hacia el pecho sin dejar que el torso rote "
            "hacia el anclaje.\n"
            "4. Regresa controlado a la posición extendida.\n"
            "5. Completa las repeticiones de un lado antes de cambiar."
        ),
        "common_errors": (
            "Dejar que el torso rote hacia el anclaje (pierde el objetivo del ejercicio).\n"
            "Cadera hundida o elevada durante el movimiento.\n"
            "Anclaje de la banda inestable.\n"
            "Elegir una banda con demasiada resistencia para el nivel actual."
        ),
        "illustration_ascii": (
            "≈≈≈≈●\n"
            "     \\\n"
            "  o___\\\n"
            " /=====\\  <- plancha alta, torso sin rotar\n"
            "▲       ▲\n"
            "manos apoyadas"
        ),
        "illustration_alt": (
            "Figura en posición de plancha alta jalando una banda elástica "
            "anclada al lado con una mano, manteniendo el torso firme y sin "
            "rotar hacia el anclaje."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "banda elástica",
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 5,
        "suggested_reps": "3x8-10 por lado",
        "age_bands": ["13-15"],
    },
    # ── 19 ─────────────────────────────────────────────────────────────────
    {
        "slug": "pull-apart-con-banda-elastica",
        "name": "Pull-apart con banda elástica",
        "summary": (
            "Sostener una banda elástica con ambos brazos extendidos al "
            "frente y separarla llevándola al pecho; fortalece la espalda "
            "alta y mejora la postura."
        ),
        "how_to": (
            "1. Sostén una banda elástica con ambas manos, brazos extendidos "
            "al frente a la altura de los hombros.\n"
            "2. Separa las manos estirando la banda hacia los lados, llevando "
            "la banda hacia el pecho.\n"
            "3. Junta los omóplatos al final del movimiento, sin encoger los "
            "hombros hacia las orejas.\n"
            "4. Regresa controlado a la posición inicial.\n"
            "5. Mantén los brazos casi extendidos durante todo el recorrido."
        ),
        "common_errors": (
            "Encoger los hombros hacia las orejas en vez de juntar omóplatos.\n"
            "Doblar demasiado los codos (pierde el enfoque en la espalda alta).\n"
            "Ir demasiado rápido, sin control en el regreso.\n"
            "Elegir una banda con demasiada resistencia para el nivel actual."
        ),
        "illustration_ascii": (
            "  ●≈≈≈    ≈≈≈●   <- banda separada hacia los lados\n"
            "     \\    /\n"
            "      \\  /\n"
            "       o\n"
            "      /=\\   <- torso erguido"
        ),
        "illustration_alt": (
            "Figura de pie sosteniendo una banda elástica con ambos brazos "
            "extendidos al frente, separando las manos hacia los lados hasta "
            "llevar la banda cerca del pecho."
        ),
        "equipment": "equipo_gym",
        "equipment_detail": "banda elástica",
        "movement_category": "traccion_superior",
        "suggested_duration_min": 4,
        "suggested_reps": "3x12-15",
        "age_bands": ["13-15"],
    },
    # ── 20 ─────────────────────────────────────────────────────────────────
    {
        "slug": "sentadilla-sumo-peso-corporal",
        "name": "Sentadilla sumo con peso corporal",
        "summary": (
            "Sentadilla con los pies más separados y puntas hacia afuera; "
            "enfatiza cadera y muslo interno con el propio peso."
        ),
        "how_to": (
            "1. Coloca los pies más separados que el ancho de los hombros, "
            "puntas rotadas hacia afuera.\n"
            "2. Baja la cadera manteniendo las rodillas en la misma dirección "
            "de los pies, pecho arriba.\n"
            "3. Baja hasta donde la técnica se mantenga sólida.\n"
            "4. Empuja el piso con toda la planta del pie para subir.\n"
            "5. Mantén el torso erguido durante todo el movimiento."
        ),
        "common_errors": (
            "Rodillas colapsando hacia adentro en vez de seguir la dirección de los pies.\n"
            "Puntas de los pies rotadas en exceso o muy poco.\n"
            "Espalda redondeada en vez de pecho arriba.\n"
            "Rango de movimiento incompleto."
        ),
        "illustration_ascii": (
            "     o\n"
            "    /=\\\n"
            "   /   \\\n"
            "  ▲     ▲   <- pies separados, puntas hacia afuera\n"
            " /       \\"
        ),
        "illustration_alt": (
            "Figura en posición de sentadilla con los pies bien separados y "
            "las puntas rotadas hacia afuera, rodillas alineadas con la "
            "dirección de los pies."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_bilateral",
        "suggested_duration_min": 5,
        "suggested_reps": "3x10-15",
        "age_bands": ["13-15"],
    },
    # ── 21 ─────────────────────────────────────────────────────────────────
    {
        "slug": "elevacion-de-cadera-a-una-pierna",
        "name": "Elevación de cadera a una pierna",
        "summary": (
            "Puente de glúteo apoyado en una sola pierna; añade exigencia "
            "unilateral al mismo patrón de cadera."
        ),
        "how_to": (
            "1. Acuéstate boca arriba, una rodilla doblada con el pie "
            "apoyado, la otra pierna extendida y elevada.\n"
            "2. Aprieta el glúteo de la pierna de apoyo y empuja el talón "
            "para levantar la cadera.\n"
            "3. Sube hasta formar una línea recta entre rodilla, cadera y "
            "hombro, sin arquear de más la lumbar.\n"
            "4. Sostén 1-2 segundos arriba.\n"
            "5. Baja controlado; completa las repeticiones de un lado antes "
            "de cambiar."
        ),
        "common_errors": (
            "Cadera rotando o cayendo hacia el lado de la pierna elevada.\n"
            "Arquear demasiado la zona lumbar.\n"
            "Empujar con la espalda en vez de con el glúteo de apoyo.\n"
            "Pierna elevada muy baja (dificulta mantener el equilibrio de cadera)."
        ),
        "illustration_ascii": (
            "        ___\n"
            "       /   \\  <- cadera elevada, una pierna extendida arriba\n"
            "  o___/     \\\n"
            "  hombro    pie apoyado (una sola pierna)"
        ),
        "illustration_alt": (
            "Figura acostada boca arriba con una rodilla doblada y el pie "
            "apoyado en el piso, la otra pierna extendida en el aire, "
            "levantando la cadera apoyada solo en una pierna."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "inferior_unilateral",
        "suggested_duration_min": 4,
        "suggested_reps": "2x8-10 por lado",
        "age_bands": ["10-12", "13-15"],
    },
    # ── 22 ─────────────────────────────────────────────────────────────────
    {
        "slug": "plancha-con-toque-de-hombro",
        "name": "Plancha con toque de hombro",
        "summary": (
            "Desde plancha alta, tocar el hombro contrario con una mano "
            "alternando, sin balancear la cadera; desafía la anti-rotación "
            "del core."
        ),
        "how_to": (
            "1. Toma la posición de plancha alta, manos bajo los hombros, "
            "pies un poco más separados que el ancho de la cadera para "
            "mayor estabilidad.\n"
            "2. Levanta una mano y toca el hombro contrario.\n"
            "3. Regresa la mano al piso sin que la cadera se balancee de "
            "lado a lado.\n"
            "4. Alterna con la mano contraria, manteniendo el ritmo controlado.\n"
            "5. Si la cadera balancea mucho, separa más los pies o reduce la "
            "velocidad."
        ),
        "common_errors": (
            "Cadera balanceándose de lado a lado con cada toque.\n"
            "Ir demasiado rápido, sacrificando el control.\n"
            "Pies muy juntos (menos base de apoyo, más inestabilidad).\n"
            "Cabeza colgando en vez de mirar el piso con cuello neutro."
        ),
        "illustration_ascii": (
            "   o\n"
            " /=|=\\   <- una mano toca el hombro contrario\n"
            "  \\|/\n"
            " __|__\n"
            "▲     ▲  <- pies separados, base estable"
        ),
        "illustration_alt": (
            "Figura en posición de plancha alta tocando el hombro contrario "
            "con una mano de forma alternada, manteniendo la cadera estable "
            "y sin balanceo."
        ),
        "equipment": "sin_equipo",
        "equipment_detail": None,
        "movement_category": "core_estabilidad",
        "suggested_duration_min": 4,
        "suggested_reps": "3x16-20 toques",
        "age_bands": ["13-15"],
    },
]
