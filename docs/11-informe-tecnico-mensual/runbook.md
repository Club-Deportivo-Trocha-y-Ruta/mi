# Informe Técnico Mensual — Runbook del coach

**Audiencia:** entrenador (coach) y administrador del club.
**Objetivo:** que al cerrar **junio 2026** tengas todos los insumos capturados durante el mes y, con pocos clics, generes el PDF del Informe Técnico Mensual (estilo informe del jefe), incluyendo el capítulo cualitativo del grupo de alto rendimiento.

Detalle técnico en [`design.md`](design.md). Visión general en [`workflow.md`](workflow.md).

---

## Idea general

El informe se arma con dos clases de trabajo:

1. **Durante el mes** capturas insumos a medida que ocurren (sesiones, fotos, asistencia, rúbricas, resultados de la válida).
2. **Al cerrar el mes** configuras una vez el perfil del proyecto, generas el reporte, revisas/editas cada bloque, apruebas y descargas el PDF.

La IA pre-redacta la narrativa con datos **agregados** (nunca nombres de menores). Tú la editas y apruebas: el PDF final siempre pasa por tu revisión.

---

## Parte A — Durante el mes (junio): capturar insumos

### A1. Registrar cada sesión con tipo y objetivos

Al crear una sesión en el formulario, completa además:

- **Tipo de sesión (`session_kind`)**: clasifica la actividad.
  - `entrenamiento` — sesión técnica/física habitual del grupo.
  - `actividad_conjunta` — actividad con varios grupos, familias o aliados.
  - `salida` — salida o rodada fuera de la sede.
  - `otro` — cualquier otra actividad relevante para el informe.
- **Objetivos (`objectives`)**: una o dos frases con el foco de la sesión.

> El tipo alimenta la separación del PDF: las sesiones de `entrenamiento` van al capítulo del grupo de alto rendimiento; `actividad_conjunta` y `salida` van al capítulo de actividades conjuntas y salidas.

### A2. Subir fotos consentidas

Sube fotos a las sesiones desde la galería de media. Usa **solo imágenes con consentimiento informado** (Ley 1581/2012). Las imágenes alimentan el "Registro fotográfico" del informe, que es de distribución restringida.

### A3. Registrar asistencia y rúbricas

Por sesión, marca asistencia de cada atleta y completa la rúbrica (esfuerzo, actitud, técnica) y el RPE cuando aplique. Estos datos:

- Sustentan el cálculo agregado (porcentaje de asistencia, nivel técnico del grupo).
- Alimentan, ya agregados y anonimizados, la narrativa que la IA redacta.

> La IA solo ve agregados y pseudónimos: nunca ve nombres reales.

### A4. Ingerir resultados de la válida

Cuando se publiquen los PDFs oficiales de la válida del mes (en junio: **CD — Cto. Departamental, 12-jun, Ginebra**), ingiere los resultados con el flujo de Copa Valle (módulo de resultados, Fase 1.7 / módulo Competencias). El helper de competencia tomará automáticamente los **podios del club** de los eventos cuya fecha cae dentro del mes del informe.

---

## Parte B — Al cerrar el mes: generar y aprobar el informe

### B1. Configurar el perfil del proyecto (una sola vez)

En **Datos del proyecto** (`ProjectProfilePage`), completa una vez por club:

- Nombre del proyecto, entidad ejecutora, responsable del informe.
- Propósito, objetivo general, objetivos específicos (lista).
- Localización y descripción del territorio.

Esta metadata encabeza **todos** los informes; no hace falta repetirla cada mes. Si algo cambia, edítalo y se reflejará en el próximo PDF.

### B2. Generar el reporte del período

Genera el reporte del mes cerrado (no se permite el mes en curso ni meses futuros). La generación:

- Pre-redacta con IA los seis bloques narrativos (objetivo, desarrollo, resultados, conclusiones, apoyos materiales, análisis del grupo).
- Toma automáticamente los podios del club del mes (bloque de competencia).
- Deja el reporte en estado **`draft`**.

Si un bloque falla (timeout o rechazo de privacidad), el resto se genera igual; podrás regenerar el bloque fallido individualmente.

### B3. Revisar y editar cada bloque

En el detalle del reporte (`ReportDetailPage`, modo editor por bloques):

- Lee el borrador de cada bloque y **edita el texto final** (`final_text`).
- Si un borrador no te convence, usa **regenerar** ese bloque: la IA produce un nuevo borrador y se preserva tu edición previa si ya la habías cambiado.
- Presta atención especial al bloque **Análisis del grupo de alto rendimiento** (`analisis_grupo`): es el capítulo cualitativo que el jefe sumará al informe consolidado.

> Regla de privacidad: la IA nunca escribe nombres de menores. Si necesitas mencionar un podio con nombre, eso ya viene del bloque estructurado de competencia, no de la narrativa.

### B4. Aprobar

Cuando los bloques estén listos, **aprueba** el reporte (`draft → approved`). La aprobación es de un solo sentido (no hay reversión a borrador). Mientras esté en `draft`, el PDF lleva un banner **BORRADOR**.

### B5. Descargar y distribuir el PDF

Descarga el PDF (template técnico). El documento incluye portada institucional, contexto, territorio, actividades del grupo de alto rendimiento, competencia con podios, actividades conjuntas, apoyos materiales, análisis del grupo, conclusiones y registro fotográfico.

El PDF es de **distribución restringida** (coach/admin) y lleva el aviso de Ley 1581/2012: contiene datos de menores, uso exclusivo del equipo técnico, no distribuir externamente. El coach lo descarga y lo distribuye manualmente (no hay envío automático por email).

---

## Checklist de cierre de mes

- [ ] Todas las sesiones del mes registradas con `session_kind` y `objectives`.
- [ ] Fotos consentidas subidas a las sesiones.
- [ ] Asistencia y rúbricas completas.
- [ ] Resultados de la válida del mes ingeridos.
- [ ] Perfil del proyecto del club configurado (una sola vez).
- [ ] Reporte del mes generado (estado `draft`).
- [ ] Cada bloque revisado y editado; bloque `analisis_grupo` afinado.
- [ ] Reporte aprobado (`approved`).
- [ ] PDF descargado y distribuido por canal controlado.

---

## Notas

- **Población Atendida** no aparece en el informe (omitida por decisión del club). El documento se limita al grupo de alto rendimiento, sin segmentación por programa.
- Los **padres** no ven la narrativa interna (`narrative_blocks`) ni los resultados de competencia (`competition_results`); su vista es un resumen filtrado.
- Calendario de junio relevante: **CD — Cto. Departamental, 12-jun, Ginebra** (válida A, tapering completo 7 días).
