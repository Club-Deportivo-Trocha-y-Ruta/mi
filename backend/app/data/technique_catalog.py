"""
Seed payload for the Technique & Gymkhana Library (Feature 018).

Source: docs/14-tecnica-gymkana-7-15/research.md
  § 2  — Skill taxonomy A–H (SKILLS)
  § 3  — Materiales base + 24-exercise bank (MATERIALS, EXERCISES)
  § 4  — Gymkhana circuit croquis (layout_ascii / layout_alt on gymkhana exercises)

All Spanish copy is verbatim (español neutro) from the source document.
This is a pure-data module: no DB imports, no side-effects.
Consumed by the idempotent Alembic data migration (D3, research.md).
"""

# ---------------------------------------------------------------------------
# LEYENDA — §4 shared legend block (referenced by circuit alt-texts)
# ---------------------------------------------------------------------------

LAYOUT_LEGEND = """\
LEYENDA
 ▲ cono          ◎ llanta tendida      O llanta de pie
 ▮ estaca        ═ tope/bordillo o tablón
 ┅ línea (tiza/cuerda)   ✕ "mina" (botella/balón/piña)
 ⊓ limbo (cuerda/palo sobre 2 estacas)
 🚩 salida/meta   →  sentido de avance"""

# ---------------------------------------------------------------------------
# Named circuit blocks — §4.1 / 4.2 / 4.3
# Used as layout_ascii for gymkhana exercises that belong to a circuit.
# ---------------------------------------------------------------------------

LAYOUT_41 = """\
   🚩 SALIDA
    │
    ▼
 [E1] PASILLO ANCHO→ANGOSTO            [E2] OCHOS
  ┅┅┅┅┅┅┅┅┅┅┅┅                          ▲       ▲
  →  →  →  →  →  →                       ↺  ∞   ↻
  ┅┅┅┅┅┅┅┅┅┅┅┅                          ▲       ▲
   (mira al final)                     (mira la salida)
        │                                    ▲
        └──────────────►─────────────────────┘
                                             │
 [E4] FRENADO EN ZONA          ◄──────────── [E3] SLALOM SUAVE
   ▲      ▲                                  ▲   ▲   ▲   ▲
   │ caja │  ⟵ detente aquí                   ╲ ╱ ╲ ╱ ╲ ╱
   ▲      ▲                                   ▲   ▲   ▲
  (peso atrás, 1 dedo)                    (conos separados, suave)"""

LAYOUT_42 = """\
🚩 ──► ▲ ╲   ╱ ▲ ╲   ╱ ▲        SLALOM (separación media)
          ╲ ╱     ╲ ╱
           ▲       ▲
                                ↓
        ⊓  LIMBO en bici  ▮━━━━━━▮   (sepa. cuerpo-bici)
                                ↓
        ✕    ✕    ✕             CAMPO MINADO
           ✕    ✕    ✕          (mira los huecos)
        ✕    ✕    ✕
                                ↓
        ◎   ◎   ◎               ESCALERA DE LLANTAS
                                ↓
        cono ▲ · · · 🌀 tubo     TIRO AL ARO (al pasar)
                                ↓
        ▲══════▲   CAJA DE FRENO ── detente dentro ── 🏁 META"""

LAYOUT_43 = """\
🚩
 │   SLALOM APRETADO            FRENADO + GIRO 180°
 ▼   ▲ ▲ ▲ ▲ ▲                  ▲═════▲
     ╲╱╲╱╲╱╲╱      ───────►      caja│ ↺ giro cerrado
     ▲ ▲ ▲ ▲                        ▲
                                     │
        ESQUIVA LA ROCA              ▼
        ─── recto ───► ═ ◄ golpe   SUBIR/BAJAR TOPE (drop)
              de manillar           ═══════ ↓ peso atrás
                                     │
        BUNNY HOP                    ▼
        ▮━━━━━━▮  ⟵ salta ambas    PUMP / ONDULACIONES
                                    ∿∿∿∿∿  (sin pedalear)
                                     │
                                     ▼  🏁 META (toma tiempo personal)"""

# ---------------------------------------------------------------------------
# SKILLS — §2 "Tabla de habilidades del club"
# sort_order follows the A–H progression order in the research document.
# ---------------------------------------------------------------------------

SKILLS: list[dict] = [
    {
        "code": "A",
        "name": "Posición neutra/lista y equilibrio",
        "focus": "Postura atlética, peso centrado, trackstand",
        "slug": "posicion",
        "sort_order": 1,
    },
    {
        "code": "B",
        "name": "Mirada / visión",
        "focus": "Mirar lejos y donde sí quiero ir",
        "slug": "vision",
        "sort_order": 2,
    },
    {
        "code": "C",
        "name": "Frenado modulado",
        "focus": "1 dedo por freno, peso atrás, dosificar",
        "slug": "frenado",
        "sort_order": 3,
    },
    {
        "code": "D",
        "name": "Control a baja velocidad",
        "focus": "Maniobrar lento sin pie al suelo",
        "slug": "control_baja_velocidad",
        "sort_order": 4,
    },
    {
        "code": "E",
        "name": "Trazado de curvas",
        "focus": "Mirar la salida, inclinar bici, pedales",
        "slug": "curvas",
        "sort_order": 5,
    },
    {
        "code": "F",
        "name": "Separación cuerpo-bici",
        "focus": "Levantar rueda, manual, bunny hop",
        "slug": "separacion",
        "sort_order": 6,
    },
    {
        "code": "G",
        "name": "Control de presión / terreno",
        "focus": "Pump, raíces/rocas, drops",
        "slug": "presion_terreno",
        "sort_order": 7,
    },
    {
        "code": "H",
        "name": "Cambios y cadencia",
        "focus": "Engranar antes de la subida (cad. ≥70)",
        "slug": "cambios_cadencia",
        "sort_order": 8,
    },
]

# ---------------------------------------------------------------------------
# MATERIALS — §3 "Materiales base" + §3 table material column
# is_none=True marks the sentinel "sin material" entry.
# ---------------------------------------------------------------------------

MATERIALS: list[dict] = [
    {"slug": "conos",        "name": "Conos",                       "is_none": False},
    {"slug": "llantas",      "name": "Llantas / neumáticos viejos", "is_none": False},
    {"slug": "estacas",      "name": "Estacas",                     "is_none": False},
    {"slug": "topes",        "name": "Topes / bordillos / rampas",  "is_none": False},
    {"slug": "tablones",     "name": "Tablones / palés",            "is_none": False},
    {"slug": "botellas",     "name": "Botellas plásticas (con arena)", "is_none": False},
    {"slug": "cuerda",       "name": "Cuerda / palo de escoba / guadua", "is_none": False},
    {"slug": "tiza",         "name": "Tiza",                        "is_none": False},
    {"slug": "balones",      "name": "Balones pequeños",            "is_none": False},
    {"slug": "ramas",        "name": "Ramas",                       "is_none": False},
    {"slug": "sendero",      "name": "Sendero natural",             "is_none": False},
    {"slug": "pump_track",   "name": "Pump track / rollers de tierra", "is_none": False},
    {"slug": "pendiente",    "name": "Pendiente / subida corta",    "is_none": False},
    {"slug": "sin_material", "name": "Sin material",                "is_none": True},
]

# ---------------------------------------------------------------------------
# EXERCISES — §3 table, all 24 rows
#
# Field notes:
#   difficulty   : "facil" ①, "media" ②, "avanzada" ③
#                  for ranges (①→③) the dominant / entry level is used.
#   is_game      : True when the source marks 🎉
#   is_gymkhana  : True when the exercise fits into a circuit layout
#                  (appears inside §4 croquis or requires a spatial setup)
#   age_bands    : lists from "Edad" column mapped to ["7-9","10-12","13-15"]
#                  "7-15" → all three; "7-12" → ["7-9","10-12"];
#                  "9-15" → ["10-12","13-15"] (9 overlaps 7-9 but the band
#                  starts at 7; closest fit is 10-12 lower bound → both
#                  10-12 and 13-15; 7-9 excluded because 9 is the boundary
#                  and the exercise needs developmental readiness)
#                  "10-15" → ["10-12","13-15"]
#                  "11-15" → ["10-12","13-15"]
#                  "13-15" → ["13-15"]
#                  "7-13"  → ["7-9","10-12"]
#                  "8-13"  → ["7-9","10-12"]
#                  "8-15"  → all three
#   skill_codes  : letters from "Habilidad" column, order preserved
#   material_slugs: mapped from "Material" column
#   layout_ascii : verbatim §4 croquis block for gymkhana exercises; None otherwise
#   layout_alt   : plain-language Spanish placement description for screen readers
# ---------------------------------------------------------------------------

EXERCISES: list[dict] = [
    # ── 1 ──────────────────────────────────────────────────────────────────
    {
        "slug": "pie-abajo-circulo-de-la-muerte",
        "name": "Pie abajo / Círculo de la muerte",
        "summary": (
            "Todos pedalean lento dentro de un círculo de conos; quien apoya el pie "
            "o sale queda eliminado. El círculo se encoge por rondas."
        ),
        "how_to": (
            "Dilo: 'El objetivo es mantenerse dentro del círculo sin poner el pie. "
            "Si lo pones o sales, sales del juego.'\n"
            "Muéstralo: el entrenador rueda lento dentro del área y demuestra cómo "
            "ajustar el equilibrio inclinando el cuerpo y usando el freno suavemente.\n"
            "Háganlo: todos inician. Tras cada ronda de eliminaciones, reduce el radio "
            "del círculo ~1 m. Los eliminados esperan la siguiente ronda o hacen "
            "equilibrio estático fuera.\n"
            "Revísenlo: '¿Qué hiciste para quedarte más tiempo? ¿Cuándo sentiste que "
            "ibas a caer?'\n"
            "Clima de maestría: celebra el tiempo que cada uno aguantó respecto a su "
            "marca anterior, no quién ganó."
        ),
        "difficulty": "facil",
        "is_game": True,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡 [6]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["A", "D"],
        "material_slugs": ["conos"],
    },
    # ── 2 ──────────────────────────────────────────────────────────────────
    {
        "slug": "carrera-de-lentitud",
        "name": "Carrera de lentitud",
        "summary": (
            "El último en cruzar la línea gana, sin apoyar el pie. "
            "Progresa a trackstand (parado)."
        ),
        "how_to": (
            "Dilo: 'Aquí gana el más lento. Nadie puede poner el pie; si lo hace, "
            "queda eliminado. El carril lo delimitan dos conos o líneas de tiza.'\n"
            "Muéstralo: el entrenador recorre el carril al paso más lento posible, "
            "mostrando microajustes de manillar y uso del freno trasero.\n"
            "Háganlo: carreras de 4-5 m de ancho por 8-10 m de largo. Primero libre, "
            "luego reduce el ancho. Variante avanzada: zone donde si te detienes "
            "completamente debes hacer trackstand durante 3 s antes de seguir.\n"
            "Revísenlo: '¿Dónde miraban cuando iban más lentos? ¿Qué parte del "
            "freno usaban más?'\n"
            "Clima de maestría: anota el tiempo de cada uno y rétalo a batir su propio "
            "récord de lentitud en la siguiente sesión."
        ),
        "difficulty": "facil",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡⚪ [6][13]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["A", "D"],
        "material_slugs": ["tiza", "conos"],
    },
    # ── 3 ──────────────────────────────────────────────────────────────────
    {
        "slug": "semaforo",
        "name": "Semáforo (rojo/verde)",
        "summary": (
            "Verde avanza, rojo frena en seco y se queda parado. "
            "Entrena frenado de emergencia y atención auditiva."
        ),
        "how_to": (
            "Dilo: 'Cuando digo VERDE, pedalean; cuando digo ROJO, frenan y se quedan "
            "totalmente parados. Sin poner el pie si pueden.'\n"
            "Muéstralo: el entrenador rueda y frena en seco al escuchar ROJO, "
            "mostrando el peso hacia atrás y los dos dedos sobre los frenos.\n"
            "Háganlo: empieza con cambios lentos entre verde y rojo. Aumenta la "
            "velocidad base o acorta el tiempo entre señales. Variante: agrega "
            "AMARILLO = rueda muy lento.\n"
            "Revísenlo: '¿Cuándo sentiste que te ibas a pasar? ¿Qué hiciste con el "
            "cuerpo al frenar?'\n"
            "Clima de maestría: sin pulsómetro ni cronómetro; el disfrute y la "
            "reacción rápida son el logro."
        ),
        "difficulty": "facil",
        "is_game": True,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡 [6]",
        "age_bands": ["7-9", "10-12"],
        "skill_codes": ["A", "C"],
        "material_slugs": ["sin_material"],
    },
    # ── 4 ──────────────────────────────────────────────────────────────────
    {
        "slug": "campo-minado",
        "name": "Campo minado",
        "summary": (
            "Cruzar una zona llena de 'minas' (botellas/balones/piñas) sin tocarlas, "
            "mirando los huecos (donde sí quiero ir), no los obstáculos."
        ),
        "how_to": (
            "Dilo: 'El campo tiene minas. Tu trabajo es mirar los HUECOS — por dónde "
            "sí puedes pasar — no las minas. Si miras la mina, tu bici va hacia ella.'\n"
            "Muéstralo: el entrenador atraviesa lento señalando con la cabeza hacia "
            "los espacios libres, no hacia los objetos.\n"
            "Háganlo: siembra las minas en campo abierto (~5×5 m); primero pocas y "
            "separadas, luego más densas. Variante: recorrido slalom entre grupos de "
            "minas. Para 13-15: añade velocidad y una variación de las posiciones de "
            "minas entre turnos.\n"
            "Revísenlo: '¿Tocaron más minas cuando las miraban o cuando miraban el "
            "hueco?'\n"
            "Clima de maestría: cuenta las minas tocadas; el reto es mejorar el número "
            "propio, no competir con el compañero."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_42,
        "layout_alt": (
            "Zona rectangular con botellas, balones o piñas dispersas como obstáculos "
            "(minas). Las minas se distribuyen en filas alternadas dejando huecos de "
            "paso entre ellas. El ciclista entra por un extremo y debe cruzar hasta el "
            "otro evitando todos los objetos, mirando siempre los espacios libres. "
            "Este ejercicio aparece como estación 'CAMPO MINADO' dentro de la Gymkana "
            "de Habilidad 10-12 (circuito 4.2)."
        ),
        "confidence": "🟡 [6][7]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["B", "D"],
        "material_slugs": ["botellas", "balones", "ramas"],
    },
    # ── 5 ──────────────────────────────────────────────────────────────────
    {
        "slug": "limbo-en-bici",
        "name": "Limbo en bici",
        "summary": (
            "Pasar agachado bajo una barra (cuerda/palo/guadua) sin tocarla; "
            "entrena separación cuerpo-bici. La barra baja por rondas."
        ),
        "how_to": (
            "Dilo: 'Deben pasar bajo la barra sin tocarla ni con el cuerpo ni con "
            "el casco. La bici puede pasar; ustedes deben agacharse y separar el "
            "cuerpo de la bici.'\n"
            "Muéstralo: el entrenador pasa lento mostrando cómo bajar el centro de "
            "gravedad, empujar la bici hacia delante con los brazos y mantener los "
            "pedales nivelados.\n"
            "Háganlo: empieza con la barra alta (hombros); bájala ~10 cm cada ronda. "
            "Para quienes no pasan: invítalos a intentar solo con el manillar por "
            "debajo mientras caminan la bici. Variante avanzada: limbo en movimiento "
            "rápido o encadenado con slalom.\n"
            "Revísenlo: '¿Qué parte del cuerpo les costó más separar de la bici?'\n"
            "Clima de maestría: premia el intento y la mejora de altura lograda, "
            "no quién pasa más bajo desde el inicio."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_42,
        "layout_alt": (
            "Dos estacas clavadas o sujetas en el suelo a ambos lados del carril, "
            "separadas aproximadamente 2 metros. Una cuerda, palo de escoba o caña de "
            "guadua se apoya horizontalmente sobre las estacas a la altura ajustable. "
            "El ciclista se aproxima en línea recta, se agacha para separar el cuerpo "
            "de la bici y pasa bajo la barra sin tocarla. Este ejercicio aparece como "
            "estación 'LIMBO en bici' dentro de la Gymkana de Habilidad 10-12 "
            "(circuito 4.2)."
        ),
        "confidence": "🟡 [6]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F"],
        "material_slugs": ["cuerda", "estacas"],
    },
    # ── 6 ──────────────────────────────────────────────────────────────────
    {
        "slug": "tiro-al-aro",
        "name": "Tiro al aro",
        "summary": (
            "Lanzar un tubo/llanta vieja sobre un cono mientras se rueda al lado; "
            "puede usarse como relevo por equipos."
        ),
        "how_to": (
            "Dilo: 'Rodan al lado del cono y, sin detenerse, lanzan el tubo para que "
            "caiga encima. No importa la velocidad: importa la puntería y el control.'\n"
            "Muéstralo: el entrenador rueda lentamente al costado del cono, suelta una "
            "mano, y lanza el tubo con arco corto hacia el cono.\n"
            "Háganlo: primero de pie o caminando la bici para sentir el lanzamiento; "
            "luego rodando. Aumenta la velocidad o aleja el cono para más dificultad. "
            "Variante relevo: equipos de 3; cada uno lanza y regresa; gana el primero "
            "en anotar 3 aros.\n"
            "Revísenlo: '¿Cuándo fue más fácil apuntar: rápido o lento?'\n"
            "Clima de maestría: cada equipo intenta mejorar su marca colectiva de aros "
            "en un tiempo fijo."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_42,
        "layout_alt": (
            "Un cono se coloca en el suelo. A unos 2-3 metros de distancia lateral se "
            "traza una línea de paso (con tiza o imaginaria). El ciclista rueda en "
            "paralelo al cono, y al pasar a su lado lanza un tubo o llanta pequeña "
            "intentando encajarla sobre el cono. Este ejercicio aparece como estación "
            "'TIRO AL ARO' dentro de la Gymkana de Habilidad 10-12 (circuito 4.2)."
        ),
        "confidence": "🟡 [6]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F", "B"],
        "material_slugs": ["llantas", "conos"],
    },
    # ── 7 ──────────────────────────────────────────────────────────────────
    {
        "slug": "slalom-de-conos",
        "name": "Slalom de conos",
        "summary": (
            "Zigzag entre conos; acerca los conos y sube velocidad para más dificultad. "
            "Base del slalom dual (dos carriles, carrera)."
        ),
        "how_to": (
            "Dilo: 'Rodamos en zigzag entre los conos, mirando siempre el cono "
            "SIGUIENTE, no el que estamos pasando. La bici va donde mira la cabeza.'\n"
            "Muéstralo: el entrenador recorre el slalom señalando con los ojos el cono "
            "siguiente y mostrando la inclinación suave de la bici en cada curva.\n"
            "Háganlo: empieza con conos separados 3-4 m; cuando todos pasen fluido, "
            "acercalos a 1.5 m. Variante ①: libre; ② slalom doble (dos filas, "
            "carrera de velocidad); ③ con salida en rampa o de pie. Para 13-15: "
            "slalom apretado cronometrado contra marca propia.\n"
            "Revísenlo: '¿Dónde ponían los ojos al entrar en cada curva?'\n"
            "Clima de maestría: el reto es la mejora del tiempo propio; el slalom dual "
            "se usa para la emoción del 'duelo amistoso', nunca como ranking."
        ),
        "difficulty": "facil",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_41,
        "layout_alt": (
            "Fila de conos colocados en línea recta, alternados a izquierda y derecha "
            "del carril de avance, separados entre 1.5 y 4 metros según el nivel. "
            "El ciclista recorre el recorrido en zigzag, sorteando cada cono por el "
            "lado opuesto al anterior. Para el slalom dual se instalan dos filas "
            "paralelas de conos para que dos ciclistas corran simultáneamente. "
            "Aparece como estación 'SLALOM SUAVE' en el Circuito de Iniciación 7-9 "
            "(circuito 4.1) y como primer segmento de la Gymkana de Habilidad 10-12 "
            "(circuito 4.2) y de la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "confidence": "🟡⚪ [6][13]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["E", "D"],
        "material_slugs": ["conos"],
    },
    # ── 8 ──────────────────────────────────────────────────────────────────
    {
        "slug": "entre-las-lineas-pasillo",
        "name": "Entre las líneas (pasillo)",
        "summary": (
            "Rodar dentro de un pasillo que se va angostando; "
            "mirar al final del pasillo, no la rueda delantera."
        ),
        "how_to": (
            "Dilo: 'El pasillo tiene dos líneas. Deben mantenerse entre ellas sin "
            "pisarlas ni salirse. Miren al FINAL del pasillo, nunca la rueda.'\n"
            "Muéstralo: el entrenador recorre el pasillo mirando al frente, señalando "
            "que los ojos van a 5-10 m adelante, no abajo.\n"
            "Háganlo: empieza con pasillo de 1.5 m de ancho; reduce a 80 cm, 60 cm, "
            "40 cm según el nivel. Materiales: tiza, cuerda o tablones. Para aumentar "
            "la dificultad, añade un codo o giro leve a mitad del pasillo.\n"
            "Revísenlo: '¿Cuándo os salíais más: cuando mirabais la rueda o cuando "
            "mirabais el final?'\n"
            "Clima de maestría: cada ciclista marca el ancho mínimo que logró y trata "
            "de mejorar su propia marca en la próxima sesión."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_41,
        "layout_alt": (
            "Dos líneas paralelas trazadas con tiza, cuerda o tablones definen un "
            "pasillo recto de longitud 8-12 metros. El ancho inicial es de 1.5 metros "
            "y se reduce progresivamente. El ciclista debe recorrerlo de extremo a "
            "extremo sin pisar o cruzar ninguna de las dos líneas. Aparece como "
            "estación 'PASILLO ANCHO→ANGOSTO' en el Circuito de Iniciación 7-9 "
            "(circuito 4.1)."
        ),
        "confidence": "🟡 [6]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["A", "B"],
        "material_slugs": ["tiza", "cuerda", "tablones"],
    },
    # ── 9 ──────────────────────────────────────────────────────────────────
    {
        "slug": "esquiva-la-roca",
        "name": "Esquiva la roca",
        "summary": (
            "Acercarse recto a un obstáculo y esquivarlo en el último momento "
            "con golpe de manillar (separación cuerpo-bici)."
        ),
        "how_to": (
            "Dilo: 'Se acercan en línea recta al obstáculo y en el último momento "
            "dan un golpe seco de manillar para desviar la bici, separando el cuerpo. "
            "No frenen tarde: la maniobra es de dirección, no de velocidad.'\n"
            "Muéstralo: el entrenador se aproxima al tope/rama a velocidad moderada y "
            "realiza un desvío rápido a un lado, mostrando cómo la bici gira bajo el "
            "cuerpo mientras el torso se mantiene centrado.\n"
            "Háganlo: primero a velocidad baja; el ciclista elige el lado de esquiva. "
            "Luego el entrenador indica el lado en el último momento ('¡izquierda!'). "
            "Variante: dos obstáculos seguidos con lados opuestos.\n"
            "Revísenlo: '¿Qué parte del cuerpo movieron primero: la bici o el tronco?'\n"
            "Clima de maestría: el éxito es esquivar limpio; la velocidad de entrada "
            "la decide cada uno según su confianza. Aparece como estación 'ESQUIVA LA "
            "ROCA' en la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_43,
        "layout_alt": (
            "Un tope, rama o roca pequeña se coloca en el centro del carril de avance. "
            "El ciclista se aproxima en línea recta y, a 1-2 metros del obstáculo, "
            "realiza un desvío brusco de manillar para pasar por un lado sin frenar "
            "abruptamente. El carril de aproximación mide al menos 10 metros para "
            "permitir tomar velocidad. Aparece como segmento 'ESQUIVA LA ROCA' dentro "
            "de la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "confidence": "🟡 [6]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F", "D"],
        "material_slugs": ["topes", "ramas"],
    },
    # ── 10 ─────────────────────────────────────────────────────────────────
    {
        "slug": "ochos-figura-8",
        "name": "Ochos (figura-8)",
        "summary": (
            "Dibujar ochos entre dos conos o llantas, curvando a ambos lados, "
            "mirando la salida de cada curva con el pie exterior abajo."
        ),
        "how_to": (
            "Dilo: 'Hacemos ochos entre los dos conos. En cada curva miren hacia "
            "donde van a salir, no el cono. El pie de afuera va abajo, apoyando el "
            "peso en el pedal.'\n"
            "Muéstralo: el entrenador recorre un ocho mostrando la mirada anticipada "
            "y la posición del pedal exterior presionado hacia abajo en las curvas.\n"
            "Háganlo: empieza con los conos separados 4-5 m; cierra el radio "
            "progresivamente hasta 1.5 m. Variante: ochos con contrarreloj personal; "
            "ochos enlazados en grupo (tren).\n"
            "Revísenlo: '¿Dónde miraban cuando la curva salió más limpia?'\n"
            "Clima de maestría: el reto es el radio mínimo alcanzado con fluidez, "
            "no la velocidad."
        ),
        "difficulty": "facil",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_41,
        "layout_alt": (
            "Dos conos o llantas tendidas se colocan en el suelo separadas entre 1.5 "
            "y 5 metros (ajustable según nivel). El ciclista traza un recorrido en "
            "forma de ocho (∞) rodeando alternativamente cada referencia, curvando "
            "a la izquierda alrededor de una y a la derecha alrededor de la otra. "
            "Aparece como estación 'OCHOS' en el Circuito de Iniciación 7-9 "
            "(circuito 4.1)."
        ),
        "confidence": "⚪ [13]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["E"],
        "material_slugs": ["conos", "llantas"],
    },
    # ── 11 ─────────────────────────────────────────────────────────────────
    {
        "slug": "una-mano-soltar-mano",
        "name": "Una mano / soltar mano",
        "summary": (
            "Soltar una mano del manillar para señalar, tomar agua o pasar un objeto; "
            "prepara para beber y señalizar en grupo."
        ),
        "how_to": (
            "Dilo: 'Sueltan una mano mientras ruedan. Puede ser para señalizar, beber "
            "o pasarle algo a un compañero. La otra mano controla.'\n"
            "Muéstralo: el entrenador rueda en línea recta, suelta la mano derecha, "
            "señala, y la vuelve a poner. Luego lo hace con la izquierda.\n"
            "Háganlo: primero en recta a baja velocidad; luego con un objeto ligero "
            "(bidón, guante) que se pasa de mano en mano entre compañeros en movimiento. "
            "Variante: un dedo señalando y contando dedos del entrenador (similar al "
            "ejercicio de mirada al hombro).\n"
            "Revísenlo: '¿Cuándo el cuerpo compensó mejor?'\n"
            "Clima de maestría: énfasis en la funcionalidad (para señalizar y beber en "
            "carrera), no en la habilidad acrobática."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "⚪ [13]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F", "A"],
        "material_slugs": ["sin_material"],
    },
    # ── 12 ─────────────────────────────────────────────────────────────────
    {
        "slug": "mirada-al-hombro",
        "name": "Mirada al hombro",
        "summary": (
            "Mirar atrás y decir cuántos dedos muestra el entrenador, "
            "sin desviarse del pasillo o carril."
        ),
        "how_to": (
            "Dilo: 'Rodan en línea recta y, cuando lo indique, miran hacia atrás y "
            "me dicen cuántos dedos estoy mostrando. La bici debe seguir recta.'\n"
            "Muéstralo: el entrenador rueda, gira la cabeza 90° hacia un lado sin "
            "mover los hombros significativamente, y vuelve a mirar al frente. "
            "Señala que el truco es mover solo la cabeza.\n"
            "Háganlo: pasillo delimitado con tiza; el entrenador da la señal verbal "
            "y muestra 1-5 dedos. Variante: mirar al hombro al bajar una pendiente "
            "suave, o en un tramo de sendero recto.\n"
            "Revísenlo: '¿Se desviaron? ¿Qué parte del cuerpo movieron además de "
            "la cabeza?'\n"
            "Clima de maestría: el logro es mantener la línea recta; cuántos "
            "dedos acertaron es secundario."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "⚪ [13]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["B", "A"],
        "material_slugs": ["sin_material"],
    },
    # ── 13 ─────────────────────────────────────────────────────────────────
    {
        "slug": "frenado-en-zona",
        "name": "Frenado en zona",
        "summary": (
            "Llegar a velocidad y detenerse dentro de una 'caja de freno' de conos; "
            "peso atrás, un dedo por freno. La caja se achica y la velocidad sube."
        ),
        "how_to": (
            "Dilo: 'Hay una caja marcada con conos o tiza. Deben entrar y detenerse "
            "completamente dentro. Peso atrás, un dedo en cada freno. El freno "
            "delantero da ~70% de la potencia, el trasero ~30%.'\n"
            "Muéstralo: el entrenador se aproxima a velocidad moderada, traslada el "
            "peso hacia la rueda trasera y frena progresivamente hasta detenerse dentro "
            "de la caja. Repite con la caja achicada.\n"
            "Háganlo: empieza con caja de 2×2 m y velocidad baja; achica a 1.5 m, "
            "1 m y 0.5 m. Aumenta la velocidad de entrada según la confianza. "
            "Variante: frenado + giro de 180° (para la Gymkana 13-15).\n"
            "Revísenlo: '¿Cuándo tardaron más en frenar: cuando el peso estaba "
            "adelante o atrás?'\n"
            "Clima de maestría: celebra la mejora de la distancia de frenado propia, "
            "no la comparación. Aparece como estación 'FRENADO EN ZONA' en el "
            "Circuito de Iniciación 7-9 (circuito 4.1) y como 'CAJA DE FRENO' en "
            "la Gymkana de Habilidad 10-12 (circuito 4.2) y en la Gymkana Cronometrada "
            "13-15 como 'FRENADO + GIRO 180°' (circuito 4.3)."
        ),
        "difficulty": "facil",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_41,
        "layout_alt": (
            "Cuatro conos o líneas de tiza delimitan un rectángulo ('caja') en el suelo. "
            "Dimensiones iniciales: aproximadamente 2×2 metros, reducibles según el nivel. "
            "El ciclista toma carrera de 10-15 metros y frena para detenerse completamente "
            "dentro de la caja. En la variante avanzada (Gymkana 13-15) se agrega un giro "
            "de 180° dentro de la caja antes de arrancar de nuevo. Aparece como estación "
            "'FRENADO EN ZONA' en el Circuito de Iniciación 7-9 (circuito 4.1), como "
            "'CAJA DE FRENO' en la Gymkana de Habilidad 10-12 (circuito 4.2) y como "
            "'FRENADO + GIRO 180°' en la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "confidence": "⚪ [12]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["C"],
        "material_slugs": ["conos", "tiza"],
    },
    # ── 14 ─────────────────────────────────────────────────────────────────
    {
        "slug": "plancha-de-equilibrio-skinny",
        "name": "Plancha de equilibrio (skinny)",
        "summary": (
            "Rodar sobre un tablón angosto sin caerse; "
            "se aumenta el ancho y la altura gradualmente."
        ),
        "how_to": (
            "Dilo: 'Rodan encima del tablón de punta a punta sin caerse. Miren el "
            "extremo del tablón, no la rueda. Pedales nivelados.'\n"
            "Muéstralo: el entrenador monta el tablón despacio con pedales al nivel "
            "horizontal y mirada hacia el final del tablón, no hacia abajo.\n"
            "Háganlo: empieza con el tablón en el suelo (sin altura), ancho de ~20 cm. "
            "Cuando sea fluido, eleva uno o ambos extremos sobre un palé. Reduce el "
            "ancho a un tablón más estrecho o usa un tubo de PVC para máxima dificultad.\n"
            "Revísenlo: '¿Qué os ayudó a mantener el equilibrio: mirar el tablón o "
            "el final?'\n"
            "Clima de maestría: el logro es la longitud del tablón cruzada con "
            "fluidez, y la altura alcanzada. Sin comparaciones."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "⚪",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["A"],
        "material_slugs": ["tablones"],
    },
    # ── 15 ─────────────────────────────────────────────────────────────────
    {
        "slug": "levantar-rueda-delantera-manual",
        "name": "Levantar rueda delantera → manual",
        "summary": (
            "Levantar la rueda delantera para pasar un obstáculo bajo; "
            "progresa a sostener el manual (wheelie de momentum)."
        ),
        "how_to": (
            "Dilo: 'Primero aprenden a 'cargar' la rueda delantera: empujan el "
            "manillar hacia abajo y luego lo jalan hacia arriba al pasar el obstáculo. "
            "El manual es mantener la rueda arriba rodando.'\n"
            "Muéstralo: el entrenador pasa sobre una rama o estaca baja mostrando el "
            "movimiento de compresión-extensión de brazos. Para el manual, muestra "
            "el punto de equilibrio.\n"
            "Háganlo: rama o estaca de 5-10 cm de altura; levanta solo la delantera "
            "para pasar. Cuando sea fluido, intenta mantener la rueda arriba 2-3 m "
            "después del obstáculo (pre-manual). Para 13-15: manual sostenido sobre "
            "distancia controlada.\n"
            "Revísenlo: '¿En qué momento del movimiento sintieron que la rueda "
            "subió sola?'\n"
            "Clima de maestría: no hay altura mínima; el reto es reproducir el "
            "gesto con control."
        ),
        "difficulty": "avanzada",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡⚪ [11]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F", "G"],
        "material_slugs": ["estacas", "ramas"],
    },
    # ── 16 ─────────────────────────────────────────────────────────────────
    {
        "slug": "bunny-hop-sobre-tope",
        "name": "Bunny hop sobre tope/rama",
        "summary": (
            "Saltar ambas ruedas sobre una barra baja: primero el 'j-hop', "
            "luego el bunny hop completo. Altura progresiva."
        ),
        "how_to": (
            "Dilo: 'El bunny hop es levantar primero la delantera y luego empujar las "
            "piernas hacia arriba para que la trasera también vuele. Empezamos con "
            "el j-hop: solo levantamos la delantera y usamos el momentum para que "
            "la trasera suba.'\n"
            "Muéstralo: el entrenador hace un j-hop sobre la barra baja, luego un "
            "bunny hop completo con ambas ruedas en el aire simultáneamente.\n"
            "Háganlo: barra o rama a 5 cm; j-hop. Sube a 10-15 cm; bunny hop. "
            "Progresión de altura en pasos de 5 cm. Sin presión: cada uno elige su "
            "altura de trabajo. Solo para 13-15 años.\n"
            "Revísenlo: '¿Qué pasó cuando intentaron subir la trasera sin haber "
            "subido antes la delantera?'\n"
            "Clima de maestría: registra la altura propia de cada sesión; sin "
            "comparar alturas entre compañeros. Aparece como segmento 'BUNNY HOP' "
            "en la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "difficulty": "avanzada",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_43,
        "layout_alt": (
            "Dos estacas clavadas a ambos lados del carril sostienen una barra "
            "horizontal (palo, rama o cinta) a una altura regulable entre 5 y 30 cm "
            "del suelo. El ciclista se aproxima en línea recta, levanta primero la "
            "rueda delantera y luego la trasera para saltar la barra completa. "
            "Aparece como segmento 'BUNNY HOP' dentro de la Gymkana Cronometrada "
            "13-15 (circuito 4.3)."
        ),
        "confidence": "🟡⚪ [11]",
        "age_bands": ["13-15"],
        "skill_codes": ["F", "G"],
        "material_slugs": ["estacas", "ramas", "llantas"],
    },
    # ── 17 ─────────────────────────────────────────────────────────────────
    {
        "slug": "subir-bajar-bordillo-drop",
        "name": "Subir/bajar bordillo (drop)",
        "summary": (
            "Bajar pequeños escalones con peso atrás y subir con timing de manillar; "
            "altura progresiva desde tope hasta rampa de palé."
        ),
        "how_to": (
            "Dilo: 'Para bajar: el peso va atrás, los brazos se extienden y dejan "
            "caer la bici. Para subir: jalamos el manillar justo antes de que la "
            "rueda llegue al bordillo.'\n"
            "Muéstralo: el entrenador baja un tope/bordillo a velocidad baja, "
            "mostrando los brazos extendidos y el sillín libre. Luego sube el mismo "
            "bordillo con un pequeño jale de manillar.\n"
            "Háganlo: empieza con tope de 5-10 cm (bajada); cuando sea controlado, "
            "sube a 20-30 cm (rampa de palé). Trabaja bajada y subida por separado "
            "antes de encadenarlas. Para 13-15: incluye en la Gymkana Cronometrada.\n"
            "Revísenlo: '¿Cuándo sintieron que la bici 'se fue' hacia adelante? "
            "¿Qué habrían hecho diferente con el cuerpo?'\n"
            "Clima de maestría: la altura de trabajo la elige el ciclista; el logro "
            "es el control, no la altura máxima. Aparece como 'SUBIR/BAJAR TOPE "
            "(drop)' en la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_43,
        "layout_alt": (
            "Un tope, bordillo o rampa construida con palés y tablones se coloca "
            "atravesando el carril. Para la bajada, el ciclista sube a la parte alta "
            "y desciende el escalón con peso hacia atrás. Para la subida, se aproxima "
            "desde el nivel inferior y usa el timing de manillar para subir. Altura "
            "inicial: 5-10 cm (tope); progresa hasta 20-30 cm (rampa de palé). "
            "Aparece como 'SUBIR/BAJAR TOPE (drop)' en la Gymkana Cronometrada "
            "13-15 (circuito 4.3)."
        ),
        "confidence": "⚪ [7]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["G"],
        "material_slugs": ["topes", "tablones"],
    },
    # ── 18 ─────────────────────────────────────────────────────────────────
    {
        "slug": "escalera-de-llantas",
        "name": "Escalera de llantas",
        "summary": (
            "Pasar entre/sobre llantas tendidas en el suelo con precisión y cadencia."
        ),
        "how_to": (
            "Dilo: 'Las llantas están en el suelo formando una escalera. Pasamos "
            "entre o sobre ellas sin tocarlas, con pedales nivelados y cadencia "
            "constante. Miramos hacia el final, no los pies.'\n"
            "Muéstralo: el entrenador pasa a ritmo constante entre las llantas, "
            "con pedales horizontales cuando pasa sobre ellas.\n"
            "Háganlo: primero muy despacio caminando la bici; luego a velocidad "
            "de rodada normal. Varía el espaciado de las llantas (más juntas = más "
            "precisión). Variante avanzada: pasar sobre las llantas (no entre ellas) "
            "con la rueda delantera levantada.\n"
            "Revísenlo: '¿Cuándo fue más fácil: mirando las llantas o mirando "
            "el final de la escalera?'\n"
            "Clima de maestría: el reto es la fluidez del paso, no la velocidad. "
            "Aparece como estación 'ESCALERA DE LLANTAS' en la Gymkana de Habilidad "
            "10-12 (circuito 4.2)."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_42,
        "layout_alt": (
            "Varias llantas tendidas se colocan en el suelo alineadas en fila con "
            "espaciado regular (entre 0.5 y 1 metro), formando una 'escalera'. El "
            "ciclista rueda entre o sobre ellas de un extremo al otro sin pisarlas. "
            "El número de llantas y el espaciado se ajustan según el nivel. Aparece "
            "como estación 'ESCALERA DE LLANTAS' en la Gymkana de Habilidad 10-12 "
            "(circuito 4.2)."
        ),
        "confidence": "⚪",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["F", "H"],
        "material_slugs": ["llantas"],
    },
    # ── 19 ─────────────────────────────────────────────────────────────────
    {
        "slug": "pump-ondulaciones",
        "name": "Pump / ondulaciones",
        "summary": (
            "Avanzar sin pedalear bombeando con brazos y piernas sobre un pump track "
            "o rollers de tierra; transfiere energía del cuerpo a la bici."
        ),
        "how_to": (
            "Dilo: 'Sin pedalear: empujan con los brazos hacia abajo en la bajada de "
            "cada ondulación y 'absorben' con piernas en la subida. La bici gana "
            "velocidad con el cuerpo, no con las piernas.'\n"
            "Muéstralo: el entrenador recorre las ondulaciones sin pedalear, "
            "exagerando la compresión en la bajada y la absorción en la subida.\n"
            "Háganlo: empieza a velocidad muy baja para sentir el ritmo; "
            "para 7-9 en rollers suaves o pendiente baja con ondulaciones de tierra. "
            "Para 13-15: pump track con bermas. Variante: pump en curva peraltada "
            "(berma). Encadenado final: pump sin pedalear entre dos conos lo más "
            "lejos posible.\n"
            "Revísenlo: '¿En qué parte de la ola empujaban? ¿Ganaban o perdían "
            "velocidad?'\n"
            "Clima de maestría: el reto es cuántas ondulaciones cruzan sin pedalear; "
            "cada uno mejora su propia distancia. Aparece como segmento 'PUMP / "
            "ONDULACIONES' en la Gymkana Cronometrada 13-15 (circuito 4.3)."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_43,
        "layout_alt": (
            "Zona con ondulaciones de tierra (pump track) o una serie de montículos "
            "y bajadas construidos con tierra compactada. El ciclista recorre la zona "
            "sin pedalear, usando la compresión y extensión del cuerpo para ganar "
            "momentum. Aparece como segmento 'PUMP / ONDULACIONES' en la Gymkana "
            "Cronometrada 13-15 (circuito 4.3)."
        ),
        "confidence": "🟡 [11]",
        "age_bands": ["7-9", "10-12", "13-15"],
        "skill_codes": ["G"],
        "material_slugs": ["pump_track"],
    },
    # ── 20 ─────────────────────────────────────────────────────────────────
    {
        "slug": "terreno-natural-raices-y-rocas",
        "name": "Terreno natural: raíces y rocas",
        "summary": (
            "Pies nivelados, peso ligero sobre los pedales, mirando la línea; "
            "aplicar lo aprendido en seco antes de hacerlo en húmedo."
        ),
        "how_to": (
            "Dilo: 'En el terreno con raíces y rocas: pedales al mismo nivel, peso "
            "distribuido (no sentados en el sillín), mirada lejos buscando la línea "
            "limpia. El cuerpo absorbe, no la bici.'\n"
            "Muéstralo: el entrenador recorre una sección con raíces a velocidad "
            "controlada, señalando con la vista la línea elegida antes de entrar.\n"
            "Háganlo: primero en seco y despacio; luego aumenta la velocidad cuando "
            "la línea sea consistente. Para 13-15: añade variación de líneas y toma "
            "de decisiones en movimiento. Principio: no llevar al ciclista a terreno "
            "difícil antes de que esté listo.\n"
            "Revísenlo: '¿Dónde elegían la línea: antes de entrar a la sección o "
            "dentro de ella?'\n"
            "Clima de maestría: sin tiempo; el logro es cruzar la sección con "
            "control y sin ansiedad."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡 [5][11]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["G", "B"],
        "material_slugs": ["sendero"],
    },
    # ── 21 ─────────────────────────────────────────────────────────────────
    {
        "slug": "subida-tecnica-corta",
        "name": "Subida técnica corta",
        "summary": (
            "Engranar antes de la subida, pedalear sentado con cadencia ≥70 rpm "
            "y peso ligeramente adelante para mantener tracción."
        ),
        "how_to": (
            "Dilo: 'Antes de llegar a la subida, cambian a un desarrollo más liviano. "
            "Arriba: sentados, cadencia ≥70, peso un poco adelante para no levantar "
            "la rueda delantera.'\n"
            "Muéstralo: el entrenador se aproxima a la pendiente, cambia una marcha "
            "antes de llegar, y sube sentado con cadencia fluida sin zigzaguear.\n"
            "Háganlo: pendiente corta de 10-30 m, inclinación suave al inicio. "
            "Práctica del timing del cambio: cuándo es 'demasiado tarde'. Variante: "
            "subida en pelotón pequeño, manteniendo distancia.\n"
            "Revísenlo: '¿Cuándo perdieron tracción: cuando el peso estaba adelante "
            "o atrás?'\n"
            "Clima de maestría: el logro es completar la subida con cadencia fluida, "
            "no ser el primero en llegar arriba."
        ),
        "difficulty": "media",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟡 [1]",
        "age_bands": ["10-12", "13-15"],
        "skill_codes": ["H", "A"],
        "material_slugs": ["pendiente"],
    },
    # ── 22 ─────────────────────────────────────────────────────────────────
    {
        "slug": "busqueda-del-tesoro-relevo",
        "name": "Búsqueda del tesoro / relevo",
        "summary": (
            "Por equipos cooperativos: recoger objetos en estaciones aplicando "
            "las habilidades del día."
        ),
        "how_to": (
            "Dilo: 'Hay estaciones por el circuito. Cada equipo recoge un objeto en "
            "cada estación y lo trae a la base. Cooperan: el equipo gana junto.'\n"
            "Muéstralo: el entrenador explica la ruta y muestra cómo se recoge el "
            "objeto en cada estación (que requiere ejecutar una habilidad: slalom, "
            "pasillo, frenado, etc.).\n"
            "Háganlo: grupos de 3-4; cada estación tiene un objeto (cono, pañuelo, "
            "piedrita) y un 'peaje' (habilidad técnica que hacer antes de recoger). "
            "Sin tiempo: el objetivo es completar el recorrido. Variante: relevo "
            "posta (uno va, vuelve, sale el siguiente).\n"
            "Revísenlo: '¿Qué habilidad fue la más difícil de la estación?'\n"
            "Clima de maestría: se premia la cooperación y el intento. Ningún equipo "
            "es 'el mejor'; todos completan el recorrido."
        ),
        "difficulty": "media",
        "is_game": True,
        "is_gymkhana": True,
        "layout_ascii": LAYOUT_42,
        "layout_alt": (
            "Circuito de 4-6 estaciones distribuidas en un espacio de 20×20 metros "
            "aproximadamente. Cada estación tiene un cono identificador y un objeto "
            "a recoger (pañuelo, piedrita, pelota). Para obtener el objeto, el "
            "ciclista debe superar un peaje de habilidad en esa estación (slalom, "
            "pasillo, frenado, etc.). Los equipos recogen todos los objetos y regresan "
            "a la base. No requiere layout fijo: puede adaptarse a cualquier circuito "
            "disponible. Aquí se representa dentro de la Gymkana de Habilidad 10-12 "
            "(circuito 4.2) como ejemplo de uso del espacio."
        ),
        "confidence": "🟢(clima) [9]",
        "age_bands": ["7-9", "10-12"],
        "skill_codes": [
            "A", "B", "C", "D", "E", "F", "G", "H",
        ],
        "material_slugs": ["conos", "balones", "ramas"],
    },
    # ── 23 ─────────────────────────────────────────────────────────────────
    {
        "slug": "la-traes-sobre-bici-bike-tag",
        "name": "La traes sobre bici (bike tag)",
        "summary": (
            "'Tocar' a un compañero sin chocar, a baja velocidad, mirando alrededor; "
            "juego de persecución en zona delimitada."
        ),
        "how_to": (
            "Dilo: 'El que la trae debe tocar (suavemente con la mano) a otro "
            "ciclista. El tocado la trae. Nada de choques: si chocas, la traes "
            "automáticamente. Zona delimitada: si sales, la traes.'\n"
            "Muéstralo: el entrenador demuestra cómo acercarse y tocar suavemente "
            "el hombro o la espalda del compañero, sin chocar con las bicis.\n"
            "Háganlo: zona de ~15×15 m para 5-6 ciclistas; ajusta el tamaño a la "
            "cantidad de participantes. Velocidad baja. Puede jugarse con 1 o 2 que "
            "la traen simultáneamente.\n"
            "Revísenlo: '¿Qué mirabas para saber dónde ir?'\n"
            "Clima de maestría: el juego es para reír y moverse; sin ranking de "
            "quién la trajo más veces."
        ),
        "difficulty": "facil",
        "is_game": True,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "🟢(clima) [9]",
        "age_bands": ["7-9", "10-12"],
        "skill_codes": ["A", "D", "B"],
        "material_slugs": ["conos"],
    },
    # ── 24 ─────────────────────────────────────────────────────────────────
    {
        "slug": "trackstand-challenge",
        "name": "Trackstand challenge",
        "summary": (
            "Quedarse parado en equilibrio sobre la bici el mayor tiempo posible; "
            "reto personal contra el propio récord."
        ),
        "how_to": (
            "Dilo: 'El objetivo es quedarse parado en equilibrio, sin mover los pies, "
            "el mayor tiempo posible. Cada uno mide su tiempo y trata de batir su "
            "propia marca.'\n"
            "Muéstralo: el entrenador muestra el trackstand: pedal delantero "
            "ligeramente adelantado, peso centrado, microajustes de manillar, "
            "posibilidad de usar una leve pendiente de ayuda al inicio.\n"
            "Háganlo: cada uno intenta 3 veces seguidas; anota su mejor tiempo. "
            "Variante: trackstand en una zona delimitada (cuadro de 50×50 cm). "
            "Solo para 13-15 años (requiere control fino ya desarrollado).\n"
            "Revísenlo: '¿Qué os ayudó a aguantar más: mirar arriba o mirar abajo?'\n"
            "Clima de maestría: cada uno compite con su propio tiempo anterior, nunca "
            "con el compañero. El reto es personal."
        ),
        "difficulty": "avanzada",
        "is_game": False,
        "is_gymkhana": False,
        "layout_ascii": None,
        "layout_alt": None,
        "confidence": "⚪ [13]",
        "age_bands": ["13-15"],
        "skill_codes": ["A"],
        "material_slugs": ["sin_material"],
    },
]
