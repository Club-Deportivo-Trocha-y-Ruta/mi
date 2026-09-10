# Gobernanza multi-entrenador — registro de cambios, atribución e informes por entrenador

Feature 041. Rama `feat/041-multi-coach-governance`. Añade un segundo entrenador
por club con visibilidad total (sin portafolios), y resuelve lo que eso rompe
hoy: nada queda atribuido, borrar un atleta destruye evidencia, dos personas
pueden pisarse el trabajo, y las corridas de IA y las importaciones quedan
bloqueadas para quien no las creó.

## 1. Qué hace, por historia de usuario

**US1 — Todo cambio queda firmado (P1).** Cada creación, edición, aprobación,
envío, cancelación, archivado o borrado sobre un dato del club —perfil,
medición, sesión, asistencia, calificación, evento de calendario, informe
mensual, boletín familiar, corrida de IA, importación de resultados, cuenta de
personal— queda registrado con actor, momento, registro afectado y campos
cambiados. Descargar o enviar un documento con datos de un menor (PDF de
crecimiento, DOCX de autorización médica, boletín) también queda registrado.
Las lecturas simples no. Un entrenador o administrador abre un historial del
club en español llano ("Ana Coach aprobó el informe mensual de marzo"),
filtrable por persona, período, tipo de registro y atleta; las familias nunca
lo ven, y ninguna entrada expone nombre, fecha de nacimiento, medición o texto
narrativo de un menor.

**US2 — Eliminar un atleta conserva la evidencia (P1).** Quitar un atleta lo
archiva, no lo destruye: desaparece de listas, tablero, informes, boletines,
contextos de IA y la vista de la familia, pero el consentimiento parental, las
mediciones y el historial siguen íntegros y legibles para un administrador,
que puede restaurarlo. Una cuenta de entrenador o administrador con actividad
registrada no se puede borrar, solo desactivar, y su nombre sigue resolviendo
sobre sus acciones pasadas.

**US3 — El segundo entrenador se vincula desde la app (P1).** Un administrador
crea al entrenador nuevo desde una pantalla "Personal del club" con nombre,
correo y club obligatorio; el formulario rechaza el envío sin club. El
entrenador nuevo ve desde su primer ingreso exactamente lo que ve el existente.
El administrador lista personal activo e inactivo y puede desactivar cuentas;
un entrenador no puede crear, editar ni desactivar a otro entrenador o
administrador.

**US4 — Sesiones co-dirigidas, y la familia oye el nombre correcto (P2).** Una
sesión lleva el conjunto de entrenadores a cargo (mínimo uno, siempre). Cuando
se edita, ejecuta o cancela, el correo a la familia nombra a quien actuó, no a
quien la planeó. Asistencia, calificaciones y retroalimentación registran quién
las puso y quién las editó por última vez. Quitar un atleta del roster archiva
sus entradas en vez de destruirlas.

**US5 — Ningún entrenador sobrescribe en silencio al otro (P2).** El estudio
del boletín usa concurrencia optimista: guardar sobre una versión no vista se
rechaza con un mensaje de conflicto y la opción de recargar, sin perder el
trabajo local. La nota del entrenador queda con autor y fecha, visible solo a
entrenadores; la familia sigue viendo la voz institucional. Regenerar un
informe mensual aprobado conserva quién lo aprobó y cuándo ("previamente
aprobado por"), y la regeneración misma queda registrada.

**US6 — Cualquier entrenador actúa sobre las corridas de IA y las
importaciones del club (P2).** Se reemplaza el candado por autor por una única
regla de alcance por club: cualquier entrenador del club decide una corrida
que otro dejó esperando, o continúa una importación que otro empezó. Cada
corrida y cada importación muestra quién la lanzó y, si aplica, quién decidió.
El gasto de IA de los últimos 30 días se muestra por entrenador además de en
total, y el mensaje de presupuesto agotado nombra el período.

**US7 — Informes por club y por entrenador (P3).** Los informes de club
(informe técnico mensual, tablero, panorama de temporada) quedan exactamente
igual. Se añade una vista de actividad por entrenador y período: sesiones
lideradas o co-lideradas, entradas registradas, corridas de IA lanzadas,
operaciones de resultados, documentos aprobados o enviados, con enlace al
historial filtrado de esa persona. Toda superficie que hoy muestra "creado
por" pasa de un identificador numérico crudo al nombre visible de la persona.

**US8 — El historial se conserva dos temporadas y se purga a propósito (P3).**
Las entradas se conservan 24 meses; nada las purga automáticamente dentro de
la app. Un administrador corre un procedimiento (CLI) que primero previsualiza
cuántas entradas mayores a 24 meses se eliminarían y, con confirmación
explícita, las elimina y registra la purga misma como una entrada de
historial.

## 2. Cumplimiento de la constitución

**I. Calidad y mantenibilidad del código — cumple, con una reserva.** El
código nuevo pasa `ruff` y `tsc --noEmit`; los hallazgos cosméticos que la
primera revisión detectó en dos módulos de prueba nuevos (imports sin usar,
`E402`) quedaron limpios en la segunda corrida. No se volvió a correr un
`ruff check` completo de cierre después de esa limpieza para confirmar el
estado final exacto frente a `main` (que tampoco está limpio hoy, así que no
es una compuerta que hoy pase en ningún lado del repositorio). La revisión
humana de al menos un revisor distinto del autor, que exige este principio,
está pendiente de que se abra el PR — este documento es su insumo.

**II. Estándares de prueba (NO NEGOCIABLE) — cumple parcialmente; el hueco es
de entorno, no de disciplina.** Lo que sí se corrió: la suite de backend se
midió diferencialmente contra un *worktree* limpio de `main` en cada corrida
nocturna y cerró en **cero regresiones** (220 fallas conocidas y ambientales
—el fixture `client` necesita MySQL real, que no existe aquí— idénticas a las
224 de `main`, con más pruebas pasando en la rama); el frontend cerró con
`npm run typecheck` limpio y la suite de `vitest` en verde. Cada corrección de
bug de esta ventana trae su prueba de regresión (por ejemplo,
`test_race_analysis_launch_scope.py` para las fugas de club H1/H2, o el ajuste
de fecha "futura" ya pasada en `test_training_session_notifications.py`). Lo
que **no se pudo ejecutar en este entorno**, sin Docker ni MySQL:

- La vía `pytest -m mysql`: la migración única de esta feature nunca se
  reaplicó contra una base `_test` real (T027 diferida), y la prueba de
  concurrencia optimista bajo bloqueo de fila real de InnoDB
  (`test_newsletter_concurrency.py::test_two_sessions_only_one_update_takes_effect`)
  está escrita y se salta; sqlite no reproduce ese bloqueo, así que la
  atomicidad real de la reserva de versión de US5 no está verificada.
- Los cinco specs de Playwright (T092: `staff-admin`, `athlete-archive`,
  `session-coaches`, `newsletter-conflict`, `coach-activity`) no se pudieron
  escribir contra un stack en ejecución real: un defecto de migración
  preexistente y ajeno a esta feature impide levantar una base de datos
  nueva. Queda sin verificar en vivo todo flujo de dos navegadores (el
  segundo entrenador viendo en tiempo real lo que hizo el primero), la
  aserción de correo contra MailHog, y la navegación por teclado end-to-end
  de las pantallas nuevas.
- La mitad dinámica de la compuerta FR-009 (que una ruta auditada escriba de
  verdad su fila al ejercitarse) recoge hoy **cero casos**: nada declara
  todavía el constructor de petición que el contrato exige, así que la
  garantía de instrumentación real sigue apoyada solo en el análisis estático
  de alcanzabilidad, no en ejecución.
- T078 (pruebas de backend del alcance por club de US6) no se escribió.
- T080 (revisión de seguridad de US6) sí se ejecutó y encontró dos fugas
  altas que ya están corregidas y con prueba de regresión, pero deja cinco
  hallazgos menores abiertos (§5); la tarea sigue sin marcar porque la
  superficie no está cerrada del todo.

**III. Consistencia de experiencia — cumple en lo construido, sin
verificación final en vivo.** El texto de producto nuevo (selector de
entrenadores de sesión, diálogo de conflicto de la bitácora, página de
actividad por entrenador, tabla de gasto por entrenador) está en español
neutro con tildes completas; los componentes reutilizan `shadcn/ui`; los
formularios siguen React Hook Form + Zod; las páginas nuevas traen su propia
prueba `jest-axe`. Falta la revisión de integración en el stack de desarrollo
(T086) que confirma nav por rol, estados de carga/vacío/error en vivo y
accesibilidad fuera del componente aislado.

**IV. Presupuestos de rendimiento — sin verificar en esta ventana.** El
tamaño de los tres bundles perezosos nuevos contra el presupuesto de 150 KB
gzip por ruta, y que el chunk de entrada no haya regresado, es exactamente lo
que mide T086 (abierta). El único ítem de presupuesto conocido, el chunk de
entrada preexistente de 336 KB por encima de los 250 KB, es anterior a esta
feature, está documentado en `plan.md` (Complexity Tracking) y esta feature
no lo agrava —solo añade rutas perezosas—, pero tampoco lo corrige.

**V. Salvaguardas de evaluación psicológica juvenil — no aplica.** Esta
feature no toca ningún instrumento psicológico; añade atribución y registro
alrededor de datos que ya existían. La auditoría obligatoria de privacidad de
datos de menores para la feature completa (T091, `data-privacy-guard`) sigue
sin correr como revisión formal, aunque cada historia trae sus propias
pruebas de invariantes de privacidad (por ejemplo, la matriz de exposición de
la nota del entrenador en US5 se verificó contra el PDF familiar real
renderizado con WeasyPrint, contando cero apariciones del apellido del
entrenador).

## 3. El recorte de FR-010

FR-010 exige que todo registro editable conserve quién lo creó, quién lo
editó por última vez y cuándo. Para cinco tablas de planificación
interna del entrenador —`training_sessions`, `race_events`,
`race_event_roster`, `interval_structures` e `interval_templates`— esta
feature no añade una columna `updated_by_user_id`: las cinco conservan
`created_by_user_id` y `updated_at`, pero el **autor** de la última edición
solo se puede recuperar consultando `audit_log` (indexado por entidad y
fecha), no leyendo una columna.

La razón: ninguna pantalla de esta feature muestra un chip de "última edición
por" para estos cinco tipos de registro —la lista de superficies de FR-013
llega hasta "creado / evaluado / generado / aprobado / importado por", nunca
"editado por"—, y cada ruta que muta estas tablas ya queda instrumentada en la
misma transacción de la escritura. Añadir las cinco columnas es barato en DDL,
pero no gratis: cada camino de escritura tendría que fijarlas, y un camino que
lo olvide deja una columna que calladamente contradice el historial —una
segunda fuente de verdad para un hecho que el historial ya tiene, el mismo
argumento que llevó a rechazar `archived_by_user_id` redundante en otra parte
del diseño. Se rechazó mientras no exista ningún lector de ese dato; se
revisa el día que se diseñe la primera pantalla de "última edición por" para
una sesión, un evento de carrera o una estructura de intervalos. El costo
aceptado: consultar el autor cuesta una búsqueda en el historial en vez de una
lectura de columna, y ese dato desaparece cuando la purga de 24 meses (FR-030)
borra la entrada.

## 4. Decisiones operativas abiertas (para el dueño)

| Decisión | Recomendación registrada | Por qué importa |
|---|---|---|
| Alcanzabilidad de la purga programada: los runners de GitHub Actions tienen IP rotativa y el MySQL de Hostinger está en lista blanca por IP, así que el job mensual de Actions puede no alcanzar la base de datos. | Publicar el CLI y el runbook; correr la purga mensual desde la máquina del dueño (que ya alcanza producción para el boletín); dejar `audit-retention.yml` como `workflow_dispatch` en modo simulación hasta confirmar alcanzabilidad. | FR-030 queda satisfecho por el CLI más el procedimiento documentado; la programación automática es una comodidad, no un requisito. |
| El texto del correo familiar "El entrenador {nombre}" está en masculino (así lo fija FR-025 en el spec). | Mantenerlo como está especificado para esta feature; revisar la redacción cuando se conozca el perfil del segundo entrenador. | Cambiar la redacción de producto es una tarea aparte y barata; no bloquea. |
| `backend/app/routers/race_events.py:606-609,700-703` son exclusivos de entrenador y devuelven 403 a un administrador, distinto del resto de mutaciones de ese router. | Fuera de alcance de esta feature; dejarlo anotado como seguimiento en `docs/technical-notes.md`. | Inconsistencia preexistente, no relacionada con la atribución. |
| El respaldo de aprobación (`monthly_reports.approved_at`) para filas ya aprobadas se llena con `generated_at`, pero `approved_by_user_id` queda en `NULL`. | Aceptar: nunca inventar un aprobador; la interfaz muestra "aprobado (sin registro de autor)" en filas antiguas. | Demuestra la responsabilidad de la Ley 1581 con datos verdaderos únicamente. |

## 5. Decisiones que las corridas desatendidas tuvieron que tomar solas

Registradas en `checklists/integration-review.md`, cada una con su motivo:

- **No aplicar tal cual la restricción de listar personal que proponía la
  revisión anterior.** Negarle al entrenador `GET /api/users?role=coach`
  habría roto la propia feature: el filtro "Entrenador" del historial y el
  selector de entrenadores a cargo de una sesión la necesitan como
  entrenador. Se conservó la lista y se recortó la carga (id, nombre, rol,
  estado; sin datos de contacto), y se blindó con prueba propia que un
  entrenador no pueda crear, editar ni desactivar a otro entrenador o
  administrador.
- **Dejar sin auditar `POST /api/race-analysis/imports/{parse_id}/dry-run`,
  a propósito.** El contrato la describe como una escritura, pero el código
  nunca emite ese cambio de estado: es una corrida en seco sin persistencia.
  Registrar ahí una fila de auditoría anotaría una escritura que no ocurrió,
  contra la regla de que el historial nunca registra lecturas. Resolverlo
  exige cambiar el contrato o el comportamiento del asistente de
  importación, y eso le corresponde al dueño, no a una corrida nocturna.
- **Resolver en la raíz el choque `entity_id = 0` de la fila de purga**, en
  vez de mantener el parche anterior que la reintentaba con `entity_id = 1`.
  Ese parche era peor que el error que evitaba: 1 es el id de una fila de
  auditoría real, así que la evidencia del barrido quedaba apuntando a un
  registro ajeno. Se eximió explícitamente ese único par (`audit_log` ·
  `purge`) de la guarda que exige `entity_id > 0`.
- **Corregir de inmediato, dentro de la misma ventana, las dos fugas de
  datos de una menor que encontró la revisión de seguridad de US6 (H1, H2)**
  en vez de solo dejarlas anotadas: un entrenador de otro club podía lanzar
  un análisis sobre una menor ajena (su nombre llegaba a salir hacia el
  proveedor de IA) y el listado de corridas de un evento entregaba el
  nombre completo de una menor de otro club junto con un id de corrida
  válido y ajeno. Al tratarse de datos de un menor, se priorizó sobre
  continuar con tareas nuevas.
- **Anteponer la unificación de `ActorRef` duplicado al orden estricto del
  runbook** (que mandaba retomar por la primera tarea sin marcar, T030). Era
  precondición de T076, que expone actores en las respuestas de corrida de
  US6; empezar por T030 habría dejado dos frentes de US6 chocando contra una
  clase duplicada.
- **No tocar la unificación de `ActorRef` en la corrida anterior, aunque ya
  estaba identificada**, porque quedaban solo veinticinco minutos de
  ventana, la rama estaba verde y empujada, y tocar tres módulos de esquemas
  sin margen para verificar de verdad era mal negocio; se dejó documentada
  para la corrida siguiente en vez de arriesgar un cambio sin revisar.
  Corregido en la corrida siguiente sin incidentes.
- **Dejar `PRAGMA foreign_keys=ON` sin activar en sqlite** y marcar `xfail`
  documentado la prueba que lo necesitaba, en vez de activarlo: hacerlo
  rompe el sembrado de datos, porque el arnés de prueba crea solo un
  subconjunto de tablas.
- **No aplicar el borrado lógico simétrico de `TrainingSession` al borrar su
  evento de calendario enlazado**, pese a que `session-coaches.md` §7.3 lo
  pide: `data-model.md` (que el propio contrato declara autoritativo sobre
  el código en caso de choque) no le da a `training_sessions` ninguna
  columna `deleted_at`, y la única migración de la feature ya estaba
  verificada contra MySQL real y no se podía revalidar en este entorno. Se
  documentó la contradicción entre los dos contratos en vez de resolverla
  sin poder probar el resultado.

## 6. Tareas que siguen abiertas

| Tarea | Por qué sigue abierta |
|---|---|
> Actualizada el 2026-09-10 tras la verificación local en vivo
> (`checklists/integration-review.md`, sección final). T030, T078, T080, T086, T091,
> T092, T093, T094, T095 y T098 quedaron cerradas; estas son las únicas abiertas:

| Tarea | Por qué sigue abierta |
|---|---|
| T096 | Recorrido del quickstart hecho en el stack aislado (escenarios 2–9 y 12–14 en vivo; 10 y 11 solo por pruebas, sin IA real ni datos de carrera). Falta **SC-002**, la prueba moderada presencial con el entrenador del club. |
| T097 | El humo posdespliegue requiere este PR mergeado y desplegado, y las credenciales del dueño. |

Decisiones que la verificación dejó para el dueño: la ventana read-after-write del commit implícito de `get_db` en el resto de la app (solo se corrigieron las rutas de personal), y la contradicción entre contratos sobre el `DELETE` de personal (403 frente a 409).

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01JGssBDRXKFVRYnRxmEdiPW
