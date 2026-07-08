# Feature Specification: Alinear el Informe Técnico Mensual al formato institucional aprobado

**Feature Branch**: `022-align-monthly-report-format`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Que el reporte que actualmente se elabora (Informe Técnico Mensual del club) tenga como resultado el informe generado según el formato institucional aprobado: misma estructura, secciones, contenido enriquecido y registro fotográfico del documento de referencia."

## Contexto

El club genera hoy un "Informe Técnico Mensual" (borrador) para el Grupo de Alto Rendimiento. Existe además un **formato institucional aprobado** (referencia: "Formato Informe Mensual Técnico") usado en meses anteriores, y un **informe de referencia ya validado** que muestra el resultado esperado: encabezado de proyecto completo, secciones nombradas y ordenadas, detalle sesión por sesión, resultados de competencia desglosados por jornada, asistencia y rúbrica por atleta, y un registro fotográfico agrupado.

El informe que se genera actualmente presenta brechas frente a ese resultado esperado: campos de encabezado vacíos, bloques de narrativa sin contenido (queda en borrador), ausencia del detalle enriquecido de sesiones y competencia, y evidencia fotográfica no organizada como registro. Esta funcionalidad busca cerrar esas brechas para que **el reporte generado coincida con el formato aprobado y quede listo para aprobación** sin reestructuración manual.

## Clarifications

### Session 2026-07-03

- Q: ¿Cómo debe asegurar el sistema que los insumos existan antes de generar el informe? → A: Solo marcas inline "—" en el documento; sin checklist previo, sin bloqueo y sin cambios en otras pantallas para preparación de insumos.
- Q: ¿Cómo se asigna cada foto a los grupos del registro fotográfico (Alto Rendimiento, Competencia, Actividades Conjuntas)? → A: Derivación automática desde datos existentes (tipo de sesión / vínculo con competencia); sin etiquetado manual ni cambios en la pantalla de upload.
- Q: ¿Qué significa "jornada/modalidad" en los datos de competencia? → A: Cada evento de competencia del período equivale a una jornada; el desglose se construye automáticamente agrupando por evento y categoría, sin campos nuevos ni cambios en el import.
- Q: ¿Requiere cambios la creación de sesiones para alimentar el informe? → A: Sin cambios; el wizard actual ya captura fecha, hora, lugar, foco técnico, asistencia y rúbricas como campos obligatorios.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Informe generado que coincide con el formato aprobado (Priority: P1)

Como entrenador, cuando genero el Informe Técnico Mensual de un período, obtengo un documento cuya estructura, orden y nombres de sección coinciden con el formato institucional aprobado, con el encabezado de proyecto y los bloques de narrativa completos, de modo que solo deba revisarlo y aprobarlo.

**Why this priority**: Es el núcleo del requerimiento. Sin la estructura y el contenido alineados, el informe sigue exigiendo trabajo manual de reformateo y no puede aprobarse tal como se genera.

**Independent Test**: Generar el informe de un período con datos existentes y verificar que el documento producido incluye, en el orden del formato aprobado, el encabezado de proyecto (Nombre del proyecto, Entidad ejecutora, Período, Responsable) y las secciones de actividades ejecutadas del Grupo de Alto Rendimiento (Objetivo, Plan de entrenamiento, Desarrollo de actividades, Participación en competencia, Resultados obtenidos, Conclusiones), sin campos obligatorios vacíos cuando el perfil del proyecto está completo.

**Acceptance Scenarios**:

1. **Given** un perfil de proyecto del club completo y un período con sesiones registradas, **When** el entrenador genera el Informe Técnico Mensual, **Then** el encabezado muestra Nombre del proyecto, Entidad ejecutora, Período y Responsable con valores reales (ningún campo obligatorio en "—").
2. **Given** un período con narrativa generada, **When** se produce el documento, **Then** las secciones aparecen con los nombres y el orden del formato aprobado y ninguna sección obligatoria queda vacía.
3. **Given** un período sin narrativa aún generada, **When** se produce el documento, **Then** el informe se marca claramente como "Borrador / pendiente de aprobación" e indica qué secciones faltan por completar.

---

### User Story 2 - Contenido enriquecido de sesiones, asistencia y competencia (Priority: P2)

Como entrenador, quiero que el informe incluya el detalle enriquecido que respalda el trabajo del mes: tabla sesión por sesión (fecha, hora, foco técnico, lugar y asistencia), asistencia y rúbrica por atleta, y los resultados de competencia desglosados por jornada (un evento del período = una jornada), para evidenciar el proceso completo ante la dirección.

**Why this priority**: Aporta el sustento verificable del informe. Es de alto valor pero depende de que la estructura base (P1) exista.

**Independent Test**: Generar el informe de un período con sesiones y una competencia registradas y verificar que aparecen la tabla de detalle de sesiones, la tabla de asistencia por atleta y el desglose de competencia por jornada, con una nota que distingue eventos con y sin puntos.

**Acceptance Scenarios**:

1. **Given** sesiones ejecutadas con lugar y asistencia, **When** se genera el informe, **Then** se muestra una tabla con una fila por sesión (fecha, hora, foco técnico, lugar, asistencia).
2. **Given** atletas con asistencia y rúbricas del período, **When** se genera el informe, **Then** se muestra la tabla de asistencia y rúbrica por atleta con los totales del club.
3. **Given** competencias con resultados en el período, **When** se genera el informe, **Then** los resultados se desglosan por jornada (evento) y categoría, y se indica si cada evento otorga o no puntos.

---

### User Story 3 - Registro fotográfico agrupado (Priority: P3)

Como entrenador, quiero incorporar la evidencia fotográfica del mes organizada como "Registro Fotográfico" agrupado por programa/sección (p. ej. Grupo de Alto Rendimiento, Competencia, Actividades Conjuntas), para que el informe cierre con el respaldo visual en el mismo formato de la referencia.

**Why this priority**: Complementa el informe y mejora su presentación institucional, pero no bloquea la aprobación del contenido técnico.

**Independent Test**: Adjuntar evidencia fotográfica a un período y verificar que el informe la presenta agrupada por sección con sus rótulos, sin exponer datos de menores fuera del club.

**Acceptance Scenarios**:

1. **Given** fotos asociadas al período, **When** se genera el informe, **Then** aparecen en un registro fotográfico agrupado por sección con títulos y espacios consistentes.
2. **Given** un período sin fotos cargadas, **When** se genera el informe, **Then** el registro fotográfico muestra espacios reservados claramente identificados para completar.

---

### Edge Cases

- ¿Qué ocurre cuando el perfil del proyecto del club está incompleto (sin Nombre del proyecto o Responsable)? El informe debe generarse igualmente, marcar los campos faltantes de forma visible y no quedar bloqueado.
- ¿Qué ocurre en un período sin competencias? La sección de competencia debe omitirse o indicar "sin competencias en el período", sin dejar tablas vacías.
- ¿Qué ocurre con una competencia sin puntos (p. ej. departamental)? Debe reflejarse la posición por categoría y aclararse que no otorga puntos.
- ¿Qué ocurre con atletas lesionados o con asistencia 0? Deben aparecer en la tabla con su estado, sin romper los totales.
- ¿Cómo se maneja el acceso de padres? Los padres no deben ver narrativa interna, resultados con nombres de menores ni el PDF técnico completo.
- ¿Qué ocurre si se regenera un solo bloque de narrativa? El resto del informe y su estructura aprobada deben permanecer intactos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El informe generado MUST presentar un encabezado de proyecto con Nombre del proyecto, Entidad ejecutora, Período y Responsable, poblados desde el perfil de proyecto del club cuando exista.
- **FR-002**: El informe MUST organizar las secciones con el mismo orden y nomenclatura del formato institucional aprobado, incluyendo para el Grupo de Alto Rendimiento: Objetivo, Plan de entrenamiento, Desarrollo de actividades, Participación en competencia, Resultados obtenidos y Conclusiones.
- **FR-003**: El informe MUST incluir un resumen de sesiones del período (sesiones ejecutadas/canceladas, volumen, promedio semanal y promedios de rúbrica de esfuerzo, actitud y técnica).
- **FR-004**: El informe MUST incluir una tabla de detalle sesión por sesión con fecha, hora, foco técnico, lugar y asistencia.
- **FR-005**: El informe MUST incluir una tabla de asistencia y rúbrica por atleta con los totales del club.
- **FR-006**: El informe MUST presentar los resultados de competencia del período desglosados por jornada, donde cada evento de competencia del período equivale a una jornada y el desglose se agrupa automáticamente por evento y categoría (sin campos nuevos de datos), e indicar explícitamente si el evento otorga o no puntos.
- **FR-007**: El informe MUST incluir un registro fotográfico agrupado por sección/programa, con espacios reservados cuando falten fotos. La sección de cada foto se deriva automáticamente de los datos existentes de la sesión asociada (tipo de sesión, vínculo con competencia); no hay etiquetado manual de fotos.
- **FR-008**: El sistema MUST distinguir el estado del informe entre "borrador/pendiente de aprobación" y "aprobado", y reflejarlo de forma visible en el documento.
- **FR-009**: El sistema MUST permitir generar y regenerar bloques de narrativa individuales sin alterar la estructura aprobada ni el resto del contenido.
- **FR-010**: El sistema MUST preservar la privacidad de menores de edad: la narrativa interna, los resultados con nombres y el documento técnico completo son exclusivos de coach/admin del club; los padres reciben una vista restringida.
- **FR-011**: El informe generado MUST poder producirse en un formato descargable y editable adecuado para revisión y aprobación institucional.
- **FR-012**: Cuando falten datos obligatorios (p. ej. campos del encabezado), el sistema MUST señalarlos de forma visible en el documento en lugar de omitirlos silenciosamente. La generación nunca se bloquea por insumos faltantes y no se requiere checklist previo ni modificaciones a otras pantallas para preparación de insumos.

### Key Entities *(include if feature involves data)*

- **Informe Técnico Mensual**: documento del período por club; agrupa encabezado de proyecto, bloques de narrativa, métricas de sesiones, asistencia, resultados de competencia y evidencia fotográfica; tiene un estado (borrador/aprobado).
- **Perfil de Proyecto del Club**: datos institucionales estables (Nombre del proyecto, Entidad ejecutora, Responsable) usados para poblar el encabezado.
- **Sesión de entrenamiento**: unidad con fecha, hora, foco técnico, lugar, asistencia y rúbricas; alimenta el resumen y el detalle de sesiones.
- **Resultado de competencia**: participación de atletas por evento, categoría, posición y puntos; una "jornada" del informe corresponde a un evento de competencia del período.
- **Bloque de narrativa**: texto por sección (objetivo, desarrollo, resultados, conclusiones, análisis del grupo, competencia, apoyos materiales) editable/regenerable.
- **Evidencia fotográfica**: imágenes del período asociadas a sesiones; su sección/programa en el registro fotográfico se deriva automáticamente del tipo de sesión o del vínculo con competencia (sin atributo manual de sección).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las secciones del formato institucional aprobado están presentes, en el orden correcto, en el informe generado para un período con datos completos.
- **SC-002**: Cuando el perfil de proyecto del club está completo, 0 campos obligatorios del encabezado aparecen vacíos ("—") en el informe generado.
- **SC-003**: El entrenador puede obtener un informe listo para aprobación sin realizar reestructuración manual de secciones (0 pasos de reformateo).
- **SC-004**: Para un período con sesiones y una competencia registradas, el informe incluye la tabla de detalle de sesiones, la tabla de asistencia por atleta y el desglose de competencia por jornada en el 100% de los casos.
- **SC-005**: En vistas de padres, 0 documentos exponen narrativa interna, nombres de menores en resultados o el PDF técnico completo.
- **SC-006**: El tiempo del entrenador para dejar un informe listo para aprobación se reduce de forma significativa respecto al proceso manual actual (línea base a medir; objetivo ≥ 50% de reducción).

## Assumptions

- El formato institucional aprobado de referencia (documento "Formato Informe Mensual Técnico" y el informe de referencia validado) es la fuente de verdad para estructura, orden y nomenclatura de secciones.
- El alcance de esta funcionalidad se centra en el informe del **Grupo de Alto Rendimiento**; las secciones institucionales de nivel dirección (Contexto del Proyecto, Información del Territorio, Población Atendida) y el programa Escuela de Teteros se consideran responsabilidad de la dirección y quedan fuera del alcance del rol entrenador, aunque el encabezado y la numeración del formato se conservan.
- Los datos de sesiones, asistencia, rúbricas y resultados de competencia ya existen en el sistema y son la fuente para poblar el informe. La creación de sesiones no cambia: el wizard actual ya captura como obligatorios fecha, hora, lugar, foco técnico, asistencia y rúbricas — todos los insumos que el informe requiere de las sesiones.
- No se modifican otras pantallas para preparación de insumos: no hay checklist previo a la generación ni bloqueo por datos faltantes; los faltantes se señalan inline en el documento (FR-012).
- El perfil de proyecto del club es la fuente para el encabezado; puede estar incompleto y el informe debe tolerarlo.
- Las reglas de privacidad de menores vigentes (coach/admin vs. padres) se mantienen sin cambios en su intención.
- La evidencia fotográfica puede cargarse por período; cuando no exista, se muestran espacios reservados.
