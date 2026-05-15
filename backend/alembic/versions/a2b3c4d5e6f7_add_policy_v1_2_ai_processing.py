"""add_policy_v1_2_ai_processing

Revision ID: a2b3c4d5e6f7
Revises: b59ded290a0c
Create Date: 2026-05-15 10:00:00.000000

Cambios:
- Depreca política v1.1 (deprecated_at = '2026-05-15')
- Inserta política v1.2 con finalidad opcional de procesamiento con IA
  (Anthropic Claude / Google Gemini) para generar explicaciones PHV para padres.
  Esta finalidad es separable: rechazarla no afecta el servicio principal del club.
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "b59ded290a0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Contenido HTML de la política v1.2
# Extiende v1.1 con bloque de procesamiento IA en sección 6 "Transferencia a terceros"
# ---------------------------------------------------------------------------

_POLICY_V1_2_HTML = """\
<h1>Política de Tratamiento de Datos Personales</h1>
<p>Club Deportivo Trocha y Ruta · Valle del Cauca, Colombia</p>
<p><strong>Versión 1.2 — Vigente desde el 15 de mayo de 2026.</strong></p>

<h2>Resumen</h2>
<p>Recolectamos datos personales y de salud de los atletas y sus representantes legales para gestionar su participación en el club. El tratamiento cumple con la Ley 1581 de 2012 y el Decreto 1377 de 2013. Para datos de menores exigimos autorización expresa de un padre o representante legal. Puedes ejercer tus derechos escribiéndonos a datos@trochyruta.com.</p>

<h2>1. Responsable del tratamiento</h2>
<p>Club Deportivo Trocha y Ruta actúa como responsable del tratamiento de los datos personales recolectados a través de esta plataforma.</p>
<p><strong>Contacto:</strong> datos@trochyruta.com</p>
<p><strong>Ubicación:</strong> Valle del Cauca, Colombia</p>

<h2>2. Datos que recolectamos</h2>
<p>Recolectamos únicamente los datos necesarios para las finalidades descritas:</p>
<ul>
  <li><strong>Datos básicos del atleta:</strong> nombre, apellido, fecha de nacimiento y sexo, necesarios para gestionar la membresía del atleta en el club.</li>
  <li><strong>Antropometría y maduración biológica (datos sensibles):</strong> talla de pie, talla sentado, peso, envergadura y cálculo del Pico de Velocidad de Crecimiento (PHV — Mirwald). Estos datos son de salud y requieren consentimiento expreso.</li>
  <li><strong>Datos del representante legal:</strong> nombre, teléfono, correo electrónico y relación con el atleta.</li>
</ul>
<p><em>Principio de mínima recolección: no solicitamos datos que excedan lo necesario para las finalidades declaradas (Art. 4, Ley 1581/2012). En esta versión de la plataforma no recolectamos documentos de identidad, contactos de emergencia, sesiones de entrenamiento ni resultados de competencias. Cuando se incorporen estas funcionalidades solicitaremos un consentimiento nuevo.</em></p>

<h2>3. Finalidades del tratamiento</h2>
<ul>
  <li>Gestionar la membresía del atleta en el club.</li>
  <li>Llevar control del crecimiento y la maduración biológica (PHV) del atleta y detectar señales de alerta nutricional o de desarrollo.</li>
  <li>Comunicarse con los representantes legales sobre novedades del club y bienestar del atleta.</li>
  <li><strong>(Opcional)</strong> Generar explicaciones personalizadas y comprensibles sobre el estadio de maduración biológica del atleta, dirigidas a padres y acudientes, mediante modelos de lenguaje (IA). Esta finalidad solo se activa si el representante otorga consentimiento específico en la sección 6.</li>
</ul>

<h2>4. Datos sensibles — antropometría y salud</h2>
<p>Los datos antropométricos (talla, peso, envergadura, PHV) se clasifican como datos sensibles de salud bajo la Ley 1581/2012 (Art. 5). Su tratamiento requiere consentimiento expreso del representante legal. No puedes ser obligado a suministrarlos como condición para inscribirse al club, aunque son necesarios para la personalización del entrenamiento.</p>
<p>Estos datos se utilizan exclusivamente para calcular el estadio de maduración biológica (Pre-PHV, Circa-PHV, Post-PHV), llevar control del crecimiento del atleta a lo largo del tiempo y detectar señales de alerta (brote de crecimiento, riesgo nutricional). Salvo que otorgues el consentimiento opcional de la sección 6, los datos no se comparten con terceros.</p>

<h2>5. Tratamiento de datos de menores de edad</h2>
<p>Nuestros atletas son menores entre 10 y 15 años. Conforme a la Ley 1581/2012 y las directrices del ICBF, el tratamiento de datos de menores está sujeto a protección especial:</p>
<ul>
  <li><strong>Autorización parental obligatoria:</strong> el padre, madre o representante legal debe otorgar autorización previa, expresa e informada antes de cualquier tratamiento.</li>
  <li><strong>Verificación:</strong> la autorización se captura mediante correo electrónico verificado del representante y queda registrada con marca de tiempo y versión de esta política.</li>
  <li><strong>Interés superior del menor:</strong> toda decisión sobre el tratamiento de datos considera ante todo el bienestar y la seguridad del atleta.</li>
  <li>El representante puede revocar el consentimiento en cualquier momento desde su panel de usuario.</li>
</ul>

<h2>6. Transferencia a terceros y procesamiento con inteligencia artificial (OPCIONAL)</h2>
<p>De manera <strong>completamente opcional y separable</strong> del servicio principal del club, el representante legal puede autorizar el uso de modelos de lenguaje (IA) para generar explicaciones personalizadas sobre el estadio de maduración biológica del atleta. Esta funcionalidad convierte los datos numéricos del cálculo PHV en un texto comprensible para padres y acudientes.</p>

<h3>Proveedores de IA utilizados</h3>
<ul>
  <li><strong>Anthropic Claude</strong> (Anthropic PBC, San Francisco, EE. UU.) — modelo de lenguaje para generación de texto.</li>
  <li><strong>Google Gemini</strong> (Google LLC, Mountain View, EE. UU.) — modelo de lenguaje alternativo para generación de texto.</li>
</ul>

<h3>Datos que se envían al proveedor de IA</h3>
<p>Cuando el representante autoriza esta finalidad, el sistema puede enviar al proveedor de IA los siguientes datos del atleta para construir el contexto de la explicación:</p>
<ul>
  <li>Estadio de maduración biológica calculado (Pre-PHV, Circa-PHV o Post-PHV).</li>
  <li>Edad decimal y valores numéricos del cálculo PHV (offset de madurez, edad en PHV).</li>
  <li>Grupo de edad (10-12 años / 13-15 años) con fines de personalización del mensaje.</li>
</ul>
<p>No se envían nombre, apellido, fecha de nacimiento exacta, documentos de identidad ni información de contacto del atleta ni de su representante.</p>

<h3>Uso de los datos por parte del proveedor de IA</h3>
<p>Los datos transmitidos se usan <strong>exclusivamente</strong> para generar la explicación solicitada en tiempo real. Los proveedores de IA listados tienen contractualmente prohibido usar estos datos para entrenar, mejorar o afinar sus modelos. Las explicaciones generadas se almacenan en los servidores del club para evitar transmisiones repetidas de los mismos datos.</p>

<h3>Carácter opcional e independiente</h3>
<p>Si no otorgas este consentimiento, el servicio principal del club no se ve afectado: el entrenador puede seguir registrando mediciones, calcular el PHV y planificar el entrenamiento con normalidad. Solo la funcionalidad de explicación en lenguaje natural para padres quedará desactivada para el atleta en cuestión.</p>
<p>Puedes revocar este consentimiento en cualquier momento desde tu panel de padre/acudiente. La revocación no borra explicaciones ya generadas ni afecta retroactivamente el historial de mediciones.</p>

<h2>7. Tus derechos (Habeas Data)</h2>
<p>Como titular de los datos — o su representante legal — tienes los siguientes derechos reconocidos por la Ley 1581/2012:</p>
<ul>
  <li><strong>Conocer:</strong> saber qué datos tenemos sobre ti y cómo los usamos.</li>
  <li><strong>Actualizar y rectificar:</strong> corregir datos incompletos, inexactos o desactualizados.</li>
  <li><strong>Suprimir:</strong> solicitar la eliminación de tus datos cuando ya no sean necesarios, salvo obligación legal de retención.</li>
  <li><strong>Revocar el consentimiento:</strong> retirar la autorización otorgada. Puedes hacerlo desde tu panel de usuario o escribiéndonos.</li>
  <li><strong>Portabilidad:</strong> recibir tus datos en formato estructurado para trasladarlos a otro servicio.</li>
  <li><strong>Presentar queja:</strong> acudir a la Superintendencia de Industria y Comercio (SIC) si consideras que tus derechos han sido vulnerados.</li>
</ul>

<h2>8. Seguridad de los datos</h2>
<ul>
  <li>Comunicaciones cifradas con TLS (HTTPS) en todas las rutas.</li>
  <li>Contraseñas almacenadas con bcrypt (sin texto plano).</li>
  <li>Acceso restringido por roles (entrenador, padre, administrador).</li>
  <li>En caso de incidente de seguridad que afecte tus datos, notificaremos a la SIC y a los titulares afectados en los plazos aplicables.</li>
</ul>

<h2>9. Vigencia, versiones y actualizaciones</h2>
<p>Esta política entra en vigor el 15 de mayo de 2026 (versión 1.2). Podemos actualizarla cuando cambie el marco legal o el tratamiento de datos. Si los cambios afectan las finalidades originalmente autorizadas, te notificaremos por correo y solicitaremos una nueva autorización antes de continuar el tratamiento. Cada autorización queda registrada con la versión de política vigente al momento de otorgarla.</p>

<h2>Cómo ejercer tus derechos</h2>
<p>Escríbenos a datos@trochyruta.com indicando: (1) tu nombre completo, (2) documento de identidad, y (3) la solicitud específica (acceso, rectificación, supresión, portabilidad o revocación). Responderemos conforme a los plazos establecidos en la Ley 1581/2012. También puedes revocar tu consentimiento directamente desde tu panel de padre/acudiente sin necesidad de contactarnos.</p>\
"""

_HASH_V1_2 = hashlib.sha256(_POLICY_V1_2_HTML.encode()).hexdigest()

_POLICY_TITLE = "Política de Tratamiento de Datos Personales"
_CHANGELOG_V1_2 = (
    "Agrega finalidad opcional de procesamiento con IA (Anthropic Claude / Google Gemini) "
    "para generar explicaciones personalizadas sobre el estadio de maduración biológica "
    "del atleta, dirigidas a padres y acudientes. La finalidad es separable: rechazarla "
    "no afecta el servicio principal del club. Los datos no se usan para entrenar modelos."
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Deprecar v1.1
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "UPDATE privacy_policies SET deprecated_at = '2026-05-15' WHERE version = 'v1.1'"
        )
    )

    # ------------------------------------------------------------------
    # 2. Insertar v1.2 (INSERT IGNORE para idempotencia)
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT IGNORE INTO privacy_policies
                (version, effective_date, deprecated_at, title,
                 content_html, content_hash, changelog, created_by, created_at)
            VALUES
                ('v1.2', '2026-05-15', NULL, :title,
                 :html_v12, :hash_v12, :changelog, NULL, NOW())
            """
        ).bindparams(
            title=_POLICY_TITLE,
            html_v12=_POLICY_V1_2_HTML,
            hash_v12=_HASH_V1_2,
            changelog=_CHANGELOG_V1_2,
        )
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Reverso: eliminar v1.2 y restaurar v1.1 como activa
    # ------------------------------------------------------------------
    op.execute(
        sa.text("DELETE FROM privacy_policies WHERE version = 'v1.2'")
    )
    op.execute(
        sa.text(
            "UPDATE privacy_policies SET deprecated_at = NULL WHERE version = 'v1.1'"
        )
    )
