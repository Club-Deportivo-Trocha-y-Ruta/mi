# Feature Specification: Newsletter Audit Fixes — Boletín Mensual Individual

**Feature Branch**: `024-newsletter-audit-fixes`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "Corrección y pulido del Boletín Mensual Individual (newsletter para padres). Arregla 5 bugs confirmados y 9 mejoras de presentación detectadas al auditar el PDF generado (boletín junio 2026): etiqueta de campeonato mostrada como V1, género incorrecto en narrativa IA, galería vacía renderizada, referencia RPE engañosa, horas vs límite LTAD sin conversión, focos del mes sin agrupar, código de categoría crudo, fechas ISO, página 1 vacía, labels de gráficos recortados, headers de tabla antropométrica rotos, redundancia de racha, gráfico de puntos plano en campeonatos sin nota, y tips de apoyo genéricos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Datos correctos y confiables en el boletín (Priority: P1)

Como padre/madre de un atleta del club, cuando recibo el boletín mensual quiero que cada dato sea correcto: que el resultado de una carrera esté identificado con el nombre real de la competencia (Campeonato Departamental, no "Válida 1"), que el texto del entrenador use el género correcto de mi hija/hijo, y que las referencias de esfuerzo (RPE) y de carga de entrenamiento reflejen el marco de entrenamiento juvenil del club sin inducir interpretaciones erróneas.

**Why this priority**: Errores factuales visibles (competencia mal etiquetada, "su hijo" para una niña) minan la confianza de las familias en todo el documento. Son los defectos más visibles del boletín de junio 2026 y afectan directamente la credibilidad del club.

**Independent Test**: Regenerar el boletín de junio 2026 de una atleta femenina que compitió en el Campeonato Departamental y verificar: (a) el destacado de resultado dice "CD" / "Campeonato Departamental" y no "V1"; (b) la valoración del entrenador usa género femenino o forma neutra; (c) la referencia de RPE es coherente con entrenamiento base juvenil; (d) la carga mensual se compara contra el límite semanal convertido correctamente.

**Acceptance Scenarios**:

1. **Given** una atleta cuyo último resultado del mes fue en el Campeonato Departamental, **When** se genera el boletín, **Then** el indicador destacado de la página 1 muestra la etiqueta corta del campeonato ("CD") y nunca "V1", y las tablas/detalles muestran "Campeonato Departamental".
2. **Given** un atleta cuyo último resultado del mes fue la Válida 3 de la Copa, **When** se genera el boletín, **Then** el indicador destacado muestra "V3" (comportamiento actual preservado).
3. **Given** una atleta de sexo femenino, **When** se genera la valoración narrativa del entrenador (con IA), **Then** el texto usa género femenino ("su hija", "ella") de forma consistente en todo el documento.
4. **Given** que el servicio de IA no está disponible y se usa el texto de respaldo estático, **When** se genera la valoración, **Then** el texto usa una forma acorde al sexo registrado del atleta o una forma neutra que no asigne género incorrecto.
5. **Given** un mes con RPE promedio de 4.8 en fase de base, **When** se muestra el indicador de RPE, **Then** la referencia contextual indica el rango apropiado para entrenamiento base juvenil (aprox. 3–5 en escala OMNI 0–10) y no "ideal 6-7 para entrenamiento base".
6. **Given** un atleta de 13.9 años con 27.5 horas entrenadas en el mes, **When** se muestra el indicador de horas, **Then** el boletín muestra el promedio semanal calculado (≈6.4 h/sem) junto al límite personal (≤13.9 h/sem) y un estado de cumplimiento visible (dentro del límite / por revisar).

---

### User Story 2 - Secciones sin contenido vacío ni redundante (Priority: P2)

Como padre/madre, quiero que el boletín no muestre secciones vacías (galería sin fotos) ni datos repetidos (la racha de asistencia dos veces), y que el gráfico de puntos explique por qué se aplana cuando hay campeonatos.

**Why this priority**: Una sección vacía o duplicada hace ver el documento como inacabado, pero no comunica información incorrecta. Impacta percepción de calidad, no confianza en los datos.

**Independent Test**: Generar tres boletines: uno sin fotos consentidas del mes, uno con fotos disponibles, y uno cuyo historial incluye un campeonato; verificar galería oculta/placeholder, galería con imágenes, y nota aclaratoria en el gráfico de puntos respectivamente.

**Acceptance Scenarios**:

1. **Given** un mes sin fotos elegibles (con consentimiento y atleta etiquetado), **When** se genera el PDF, **Then** la sección "Galería del Mes" no aparece.
2. **Given** un mes con fotos elegibles pero cuyas imágenes no pueden incorporarse al PDF, **When** se genera el PDF, **Then** la sección muestra un mensaje con el número de fotos disponibles y dónde verlas, en lugar de un espacio vacío.
3. **Given** un mes con fotos elegibles e incorporables, **When** se genera el PDF, **Then** las imágenes aparecen en la galería (comportamiento esperado preservado).
4. **Given** un boletín con racha de asistencia, **When** se genera el documento, **Then** la racha aparece una sola vez, etiquetada como sesiones consecutivas (no "días").
5. **Given** un historial de temporada que incluye un campeonato, **When** se muestra el gráfico de puntos acumulados, **Then** aparece una nota aclaratoria indicando que los campeonatos no otorgan puntos de Copa.

---

### User Story 3 - Presentación legible y en español para las familias (Priority: P2)

Como padre/madre sin conocimiento técnico, quiero leer fechas en español ("1 de agosto" en lugar de "2026-08-01"), el nombre de la categoría en palabras ("Prejuvenil A Femenino" en lugar de "PJUV_A_F"), y un resumen de los focos de entrenamiento del mes agrupado por tipo de habilidad en lugar de una lista de ~15 títulos de sesión con casi-duplicados.

**Why this priority**: Mejora la comprensión de la audiencia objetivo (familias), pero el contenido subyacente ya es correcto.

**Independent Test**: Generar el boletín de junio 2026 y verificar formato de fechas, etiqueta de categoría y agrupación de focos en las secciones correspondientes.

**Acceptance Scenarios**:

1. **Given** cualquier fecha visible para las familias (próxima válida, sesiones planificadas, resultados), **When** se genera el boletín, **Then** las fechas se muestran en formato en español (ej. "1 de agosto de 2026" o "1 ago 2026"), de forma consistente en PDF y email.
2. **Given** un resultado con código de categoría "PJUV_A_F", **When** se muestra en el boletín, **Then** aparece la etiqueta legible "Prejuvenil A Femenino"; ante un código no reconocido se muestra el código original sin fallar.
3. **Given** un mes con ~15 sesiones cuyos focos incluyen casi-duplicados ("Descenso técnico", "Técnica en descenso", "Técnico en descensos rápidos"), **When** se muestra "Focos del mes", **Then** los focos aparecen agrupados por familia de habilidad con conteo de sesiones (ej. "Descensos y curvas — 5 sesiones"), y los focos que no encajan en ninguna familia se agrupan en "Otros".

---

### User Story 4 - Documento visualmente pulido (Priority: P3)

Como entrenador que envía el boletín a las familias, quiero que el PDF se vea profesional: sin la primera página 60% vacía, sin números recortados en los gráficos, sin encabezados de tabla partidos ("IM C", "ZTallaPTalla"), y con la sección "Cómo apoyar desde casa" mostrando solo la banda etaria del atleta y variando mes a mes.

**Why this priority**: Pulido visual y de contenido estático; no afecta corrección de datos ni comprensión esencial.

**Independent Test**: Generar el PDF de junio 2026 e inspeccionar visualmente página 1, los tres gráficos de evolución, la tabla antropométrica y la sección de apoyo; regenerar para un mes distinto y verificar que los tips varían.

**Acceptance Scenarios**:

1. **Given** el boletín generado, **When** se revisa la página 1, **Then** el contenido fluye de modo que la valoración del entrenador (o la siguiente sección) comienza en la página 1, sin dejar más de ~30% de espacio vacío.
2. **Given** los gráficos de evolución (posición, gap, puntos), **When** se renderizan, **Then** ningún valor o etiqueta queda recortado por los bordes del gráfico.
3. **Given** la tabla de seguimiento antropométrico, **When** se renderiza, **Then** los encabezados de columna se leen completos y sin cortes de palabra erróneos ("IMC", "Z-Talla", "P-Talla").
4. **Given** un atleta de 14 años, **When** se muestra "Cómo apoyar desde casa", **Then** los consejos muestran únicamente los valores de la banda 13-15 (ej. sueño 8-10 horas) y no ambas bandas.
5. **Given** boletines de dos meses consecutivos para el mismo atleta, **When** se comparan las secciones "Cómo apoyar desde casa", **Then** el contenido de los consejos varía entre meses (rotación determinista por mes), manteniendo siempre los principios del club (sin suplementos, sin conteo calórico).

---

### Edge Cases

- Atleta sin sexo registrado → la narrativa (IA y respaldo) usa forma neutra ("su hijo/a" o el nombre del atleta) sin fallar.
- Último resultado del mes es un Campeonato Nacional → etiqueta corta "CN" / "Campeonato Nacional" (mismo mecanismo que "CD").
- Mes sin ninguna sesión ejecutada → indicadores de horas/RPE y focos muestran estado vacío sin comparativa LTAD ni división por cero.
- Mes con menos de una semana de duración efectiva de entrenamiento → el promedio semanal usa las semanas calendario del mes (constante ≈4.33), no las semanas con sesiones.
- Foto elegible cuyo archivo remoto ya no existe al momento de generar el PDF → el boletín se genera igual; la foto ausente no rompe la galería.
- Código de categoría nuevo o con formato inesperado → se muestra tal cual, sin traducción, y la generación no falla.
- Boletines históricos ya generados (snapshots persistidos con el esquema anterior) → se siguen pudiendo renderizar sin error; los cambios aplican a boletines generados a partir de esta versión.
- Atleta que cumple años a mitad de mes → el límite LTAD usa la edad decimal vigente a la fecha de generación del boletín.

## Requirements *(mandatory)*

### Functional Requirements

**Corrección de datos (Sección A)**

- **FR-001**: El indicador destacado de resultado de carrera MUST identificar los campeonatos con su etiqueta propia (corta "CD"/"CN" en tarjetas compactas; "Campeonato Departamental"/"Campeonato Nacional" en textos y tablas) y MUST NOT mostrarlos como válida numerada, en PDF y email.
- **FR-002**: La valoración narrativa generada con IA MUST recibir el sexo registrado del atleta y producir texto con el género gramatical correcto; el texto de respaldo estático MUST usar el género correcto o una forma neutra cuando el sexo no esté registrado.
- **FR-003**: La sección "Galería del Mes" MUST omitirse cuando no existan fotos elegibles en el mes, y MUST mostrar un mensaje informativo con el conteo de fotos cuando existan fotos elegibles que no puedan incorporarse al documento; MUST NOT renderizarse como sección vacía.
- **FR-004**: La referencia contextual del indicador de RPE MUST ser coherente con el marco de entrenamiento juvenil del club (base ≈ RPE 3–5 en escala OMNI 0–10) y MUST NOT indicar "ideal 6-7 para entrenamiento base".
- **FR-005**: El indicador de carga MUST mostrar el promedio semanal de horas del mes junto al límite personal según la regla LTAD (horas/semana ≤ edad del atleta) y un estado de cumplimiento visible; MUST NOT comparar el total mensual directamente contra el límite semanal.

**Presentación (Sección B)**

- **FR-006**: Los focos técnicos del mes MUST presentarse agrupados por familia de habilidad con el número de sesiones por grupo; los focos no clasificables MUST agruparse bajo "Otros"; la lista cruda de títulos MUST NOT mostrarse.
- **FR-007**: Los códigos de categoría de competencia MUST mostrarse con etiqueta legible en español; ante un código no mapeado el sistema MUST mostrar el código original sin fallar.
- **FR-008**: Todas las fechas visibles para las familias MUST mostrarse en formato de fecha en español, consistente entre PDF y email.
- **FR-009**: El contenido del PDF MUST fluir sin dejar la página 1 mayormente vacía; la valoración del entrenador o la siguiente sección MUST comenzar en la página 1 cuando el contenido lo permita.
- **FR-010**: Los gráficos de evolución MUST renderizar todos los valores y etiquetas dentro del área visible, sin recortes.
- **FR-011**: Los encabezados de la tabla antropométrica MUST leerse completos, sin cortes de palabra erróneos.
- **FR-012**: La racha de asistencia MUST aparecer una sola vez por documento y MUST etiquetarse como sesiones consecutivas.
- **FR-013**: El gráfico de puntos acumulados MUST incluir una nota aclaratoria cuando el historial contenga campeonatos, indicando que estos no otorgan puntos de Copa.
- **FR-014**: La sección "Cómo apoyar desde casa" MUST mostrar solo los valores de la banda etaria del atleta (10-12 o 13-15) y MUST variar su contenido entre meses de forma determinista (mismo mes + mismo atleta → mismo contenido), preservando siempre los principios del club (sin suplementos, sin conteo calórico, comida real).

**Compatibilidad**

- **FR-015**: Los boletines ya generados con el esquema de datos anterior MUST seguir siendo renderizables sin error (los campos nuevos son opcionales con degradación elegante).
- **FR-016**: El comportamiento actual para resultados de válidas de Copa (etiquetas "V{n}") MUST preservarse sin cambios.

### Key Entities

- **Snapshot de métricas del boletín**: estructura persistida por boletín con bloques de email y bloques solo-PDF; gana campos derivados (promedio semanal de horas, estado de cumplimiento LTAD, focos agrupados, etiqueta de racha) manteniendo compatibilidad con snapshots previos.
- **Resultado de carrera del mes**: posición, tiempo, gap, tipo de serie (copa/campeonato), nivel (departamental/nacional) y etiquetas corta/legible ya calculadas; la etiqueta es la identidad visible del evento.
- **Familia de habilidad**: agrupación temática de focos técnicos (alineada con la taxonomía de habilidades existente del club) usada solo para presentación; no altera las sesiones.
- **Consejo de apoyo en casa**: contenido estático parametrizado por banda etaria y rotado por mes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los resultados de campeonato en boletines regenerados muestran su etiqueta propia (CD/CN) en todas las apariciones (tarjeta destacada, tablas, gráficos); cero apariciones de "V1" para campeonatos.
- **SC-002**: El 100% de las valoraciones narrativas (IA y respaldo) usan el género gramatical correcto según el sexo registrado del atleta; cero casos de "su hijo" para atletas femeninas en una muestra de regeneración de todos los atletas activos.
- **SC-003**: Cero secciones vacías en los PDFs generados: la galería aparece con imágenes, con placeholder informativo, o no aparece.
- **SC-004**: Un padre sin contexto técnico puede identificar la próxima competencia (fecha y sede) y la categoría de su hija/hijo leyendo el boletín, sin códigos ni fechas ISO — verificado por revisión del entrenador sobre el boletín regenerado.
- **SC-005**: La sección "Focos del mes" contiene como máximo 8 grupos legibles (vs ~15 títulos crudos actuales) con conteo de sesiones por grupo.
- **SC-006**: La página 1 del PDF regenerado utiliza al menos el 70% de su área de contenido.
- **SC-007**: Los boletines históricos existentes se renderizan sin error tras el cambio (verificación sobre los snapshots persistidos en el entorno de desarrollo).

## Assumptions

- La regla LTAD aplicable es "horas semanales ≤ edad del atleta" (ya establecida en la documentación del club); el promedio semanal se calcula como horas del mes ÷ (días del mes ÷ 7).
- El rango de referencia de RPE para fase de base en escala OMNI 0–10 es ≈3–5; la referencia mostrada es informativa, no un juicio del mes del atleta.
- La agrupación de focos usa la taxonomía de habilidades A–H ya existente en la biblioteca de técnica del club (feature 018) como familias de presentación, con mapeo por palabras clave sobre el texto del foco; no requiere reetiquetar sesiones históricas.
- El mapeo de códigos de categoría cubre los códigos de la Copa Valle conocidos (PJUV/INF/JUV, A/B, M/F); códigos futuros se muestran crudos hasta ampliar el mapeo.
- La rotación mensual de tips de apoyo es determinista (derivada del número de mes), sin aleatoriedad, para que regenerar el mismo boletín produzca el mismo documento.
- No se requiere migración de base de datos: los cambios son de construcción del snapshot y de presentación; los snapshots antiguos se renderizan con degradación elegante ("dato no disponible" donde falte un campo nuevo).
- Fuera de alcance: informe mensual técnico (spec 022), ingestión de resultados, módulo de competencias, y cualquier cambio en la lógica de puntos o rankings.
- El correo electrónico reutiliza los mismos bloques de datos; los cambios de formato de fecha y etiquetas aplican también al email, pero la galería, gráficos y tabla antropométrica son solo-PDF (sin cambio de canal).
