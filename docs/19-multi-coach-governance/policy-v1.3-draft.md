> **BORRADOR — NO PUBLICADO EN ESTA FUNCIONALIDAD.**
> Este texto es un insumo para la próxima versión de la política de privacidad. **No se
> libera, no se activa y no se le pide a ninguna familia que renueve su consentimiento
> como parte de la funcionalidad 041 (gobernanza multi-entrenador).** Motivo: cualquier
> cambio de versión de la política dispara el aviso bloqueante de renovación de
> consentimiento para **todas** las familias del club (FR-033 de
> `specs/041-multi-coach-governance/spec.md`; supuesto legal documentado en la sección
> "Assumptions" del mismo archivo). El texto se redacta ahora, listo para cuando el club
> decida empaquetarlo junto con el siguiente cambio de política que sí amerite ese costo —
> no se libera solo por este motivo.

# Política de privacidad — borrador v1.3 (pluralidad de entrenadores)

## 1. Qué cambia y por qué

La versión vigente hoy (**v1.1**, `frontend/src/routes/PrivacyPage.tsx`,
`POLICY_VERSION = "1.1"`, `POLICY_DATE = "6 de mayo de 2026"`) describe el tratamiento de
datos asumiendo un único entrenador operando el club. Con la funcionalidad 041 el club
incorpora un segundo entrenador con el mismo alcance de acceso que el primero: cualquiera
de los dos —o de los que haya en el futuro— puede ver y tratar los datos de cualquier
atleta del club en ejercicio de su rol.

**Base legal de por qué esto no exige un nuevo consentimiento por sí solo**: el
consentimiento parental se otorga al club como responsable del tratamiento y por
finalidad — no a una persona con nombre propio. Agregar un entrenador no cambia el
responsable del tratamiento ni las finalidades autorizadas, así que, en estricto sentido,
no requeriría un nuevo consentimiento. Aun así, el texto de la política **describe**
quién accede a los datos, y hoy lo hace en singular; dejar ese texto desactualizado sería
inexacto de cara a las familias, aunque no sea ilegal. Por eso el cambio de redacción
queda listo aquí, para viajar en el próximo cambio de versión que de todas formas active
el aviso de renovación — nunca solo.

## 2. Alcance del cambio de texto

Dos cambios de redacción, ambos de pluralización — ningún dato nuevo se recolecta, ninguna
finalidad nueva se declara, ningún tercero nuevo recibe datos:

1. **En toda mención al personal que accede a los datos del atleta**, "el entrenador" pasa
   a "los entrenadores" o "el personal técnico del club" (plural), reflejando que más de
   una persona puede ejercer ese rol.
2. **En la sección de ejercicio de derechos (Habeas Data)**, el texto que describe cómo el
   club atiende una solicitud pasa a hablar en plural: no es una persona la que responde,
   es el equipo del club, y la solicitud puede ser atendida por cualquiera de los
   entrenadores o por el administrador — nunca solo por quien fue el entrenador original
   del atleta.

## 3. Redacción propuesta, sección por sección

Formato: texto vigente (v1.1) → texto propuesto (v1.3, borrador). Numeración de sección
según `PrivacyPage.tsx` actual.

### 3.1 Sección "8. Seguridad de los datos"

**Vigente (v1.1)**:

> Acceso restringido por roles (entrenador, padre, administrador).

**Propuesto (v1.3, borrador)**:

> Acceso restringido por roles (entrenador — puede haber más de uno autorizado por el
> club —, padre/acudiente, administrador). Cualquier entrenador autorizado por el club
> tiene el mismo nivel de acceso a los datos de los atletas del club, y cada acción queda
> registrada con el nombre de quien la realizó.

La cláusula final ("cada acción queda registrada...") conecta con la funcionalidad 041 en
sí misma — la bitácora de auditoría (`docs/19-multi-coach-governance/design.md` §1) — y
es una oportunidad honesta de decirle a la familia que la pluralidad de acceso no significa
menos trazabilidad, sino más.

### 3.2 Sección "5. Tratamiento de datos de menores de edad"

**Vigente (v1.1)**, dentro de la lista de garantías:

> El representante puede revocar el consentimiento en cualquier momento desde su panel de
> usuario.

No requiere cambio de fondo, pero se sugiere agregar un punto nuevo a la misma lista,
explícito sobre la pluralidad de entrenadores como responsables operativos (no como
responsables legales del tratamiento, que sigue siendo el club):

**Nuevo punto propuesto**:

> **Entrenadores autorizados por el club:** el club puede contar con más de un
> entrenador. Todos los entrenadores autorizados por el club tienen acceso a los mismos
> datos, bajo las mismas obligaciones de confidencialidad y con el mismo registro de
> trazabilidad. El consentimiento se otorga al club como responsable del tratamiento, no a
> un entrenador en particular, y permanece vigente aunque el club incorpore o retire
> personal.

### 3.3 Sección "Cómo ejercer tus derechos" (Habeas Data) — el canal, en plural

**Vigente (v1.1)**:

> Escríbenos a clubtrochayruta@hotmail.com indicando: (1) tu nombre completo, (2)
> documento de identidad, y (3) la solicitud específica (acceso, rectificación,
> supresión, portabilidad o revocación). Responderemos conforme a los plazos establecidos
> en la Ley 1581/2012.
>
> También puedes revocar tu consentimiento directamente desde tu panel de padre/acudiente
> sin necesidad de contactarnos.

**Propuesto (v1.3, borrador)** — mismo canal de correo (no se abre un canal nuevo; el
cambio es de redacción, de "quien te atiende" en singular implícito a plural explícito):

> Escríbenos a clubtrochayruta@hotmail.com indicando: (1) tu nombre completo, (2)
> documento de identidad, y (3) la solicitud específica (acceso, rectificación,
> supresión, portabilidad o revocación). **Cualquiera de los entrenadores autorizados o el
> administrador del club puede dar trámite a tu solicitud** — no depende de una sola
> persona ni de que un entrenador en particular esté disponible. Responderemos conforme a
> los plazos establecidos en la Ley 1581/2012.
>
> También puedes revocar tu consentimiento directamente desde tu panel de padre/acudiente
> sin necesidad de contactarnos.

**Nota de alcance, dicha de frente**: "el canal de habeas data en plural" en esta
funcionalidad se resuelve como arriba — pluralizar quién puede atenderlo, sobre el mismo
canal de correo único que ya existe. No se abrió, y esta funcionalidad no exige abrir, un
segundo canal de contacto (por ejemplo un teléfono o un formulario adicional); si el club
decide agregar uno en el futuro, es una decisión de producto independiente de esta
funcionalidad.

### 3.4 Encabezado y pie de página

`POLICY_VERSION` → `"1.3"`, `POLICY_DATE` → fecha real de publicación (pendiente de
decisión del dueño del producto; no se fija aquí). Un `changelog` interno para la nueva
fila de `privacy_policies` (ver §5) debería decir, en el mismo estilo que el comentario
`v1.0 → v1.1` que ya existe en `PrivacyPage.tsx`:

```text
Cambios v1.1 → v1.3:
  - Texto actualizado para reflejar que el club puede tener más de un
    entrenador con el mismo nivel de acceso a los datos de los atletas
    (funcionalidad 041, gobernanza multi-entrenador).
  - Sección de ejercicio de derechos (Habeas Data): aclarado que cualquier
    entrenador autorizado o el administrador puede dar trámite a una
    solicitud, sobre el mismo canal de correo existente.
  - Sin cambios de fondo: no se recolectan datos nuevos, no se declaran
    finalidades nuevas, no hay transferencia a terceros nueva.
```

**Salto de versión 1.1 → 1.3, no 1.1 → 1.2**: el número de archivo (`policy-v1.3-draft.md`)
fue asignado por quien definió esta tarea (`tasks.md` T094); este documento no encontró
ningún borrador de v1.2 en el repositorio al momento de escribirse. Si "v1.2" está
reservada para otro cambio de política que este borrador desconoce, quien libere la
versión final debe reconciliar el número antes de publicar — no asumir que 1.2 quedó
vacía por error.

## 4. Lo que este borrador NO cambia

- No se recolecta ningún dato nuevo.
- No se declara ninguna finalidad nueva.
- No hay transferencia a terceros nueva (sección 6 de la política vigente queda igual).
- No cambia el responsable del tratamiento (sigue siendo el club, no un entrenador).
- No se activa ningún aviso de renovación de consentimiento como parte de esta
  funcionalidad.
- No se toca ninguna otra pieza de copy del producto (plantillas de correo, PDF/DOCX)
  donde "el entrenador" aparece en singular — esas piezas son parte del producto operativo
  del día a día (por ejemplo, el correo de invitación a una sesión), no de la política de
  privacidad, y quedan fuera del alcance de FR-033. Pluralizarlas, si el club lo decide, es
  una decisión de copy de producto independiente.

## 5. Qué hace falta para liberar esto (fuera de esta funcionalidad)

1. **Fecha de vigencia real y revisión legal/editorial final** del texto de §3 — este
   borrador no fija `POLICY_DATE` a propósito.
2. **Insertar una fila nueva en `privacy_policies`** (`backend/app/models/privacy_policy.py`)
   con `version="1.3"`, el `content_html` completo (no solo las secciones que cambian —
   la tabla es append-only, cada fila es el documento entero), `content_hash` (SHA-256 del
   `content_html`), y `changelog` con el texto de §3.4. La fila anterior (`v1.1`) se marca
   `deprecated_at` en la misma operación.
3. **Sincronizar `frontend/src/routes/PrivacyPage.tsx`** con exactamente ese mismo texto —
   `POLICY_VERSION`, `POLICY_DATE` y el cuerpo de las secciones 5 y 8 y del bloque "Cómo
   ejercer tus derechos". `frontend/src/schemas/onboarding.schema.ts`'s
   `PRIVACY_POLICY_VERSION` también debe pasar a `"v1.3"` en la misma operación — hoy dice
   `"v1.1"` y es lo que el flujo de onboarding compara contra la versión vigente en la
   base de datos; dejarlo desincronizado del `PrivacyPolicy.version` de la base de datos
   rompería la captura de consentimiento (`backend/app/routers/consent.py`), no solo la
   página pública.
4. **Confirmar el disparo del aviso de renovación de consentimiento** para todas las
   familias, y decidir junto con el dueño del producto si este cambio se libera solo o
   empaquetado con otro cambio de política pendiente — la razón misma por la que FR-033
   pide no liberarlo solo.

## 6. Referencias

- `specs/041-multi-coach-governance/spec.md` — FR-033, sección Assumptions ("Legal").
- `frontend/src/routes/PrivacyPage.tsx` — texto vigente v1.1, fuente de la redacción
  base de este borrador.
- `frontend/src/schemas/onboarding.schema.ts` — `PRIVACY_POLICY_VERSION`, consumido por
  el flujo de consentimiento del onboarding.
- `backend/app/models/privacy_policy.py` — modelo `PrivacyPolicy`, append-only,
  `ix_privacy_policies_version` único por versión.
- `backend/app/routers/consent.py` — captura y verificación del consentimiento contra la
  versión de política vigente.
