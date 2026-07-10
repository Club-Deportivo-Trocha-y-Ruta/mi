# Sincronización con Strava — Guía para familias

**Para:** padres, madres y acudientes de atletas del Club Deportivo Trocha y Ruta.
**Qué logra:** que las rodadas que tu hija o hijo ya registra en su ciclocomputador (Garmin, Magene, iGPSport) aparezcan automáticamente en la plataforma del club — duración, distancia y frecuencia cardiaca — sin subir ningún archivo a mano.

> Detalle técnico del módulo en [`../../specs/025-strava-activity-sync/plan.md`](../../specs/025-strava-activity-sync/plan.md) y [`spec.md`](../../specs/025-strava-activity-sync/spec.md). Guía operativa del entrenador en [`guia-entrenador.md`](guia-entrenador.md).

---

## 1. Cómo funciona, en una frase

El atleta ya sincroniza sus rodadas a **Strava** desde su dispositivo (así lo hace hoy, sin cambiar nada). Nosotros conectamos, una sola vez, la cuenta de Strava del atleta con la plataforma del club. Desde ese momento, cada rodada nueva llega sola.

- **No hay que subir archivos.** No hay que copiar datos a mano.
- **El entrenador decide** si una actividad queda asociada a una sesión de entrenamiento planeada o si queda libre (paseo familiar, salida por fuera del club, etc.). Ustedes no tienen que hacer nada en esa parte.
- **La ubicación y el mapa de la ruta nunca se muestran** en la plataforma del club, aunque Strava sí los tenga. Ver sección 5.

## 2. Antes de conectar: el consentimiento del acudiente

La conexión con Strava es un dato externo sobre tu hijo o hija, por lo que el club exige tu autorización explícita antes de activarla — el mismo tratamiento que ya aplica a otros datos sensibles del atleta (Ley 1581 de 2012).

**Cómo se registra hoy:** dile al entrenador o al administrador del club que autorizas la sincronización de actividades externas de Strava para tu hijo/a. El entrenador o administrador deja constancia de tu autorización en la ficha del atleta antes de iniciar la conexión.

> Nota: por ahora esta autorización la registra el entrenador/administrador a partir de tu autorización verbal o escrita — todavía no hay una casilla de autoservicio en el portal de padres para este consentimiento en particular (pendiente de decisión de producto). Sin ese registro, el botón "Conectar con Strava" del perfil del atleta permanece deshabilitado y muestra el aviso "Falta el consentimiento del acudiente para sincronizar actividades externas".

## 3. Conectar la cuenta de Strava del atleta (una sola vez)

Requisito previo: tu hijo/a debe tener cuenta propia de Strava. **Strava exige 13 años cumplidos** para tener cuenta. Si el atleta tiene entre 10 y 12 años y no cumple ese mínimo, sencillamente no habrá actividades sincronizadas — el resto de la plataforma funciona igual, sin ningún cambio.

Pasos (toma menos de 5 minutos):

1. Con el consentimiento ya registrado (sección 2), entra al perfil del atleta en la plataforma del club y abre la pestaña **Actividades**.
2. En la tarjeta **Conexión con Strava**, pulsa **Conectar con Strava**.
3. Se abre la página oficial de autorización de Strava (`strava.com`). Inicia sesión con la cuenta del atleta si no lo está ya, y confirma el permiso solicitado.
4. Strava te devuelve al perfil del atleta. La tarjeta ahora muestra el estado **Conectado**, con el nombre de quien autorizó y la fecha.

A partir de aquí no hay que repetir nada: cada vez que el atleta suba una rodada a Strava desde su dispositivo, aparecerá sola en la plataforma del club — normalmente en menos de 15 minutos, y como garantía siempre dentro de 24 horas incluso si la notificación inmediata de Strava falla.

## 4. Recomendación importante: mantén tus actividades privadas en Strava

Strava, por defecto, puede mostrar tus rutas a cualquier persona que use la aplicación o el sitio web, incluyendo el mapa exacto de dónde empezó y terminó cada rodada — es decir, puede revelar dónde vive el atleta.

**Recomendación del club:** configura las actividades del atleta como privadas (o al menos visibles solo para seguidores de confianza) directamente en la app de Strava, en **Ajustes → Privacidad**. Esto no afecta en nada la sincronización con la plataforma del club: seguimos recibiendo la actividad igual, porque la autorización que diste en el paso 3 nos permite leerla aunque sea privada.

La plataforma del club, por su parte, **nunca muestra el mapa de la ruta ni la ubicación de inicio/fin** de ninguna actividad, sin importar la configuración de privacidad en Strava — es una decisión de diseño del club para proteger a los menores, no una opción que se pueda activar. Ver sección 5.

## 5. Qué se ve en la plataforma del club (y qué no)

**Sí se muestra**, en la pestaña Actividades del perfil del atleta:

- Fecha y hora de la rodada.
- Tipo de actividad (ruta, MTB, entrenamiento indoor, etc.).
- Duración y distancia.
- Frecuencia cardiaca media y máxima (cuando el dispositivo la registró).
- Si el entrenador la asoció a una sesión de entrenamiento del club, o si quedó libre.

**Nunca se muestra**, en ninguna vista de la plataforma:

- El mapa de la ruta.
- Las coordenadas de inicio o final de la rodada.
- Cualquier otro dato de ubicación precisa.

Este dato ni siquiera se guarda en nuestra base de datos: se descarta al momento de recibir la actividad desde Strava, así que no existe manera de que aparezca por accidente en el futuro.

**Quién puede ver las actividades de tu hijo/a:** solo tú (como acudiente vinculado a ese atleta), el entrenador y el administrador del club. Otras familias del club no tienen acceso a las actividades de atletas que no son suyos.

## 6. Si la actividad no aparece

- **Espera un poco.** El caso normal es que aparezca en minutos; el margen de garantía es de 24 horas.
- **Revisa que la rodada haya llegado a Strava** desde el dispositivo (Garmin Connect, Magene, iGPSport suelen sincronizar automáticamente por wifi/bluetooth, pero a veces requieren abrir la app).
- **Revisa el estado de la conexión** en la pestaña Actividades del perfil: si dice **Conexión rota** o **Desconectado**, hay que volver a conectar (sección 7).
- Si nada de esto resuelve, contacta al entrenador.

## 7. Conexión rota o desconexión

- **Conexión rota**: ocurre cuando la autorización dejó de ser válida del lado de Strava (por ejemplo, Strava revocó el acceso por inactividad prolongada). La tarjeta muestra un aviso ámbar y el botón cambia a **Reconectar** — es el mismo flujo de la sección 3, no hay que hacer nada distinto.
- **Desconexión**: en cualquier momento, tú o el entrenador pueden desconectar la cuenta desde el botón **Desconectar** en el perfil del atleta. Al desconectar:
  - Deja de llegar información nueva.
  - **Las actividades que ya se sincronizaron se conservan** — no se borran.
  - Se puede reconectar cuando quieras, repitiendo el paso 3.
- La desconexión también puede iniciarse desde el lado de Strava (por ejemplo, revocando el acceso de la app "Club Trocha y Ruta" desde los ajustes de Strava del atleta) — el club lo detecta y refleja el estado como desconectado.

## 8. Preguntas frecuentes

**¿Tengo que subir algo manualmente?**
No. Una vez conectada la cuenta, todo llega solo.

**¿El entrenador ve la ruta exacta que hizo mi hijo/a?**
No, en la plataforma del club nunca se muestra mapa ni ubicación (sección 5). Si el atleta deja sus actividades públicas en Strava, cualquier detalle adicional que Strava sí muestre está fuera del control del club — por eso la recomendación de la sección 4.

**¿Qué pasa si mi hijo/a sube una rodada que no fue entrenamiento (un paseo, una salida familiar)?**
Queda sincronizada igual, pero el entrenador simplemente no la asocia a ninguna sesión. Quedar "sin enlazar" es un estado normal y permanente — no hay que hacer nada al respecto.

**¿Qué pasa si dos atletas del club salen juntos y ambos suben la misma ruta?**
Cada quien ve su propia actividad en su propio perfil, de forma independiente. No se intenta cruzar ni deduplicar entre atletas distintos.

**¿Puedo revocar el acceso en cualquier momento?**
Sí, desde la plataforma del club (sección 7) o directamente desde los ajustes de tu cuenta de Strava.

**¿Qué pasa si mi hijo/a edita o borra una actividad en Strava después de que ya se sincronizó?**
Si la edita, el club actualiza los datos (por ejemplo, si corrige la distancia). Si la borra en Strava, la plataforma del club marca la actividad como "eliminada en Strava" en vez de borrarla de golpe — así el entrenador revisa si esa actividad tenía una sesión asociada antes de decidir qué hacer.
