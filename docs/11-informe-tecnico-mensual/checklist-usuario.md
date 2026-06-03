# ✅ Checklist de pruebas manuales — Informe Técnico Mensual

*(vista del entrenador, como usuario final)*

Esta es la guía para probar el módulo **a mano, desde la interfaz**, sin nada
técnico (ni Docker, ni variables de entorno). Para la versión de desarrollo
(stack levantado, datos sembrados) ver `e2e.md` §3.

## Antes de empezar

- [ ] Entrar al app donde esté publicado (Render o local) en el navegador.
- [ ] Tener tu **cuenta de entrenador** (local seed: `entrenador@trochyruta.com` / `Coach2026!`).
- [ ] Que exista **un mes con actividad ya registrada**: varias sesiones,
      asistencia marcada y rúbricas. El informe resume eso; sin datos, sale
      vacío. Idealmente un mes ya cerrado.
- [ ] Para la parte de competencia: al menos **una válida de ese mes** con
      resultados cargados.

> ⏱ En Render (plan gratis) el primer clic tras ~15 min inactivo tarda ~50s en
> despertar. No es un error, espera.

---

## A. Datos del proyecto *(una sola vez por club)*

- [ ] Menú lateral → **Reportes mensuales**.
- [ ] Clic en **Datos del proyecto**.
- [ ] Llenar: nombre del proyecto, entidad ejecutora, responsable, propósito,
      objetivo general, territorio.
- [ ] Agregar 2-3 **objetivos específicos**; quitar uno para probar.
- [ ] **Guardar** → confirma mensaje de éxito.
- [ ] Recargar la página → los datos siguen ahí (se guardó de verdad).

## B. Generar el informe del mes

- [ ] En **Reportes mensuales**, botón **+ Generar reporte**.
- [ ] Elegir **año y mes** del mes cerrado → confirmar.
- [ ] Te lleva al detalle del informe de ese mes.
- [ ] En la lista, el informe aparece con badge **Borrador**.

## C. Revisar métricas *(se calculan solas)*

- [ ] Sesiones **ejecutadas** y **canceladas** del mes.
- [ ] **Asistencia por atleta** (presente / tarde / justificado / ausente / lesionado).
- [ ] Promedios de **rúbrica** (esfuerzo / actitud / técnica).
- [ ] **Focos técnicos** trabajados.
- [ ] Que los números cuadren con lo que registraste ese mes.

## D. Bloques narrativos *(IA + tu edición)*

Aparecen 7 bloques **en este orden**:

1. Objetivo del período
2. Desarrollo de actividades
3. Resultados obtenidos
4. Conclusiones
5. Apoyos materiales y salidas
6. Análisis del grupo
7. Participación en competencia

- [ ] En un bloque, **Generar con IA** → aparece texto y el aviso
      *"Texto generado por IA — revísalo antes de aprobar."*
- [ ] **Regenerar** el mismo bloque → el texto propuesto cambia.
- [ ] **Editar** el texto a mano y **Guardar** → el botón pasa a *Guardado*.
- [ ] Recargar → tu edición persiste.
- [ ] 🔒 Revisar que el texto IA **no mencione nombres de menores** ni juicios
      individuales (regla de privacidad). Si aparece un nombre real → reportarlo.

## E. Aprobar

- [ ] Botón **Aprobar**.
- [ ] El badge cambia a **Aprobado**.
- [ ] Los bloques quedan **deshabilitados**: ya no se puede editar ni regenerar.

## F. PDF

- [ ] Botón **Descargar PDF**.
- [ ] Se descarga `informe-tecnico-AÑO-MES.pdf`.
- [ ] Abrirlo y comparar con lo de pantalla: portada del proyecto, contexto/
      territorio, métricas, podios de competencia, bloques narrativos, registro
      fotográfico.
- [ ] Pie de página con aviso **Ley 1581** (distribución restringida).
- [ ] Si descargaste el PDF en **Borrador** (antes de aprobar): debe llevar marca
      **BORRADOR**.

## G. Sesiones con tipo y objetivos *(alimenta el informe)*

- [ ] Menú → **Entrenamientos** → crear/editar una sesión.
- [ ] Verificar campos **Tipo de sesión** y **Objetivos**.
- [ ] Guardar → esos datos se reflejan luego en el informe del mes.

---

## H. 🔒 Privacidad — vista del padre/madre

*(usa una cuenta de padre; local seed: `padre@trochayruta.com` / `Parent2026!`)*

- [ ] El menú del padre **NO** muestra "Reportes mensuales".
- [ ] Escribir a mano en el navegador la URL del informe
      (`/training/reports/2026/5`) → te **redirige a tus atletas**
      (`/my-athletes`). El informe es interno del club.
- [ ] El padre **no ve** métricas, ni bloques, ni Aprobar, ni Descargar PDF.

---

## I. Si algo falla, anotar

- [ ] Qué pantalla, qué botón, qué esperabas vs. qué pasó.
- [ ] Captura de pantalla.
- [ ] Hora aproximada (para cruzar con logs).
