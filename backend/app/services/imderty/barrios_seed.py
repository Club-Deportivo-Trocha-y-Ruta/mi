"""Datos semilla de barrios/sectores del municipio de Yumbo para IMDERTY.

`BARRIOS_YUMBO` se extrajo de la hoja **`SECTOR`** (única hoja leída, columnas
A–B) del libro de referencia del dueño del club
(`~/Downloads/DOC-20260921-WA0005.xlsx`, no versionado en el repo). Las hojas
mensuales (AGOSTO, SEPTIEMBRE, …) de ese libro contienen datos de
participantes y nunca se abrieron para generar esta semilla.

Convenciones:
- Nombres en mayúsculas, con tildes/diacríticos conservados tal como
  aparecen en la fuente.
- Zona: uno de `"1"`, `"2"`, `"3"`, `"4"`, `"ZONA NORTE"`, `"ZONA CENTRO"`,
  `"ZONA SUR"` (texto tal como lo usa IMDERTY en la hoja SECTOR).

Grafías duplicadas encontradas en la hoja fuente:
- "ALTO DE SAN JORGE" y "ALTO SAN JORGE" apuntaban ambas a la zona "1" →
  se colapsaron en una sola entrada ("ALTO SAN JORGE", forma más corta).
- "PEDREGAL" (zona "3") y "EL PEDREGAL" (zona "ZONA SUR") NO se colapsaron:
  aunque el nombre es similar, la hoja fuente los ubica en zonas distintas,
  así que se mantienen como barrios separados.
- "MIRAVALLE", "MIRAVALLE DAPA" y "MIRAVALLE NORTE" no son grafías
  duplicadas del mismo barrio (sufijos distintos en la fuente); se
  mantienen como entradas separadas.
"""

from __future__ import annotations

BARRIOS_YUMBO: tuple[tuple[str, str], ...] = (
    ("ALTO DAPA", "ZONA SUR"),
    ("ALTO SAN JORGE", "1"),
    ("ALTOS DE MENGA", "ZONA SUR"),
    ("ARROYOHONDO", "ZONA SUR"),
    ("ASOPROSAN", "ZONA NORTE"),
    ("ASOVIVIR LAS COLINAS", "3"),
    ("BELALCAZAR", "2"),
    ("BELLAVISTA", "4"),
    ("BOLIVAR", "2"),
    ("BRISAS DE LA SULTANA", "4"),
    ("BUENOS AIRES", "3"),
    ("CACIQUE JACINTO", "4"),
    ("CAMPESTRE REAL", "4"),
    ("CANGREJO", "ZONA NORTE"),
    ("CIUDADELA PORTALES DE COMFANDI", "2"),
    ("COLINAS DEL NORTE", "1"),
    ("CONQUISTADORES", "4"),
    ("CORVIVALLE", "3"),
    ("DAPA", "ZONA SUR"),
    ("DIONISIO HERNÁN CALDERÓN", "4"),
    ("EL CHOCHO", "ZONA CENTRO"),
    ("EL HIGUERON", "ZONA NORTE"),
    ("EL PEDREGAL", "ZONA SUR"),
    ("EL PLACER", "ZONA CENTRO"),
    ("EL TABLAZO", "ZONA SUR"),
    ("FINLANDIA", "3"),
    ("FLORAL", "4"),
    ("FRAY PEÑA", "2"),
    ("GUABINAS", "1"),
    ("GUACANDA", "4"),
    ("HACIENDA VERDE", "1"),
    ("INVIYUMBO SAN JORGE", "1"),
    ("JORGE ELIECER GAITAN", "4"),
    ("JUAN PABLO II", "1"),
    ("LA BUITRERA", "ZONA CENTRO"),
    ("LA CEIBA", "4"),
    ("LA ESTANCIA", "1"),
    ("LA NUEVA ESTANCIA", "1"),
    ("LA OLGA", "ZONA SUR"),
    ("LA SULTANA", "4"),
    ("LAGUNA SECA", "ZONA SUR"),
    ("LAS AMÉRICAS", "1"),
    ("LAS CRUCES", "3"),
    ("LAS VEGAS", "4"),
    ("LLERAS", "4"),
    ("MADRIGAL", "4"),
    ("MANGA VIEJA", "ZONA NORTE"),
    ("MENGA", "ZONA SUR"),
    ("MIRAVALLE", "ZONA SUR"),
    ("MIRAVALLE DAPA", "ZONA SUR"),
    ("MIRAVALLE NORTE", "ZONA NORTE"),
    ("MONTAÑITAS", "ZONA CENTRO"),
    ("MULALÓ", "ZONA NORTE"),
    ("MUNICIPAL", "4"),
    ("NUESTRA SEÑORA DE GUADALUPE", "4"),
    ("NUEVO HORIZONTE", "3"),
    ("PANORAMA", "1"),
    ("PARQUES DEL PINAR", "1"),
    ("PASO DE LA TORRE", "ZONA NORTE"),
    ("PASOANCHO", "3"),
    ("PEDREGAL", "3"),
    ("PILAS DAPA", "ZONA SUR"),
    ("PILES", "ZONA CENTRO"),
    ("PLATANARES", "ZONA NORTE"),
    ("PORTALES DE YUMBO", "4"),
    ("PUERTO ISAAC", "1"),
    ("PUERTO RICO", "ZONA CENTRO"),
    ("RINCÓN DAPA", "ZONA SUR"),
    ("RIVERAS DE YUMBO", "3"),
    ("SALAZAR", "ZONA CENTRO"),
    ("SAN FERNANDO", "3"),
    ("SAN JORGE", "1"),
    ("SAN JOSÉ", "ZONA CENTRO"),
    ("SAN MARCOS", "ZONA NORTE"),
    ("SANTA INÉS", "ZONA CENTRO"),
    ("TELECOM", "ZONA CENTRO"),
    ("TRINIDAD", "3"),
    ("TRINIDAD I", "3"),
    ("URBANIZACIÓN CARLOS PIZARRO", "4"),
    ("URIBE URIBE", "2"),
    ("XIXAOLA", "ZONA SUR"),
    ("YUMBILLO", "ZONA CENTRO"),
)
"""82 pares (nombre, zona) — ver docstring del módulo para el detalle de
colapso de grafías duplicadas."""
