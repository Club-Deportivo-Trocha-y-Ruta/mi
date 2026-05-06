"""add_privacy_policies_table_and_consent_fk

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-05-06 12:00:00.000000

Cambios:
- Crea tabla `privacy_policies` (versiones inmutables de la política, Ley 1581 Art. 26)
- Inserta v1.0 (vigente 2026-04-15 → 2026-05-06) y v1.1 (vigente desde 2026-05-06)
- Agrega columnas `policy_id`, `user_agent`, `withdrawal_reason` a `parental_consents`
- Crea FK parental_consents.policy_id → privacy_policies.id (ON DELETE RESTRICT)
- Backfill policy_id desde consent_version
- Crea índice ix_parental_consents_policy_id
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "786202a460c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Contenido HTML de cada versión de política
# Extraído del historial de frontend/src/routes/PrivacyPage.tsx
# ---------------------------------------------------------------------------

_POLICY_V1_0_HTML = """\
<h1>Política de Tratamiento de Datos Personales</h1>
<p>Club Deportivo Trocha y Ruta · Valle del Cauca, Colombia</p>
<p><strong>Versión 1.0 — Vigente desde el 15 de abril de 2026 hasta el 6 de mayo de 2026.</strong></p>

<h2>Resumen</h2>
<p>Recolectamos datos personales y de salud de los atletas y sus representantes legales para gestionar su participación en el club. El tratamiento cumple con la Ley 1581 de 2012 y el Decreto 1377 de 2013. Para datos de menores exigimos autorización expresa de un padre o representante legal.</p>

<h2>1. Responsable del tratamiento</h2>
<p>Club Deportivo Trocha y Ruta actúa como responsable del tratamiento de los datos personales recolectados a través de esta plataforma.</p>
<p><strong>Contacto:</strong> datos@trochyruta.com</p>
<p><strong>Ubicación:</strong> Valle del Cauca, Colombia</p>

<h2>2. Datos que recolectamos</h2>
<p>Recolectamos únicamente los datos necesarios para las finalidades descritas:</p>
<ul>
  <li><strong>Identificación:</strong> nombre completo, fecha de nacimiento, documento de identidad (o tarjeta de identidad para menores), información de contacto de emergencia.</li>
  <li><strong>Seguimiento deportivo:</strong> sesiones de entrenamiento, resultados en competencias, carga de entrenamiento, frecuencia cardíaca y observaciones del entrenador.</li>
  <li><strong>Antropometría y maduración biológica (datos sensibles):</strong> talla de pie, talla sentado, peso, envergadura y cálculo del Pico de Velocidad de Crecimiento (PHV — Mirwald). Estos datos son de salud y requieren consentimiento expreso.</li>
  <li><strong>Datos del representante legal:</strong> nombre, teléfono, correo electrónico y relación con el atleta.</li>
</ul>
<p><em>Principio de mínima recolección: no solicitamos datos que excedan lo necesario para las finalidades declaradas (Art. 4, Ley 1581/2012).</em></p>

<h2>3. Finalidades del tratamiento</h2>
<ul>
  <li>Gestionar la inscripción y participación del atleta en el club y competencias.</li>
  <li>Planificar y monitorear el entrenamiento según el modelo LTAD y el cálculo PHV.</li>
  <li>Comunicarse con los representantes legales sobre novedades, competencias y bienestar del atleta.</li>
  <li>Garantizar la seguridad del atleta durante actividades deportivas.</li>
  <li>(Opcional) Análisis deportivo avanzado con herramientas externas si el representante otorgó consentimiento específico.</li>
</ul>

<h2>4. Datos sensibles — antropometría y salud</h2>
<p>Los datos antropométricos (talla, peso, envergadura, PHV) se clasifican como datos sensibles de salud bajo la Ley 1581/2012 (Art. 5). Su tratamiento requiere consentimiento expreso del representante legal. No puedes ser obligado a suministrarlos como condición para inscribirse al club, aunque son necesarios para la personalización del entrenamiento.</p>
<p>Estos datos se utilizan exclusivamente para calcular el estadio de maduración biológica (Pre-PHV, Circa-PHV, Post-PHV) y ajustar la carga de entrenamiento de acuerdo con el modelo LTAD. No se comparten con terceros salvo autorización explícita.</p>

<h2>5. Tratamiento de datos de menores de edad</h2>
<p>Nuestros atletas son menores entre 10 y 15 años. Conforme a la Ley 1581/2012 y las directrices del ICBF, el tratamiento de datos de menores está sujeto a protección especial:</p>
<ul>
  <li><strong>Autorización parental obligatoria:</strong> el padre, madre o representante legal debe otorgar autorización previa, expresa e informada antes de cualquier tratamiento.</li>
  <li><strong>Verificación:</strong> la autorización se captura mediante correo electrónico verificado del representante y queda registrada con marca de tiempo y versión de esta política.</li>
  <li><strong>Interés superior del menor:</strong> toda decisión sobre el tratamiento de datos considera ante todo el bienestar y la seguridad del atleta.</li>
  <li>El representante puede revocar el consentimiento en cualquier momento desde su panel de usuario.</li>
</ul>

<h2>6. Transferencia a terceros</h2>
<p>Solo transferimos datos a terceros cuando el representante ha otorgado consentimiento específico para ello:</p>
<ul>
  <li><strong>Intervals.icu:</strong> plataforma de análisis deportivo. Solo datos de rendimiento (potencia, FC, carga) — nunca datos de identificación personal.</li>
  <li><strong>Google Sheets:</strong> hojas de cálculo para seguimiento de equipo. Solo datos de rendimiento agregados.</li>
</ul>
<p>Si no otorgas este consentimiento opcional, el servicio del club no se ve afectado. Los terceros actúan como encargados del tratamiento con obligaciones contractuales de confidencialidad y seguridad (Decreto 1377/2013, Art. 5).</p>

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
  <li>Registro de auditoría de accesos a datos sensibles.</li>
  <li>En caso de incidente de seguridad que afecte tus datos, notificaremos a la SIC y a los titulares afectados en los plazos aplicables.</li>
</ul>

<h2>9. Vigencia, versiones y actualizaciones</h2>
<p>Esta política entra en vigor el 15 de abril de 2026 (versión 1.0). Podemos actualizarla cuando cambie el marco legal o el tratamiento de datos. Si los cambios afectan las finalidades originalmente autorizadas, te notificaremos por correo y solicitaremos una nueva autorización antes de continuar el tratamiento.</p>\
"""

_POLICY_V1_1_HTML = """\
<h1>Política de Tratamiento de Datos Personales</h1>
<p>Club Deportivo Trocha y Ruta · Valle del Cauca, Colombia</p>
<p><strong>Versión 1.1 — Vigente desde el 6 de mayo de 2026.</strong></p>

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
</ul>

<h2>4. Datos sensibles — antropometría y salud</h2>
<p>Los datos antropométricos (talla, peso, envergadura, PHV) se clasifican como datos sensibles de salud bajo la Ley 1581/2012 (Art. 5). Su tratamiento requiere consentimiento expreso del representante legal. No puedes ser obligado a suministrarlos como condición para inscribirse al club, aunque son necesarios para la personalización del entrenamiento.</p>
<p>Estos datos se utilizan exclusivamente para calcular el estadio de maduración biológica (Pre-PHV, Circa-PHV, Post-PHV), llevar control del crecimiento del atleta a lo largo del tiempo y detectar señales de alerta (brote de crecimiento, riesgo nutricional). No se comparten con terceros.</p>

<h2>5. Tratamiento de datos de menores de edad</h2>
<p>Nuestros atletas son menores entre 10 y 15 años. Conforme a la Ley 1581/2012 y las directrices del ICBF, el tratamiento de datos de menores está sujeto a protección especial:</p>
<ul>
  <li><strong>Autorización parental obligatoria:</strong> el padre, madre o representante legal debe otorgar autorización previa, expresa e informada antes de cualquier tratamiento.</li>
  <li><strong>Verificación:</strong> la autorización se captura mediante correo electrónico verificado del representante y queda registrada con marca de tiempo y versión de esta política.</li>
  <li><strong>Interés superior del menor:</strong> toda decisión sobre el tratamiento de datos considera ante todo el bienestar y la seguridad del atleta.</li>
  <li>El representante puede revocar el consentimiento en cualquier momento desde su panel de usuario.</li>
</ul>

<h2>6. Transferencia a terceros</h2>
<p>En esta versión de la plataforma no transferimos datos a terceros. Tampoco usamos los datos del atleta para entrenar modelos de inteligencia artificial ni para publicidad.</p>
<p>Cuando integremos plataformas externas de análisis deportivo (por ejemplo, Intervals.icu) o herramientas de seguimiento de equipo, te lo informaremos y solicitaremos un consentimiento específico antes de compartir cualquier dato. Hasta entonces, los datos permanecen únicamente en nuestros sistemas.</p>

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
<p>Esta política entra en vigor el 6 de mayo de 2026 (versión 1.1). Podemos actualizarla cuando cambie el marco legal o el tratamiento de datos. Si los cambios afectan las finalidades originalmente autorizadas, te notificaremos por correo y solicitaremos una nueva autorización antes de continuar el tratamiento. Cada autorización queda registrada con la versión de política vigente al momento de otorgarla.</p>

<h2>Cómo ejercer tus derechos</h2>
<p>Escríbenos a datos@trochyruta.com indicando: (1) tu nombre completo, (2) documento de identidad, y (3) la solicitud específica (acceso, rectificación, supresión, portabilidad o revocación). Responderemos conforme a los plazos establecidos en la Ley 1581/2012. También puedes revocar tu consentimiento directamente desde tu panel de padre/acudiente sin necesidad de contactarnos.</p>\
"""

_HASH_V1_0 = hashlib.sha256(_POLICY_V1_0_HTML.encode()).hexdigest()
_HASH_V1_1 = hashlib.sha256(_POLICY_V1_1_HTML.encode()).hexdigest()

_POLICY_TITLE = "Política de Tratamiento de Datos Personales"
_CHANGELOG_V1_1 = (
    "Recortadas finalidades a las efectivamente implementadas en Fase 1: datos básicos del atleta "
    "y antropometría/PHV. Eliminadas menciones a documento de identidad, contacto de emergencia, "
    "seguimiento de entrenamiento y transferencia a terceros (Intervals.icu, Google Sheets)."
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Crear tabla privacy_policies
    # ------------------------------------------------------------------
    op.create_table(
        "privacy_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("deprecated_at", sa.Date(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_html", mysql.LONGTEXT(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_privacy_policies_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index(
        "ix_privacy_policies_version", "privacy_policies", ["version"], unique=True
    )
    op.create_index(
        "ix_privacy_policies_effective_date", "privacy_policies", ["effective_date"]
    )

    # ------------------------------------------------------------------
    # 2. Insertar versiones v1.0 y v1.1 (INSERT IGNORE para idempotencia)
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT IGNORE INTO privacy_policies
                (version, effective_date, deprecated_at, title,
                 content_html, content_hash, changelog, created_by, created_at)
            VALUES
                ('v1.0', '2026-04-15', '2026-05-06', :title,
                 :html_v10, :hash_v10, NULL, NULL, NOW())
            """
        ).bindparams(
            title=_POLICY_TITLE,
            html_v10=_POLICY_V1_0_HTML,
            hash_v10=_HASH_V1_0,
        )
    )
    op.execute(
        sa.text(
            """
            INSERT IGNORE INTO privacy_policies
                (version, effective_date, deprecated_at, title,
                 content_html, content_hash, changelog, created_by, created_at)
            VALUES
                ('v1.1', '2026-05-06', NULL, :title,
                 :html_v11, :hash_v11, :changelog, NULL, NOW())
            """
        ).bindparams(
            title=_POLICY_TITLE,
            html_v11=_POLICY_V1_1_HTML,
            hash_v11=_HASH_V1_1,
            changelog=_CHANGELOG_V1_1,
        )
    )

    # ------------------------------------------------------------------
    # 3. Agregar columnas nuevas a parental_consents
    # ------------------------------------------------------------------
    op.add_column(
        "parental_consents",
        sa.Column("policy_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "parental_consents",
        sa.Column("user_agent", sa.String(500), nullable=True),
    )
    op.add_column(
        "parental_consents",
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 4. Crear FK parental_consents.policy_id → privacy_policies.id
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_parental_consents_policy_id",
        "parental_consents",
        "privacy_policies",
        ["policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 5. Backfill: resolver policy_id desde consent_version
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE parental_consents pc
            JOIN privacy_policies pp ON pp.version = pc.consent_version
            SET pc.policy_id = pp.id
            WHERE pc.policy_id IS NULL
            """
        )
    )

    # ------------------------------------------------------------------
    # 6. Índice en policy_id para JOINs y filtros futuros
    # ------------------------------------------------------------------
    op.create_index(
        "ix_parental_consents_policy_id", "parental_consents", ["policy_id"]
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Reverso simétrico
    # ------------------------------------------------------------------
    op.drop_index("ix_parental_consents_policy_id", table_name="parental_consents")
    op.drop_constraint(
        "fk_parental_consents_policy_id", "parental_consents", type_="foreignkey"
    )
    op.drop_column("parental_consents", "withdrawal_reason")
    op.drop_column("parental_consents", "user_agent")
    op.drop_column("parental_consents", "policy_id")
    op.drop_index("ix_privacy_policies_effective_date", table_name="privacy_policies")
    op.drop_index("ix_privacy_policies_version", table_name="privacy_policies")
    op.drop_table("privacy_policies")
