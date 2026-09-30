# Toma antropométrica guiada — guía para el entrenador

Función `specs/048-anthropometry-capture-ux`. Esta guía es para quien mide a los deportistas
con la tableta o el celular. El texto entre comillas angulares («…») es el que se ve en la
aplicación. Detalle técnico en `docs/23-anthropometry-capture/design.md`.

Los nombres y valores de los ejemplos son ficticios.

## 1. Antes de medir

Necesita cuatro cosas sobre una superficie plana:

- Báscula digital.
- Tallímetro de pared.
- Cajón o banco plano para la talla sentado.
- Cinta métrica para la envergadura.

Condiciones de la toma (la aplicación las muestra en «Preparación» como recordatorio; no
bloquean el guardado):

- Descalzo y con ropa ligera.
- A una hora parecida a la de las mediciones anteriores.
- Antes del entrenamiento.
- Equipos sobre suelo plano.

Se necesita conexión a internet. Si no hay conexión, la aplicación lo avisa y no permite
registrar. Nada se guarda en el dispositivo como borrador.

## 2. Medir a un deportista

1. Entre al perfil del deportista y use el enlace «+ Nueva medición».
2. Elija el modo. «Guiado» es el predeterminado: un paso por medida, con ilustración y los
   textos «Dónde» y «Cómo». «Rápido» muestra todas las medidas en una sola pantalla.
   Puede cambiar de modo en cualquier momento sin perder lo digitado. La aplicación recuerda su
   última elección en ese dispositivo.
3. Tome una sola lectura por medida: peso, talla de pie, talla sentado y, si quiere,
   envergadura. La envergadura es opcional y se puede omitir.
4. En la revisión, la aplicación resume los valores, muestra avisos si algo parece raro y
   presenta la etapa de crecimiento en lenguaje sencillo («Aún no llega al estirón», «Está en
   pleno estirón» o «Ya pasó el estirón»). Las cifras técnicas están en «Detalle técnico».
5. Guarde con «Guardar y terminar». Si el deportista es elegible (9 años o más y el intervalo
   de pliegues está abierto), también aparece «Guardar y agregar pliegues», que abre el
   asistente de pliegues (`docs/21-body-composition/runbook-coach.md`).

Meta de tiempo (por confirmar en el chequeo con tableta): guiado, menos de 2 minutos por
deportista; rápido, menos de 1 minuto.

## 3. Altura del banco y talla sentado

La talla sentado se mide sobre un banco y hay que restarle la altura del banco.

1. En el paso de talla sentado escriba la altura del banco en centímetros. Se permite 0.
2. Escriba la lectura tal como la ve en el tallímetro.
3. La aplicación resta y muestra la talla neta. Solo la talla neta se guarda; la altura del
   banco no queda en el registro.
4. La altura del banco se recuerda en el dispositivo y aparece ya escrita la próxima vez. Si
   cambia de banco, corríjala.

Si la talla neta queda demasiado alta o baja frente a la talla de pie, la aplicación la
rechaza. Casi siempre significa que no se restó el banco o que se cruzaron los campos.

## 4. Avisos antes de guardar

Los avisos no impiden guardar. Cada uno nombra la medida y ofrece volver a ese paso.

| Aviso | Cuándo aparece |
|---|---|
| Talla de pie menor que la anterior | Baja más de 1 cm |
| Crecimiento demasiado rápido | Más de 15 cm por año, si pasaron 60 días o más |
| Cambio de peso grande | Más de 10 % frente a la medición anterior |
| Talla sentado atípica | La proporción sentado/de pie sale de lo esperable |
| Envergadura atípica | Envergadura/talla fuera de 0,90–1,10 |

Qué hacer: vuelva a medir esa medida. Si la lectura se confirma, guarde de todos modos.

En el historial, una medición con aviso vigente muestra la marca «Revisar». La marca se calcula
al mostrar la lista y desaparece cuando se corrige el dato.

## 5. Ya existe una medición de esa fecha

Si el deportista ya tiene una medición con la misma fecha, la aplicación avisa antes de crear
otra. Opciones: «Abrir la existente» o «Cambiar la fecha». Dos mediciones del mismo día no son
válidas; para corregir, edite la existente.

## 6. Jornada de medición (varios deportistas)

Ruta `/anthropometry/session`, título «Jornada de medición».

1. Elija la fecha y marque los deportistas. Puede filtrar por categoría. Quienes ya tienen
   medición ese día aparecen como «Medido hoy». «Seleccionar todos los visibles» no incluye
   a esos deportistas.
2. Avance por la cola. Cada deportista pasa por la misma toma (guiada o rápida) y se guarda en
   el servidor al confirmar, antes de pasar al siguiente.
3. «Omitir por hoy» salta al deportista sin crear registro.
4. Desde la jornada puede abrir el asistente de pliegues de un deportista elegible y volver con
   «Volver a la jornada».
5. Al final, el resumen muestra Medidos, Omitidos y Pendientes, con acceso directo para corregir.
   «Terminar jornada» cierra la sesión.

Importante: la lista de la jornada no se guarda. Si recarga la página, la cierra o se apaga
la tableta, la jornada se pierde. Lo ya confirmado sí está guardado; al volver a empezar,
esos deportistas aparecen como «Medido hoy».

## 7. Si falla la conexión al guardar

- La aplicación conserva lo digitado, dice con claridad que no se guardó y ofrece «Reintentar».
- Al reintentar no se duplica el registro: si el primer intento sí llegó al servidor, el
  reintento lo reconoce como ya guardado.
- Si cierra la página antes de reintentar, los valores se pierden y hay que volver a digitarlos.

## 8. Corregir o eliminar una medición

Solo puede corregir o eliminar quien tomó la medición, o un administrador. Otros entrenadores
ven el registro pero no los botones. Las familias no ven estas acciones.

- **Editar**: en el historial, «Editar». Se abre la vista rápida con los valores. Al guardar se
  recalculan la etapa de crecimiento, los percentiles y todo lo derivado, y se borra la
  explicación de IA de esa medición (se genera de nuevo cuando la pida).
  No se envía otra notificación a la familia por una edición.
- **Cambiar la fecha** de una medición que tiene pliegues: se vuelven a aplicar la edad mínima
  y el intervalo mínimo entre series de pliegues; si no se cumplen, la aplicación lo explica y no
  guarda.
- **Eliminar**: confirme en el cuadro de diálogo, que indica qué más se borra (los pliegues
  asociados y la explicación de IA). No se puede deshacer.

Cada edición o eliminación queda en la auditoría con el nombre de los campos cambiados, nunca
con los valores.

## 9. Guía imprimible

La guía de campo en PDF (la misma de pliegues) ahora empieza con «Antes de medir» y las cuatro
medidas básicas, con las mismas ilustraciones y textos «Dónde / Cómo» de la aplicación.

## 10. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «Sin conexión — no se guardó» | Sin internet | Recupere la conexión y use «Reintentar» |
| Talla sentado rechazada | No se restó el banco o se cruzaron campos | Revise la altura del banco y la lectura |
| No aparecen «Editar» ni «Eliminar» | La medición la tomó otro entrenador | Pida a quien la tomó o a un administrador |
| La jornada desapareció | Se recargó la página | Empiece de nuevo; los ya guardados salen como «Medido hoy» |

Rollback: no hay migración de base de datos en esta función; si se revierte el código, los
registros existentes no cambian.
