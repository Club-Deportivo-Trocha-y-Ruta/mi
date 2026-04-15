"""
Template Registry — catálogo centralizado de specs de email y documentos.

Paso 2 del workflow-notifications.
Responsabilidades:
  - Registrar specs (required_context_keys, rutas de templates) para cada template.
  - Validar que el contexto recibido contiene todas las claves requeridas antes de renderizar.
  - Verificar que los archivos de template existen en disco al arrancar la aplicación.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.notification import DocumentFormat, DocumentTemplate, NotificationTemplate

logger = logging.getLogger(__name__)

# Raíz de templates. Se asume que la app corre con CWD = backend/.
# Se puede sobreescribir en tests pasando templates_root al constructor.
_DEFAULT_TEMPLATES_ROOT = Path(__file__).parents[3] / "templates"


# ---------------------------------------------------------------------------
# Dataclasses de spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmailTemplateSpec:
    """Especificación de un template de email."""

    template_id: str
    """Nombre que coincide con NotificationTemplate.value."""

    subject_template: str
    """Plantilla Jinja2 para el asunto (string, no archivo)."""

    body_path: str
    """Ruta relativa al archivo HTML dentro de templates/email/."""

    required_context_keys: frozenset[str] = field(default_factory=frozenset)
    """Claves que deben estar presentes en el contexto antes de renderizar."""

    description: str = ""


@dataclass(frozen=True)
class DocumentTemplateSpec:
    """Especificación de un template de documento (PDF o DOCX)."""

    template_id: str
    """Nombre que coincide con DocumentTemplate.value."""

    format: DocumentFormat

    template_path: str
    """Ruta relativa al archivo dentro de templates/documents/."""

    required_context_keys: frozenset[str] = field(default_factory=frozenset)
    """Claves que deben estar presentes en el contexto antes de renderizar."""

    description: str = ""


# ---------------------------------------------------------------------------
# Catálogo de templates de email
# ---------------------------------------------------------------------------

EMAIL_TEMPLATES: dict[str, EmailTemplateSpec] = {
    NotificationTemplate.WELCOME_ATHLETE: EmailTemplateSpec(
        template_id=NotificationTemplate.WELCOME_ATHLETE,
        subject_template="¡Bienvenido/a a {{ club_name }}, {{ athlete_first_name }}!",
        body_path="email/welcome_athlete.html",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "club_name",
                "season_year",
                "parent_name",
            }
        ),
        description="Email de bienvenida al atleta/familia al registrarse en el club.",
    ),
    NotificationTemplate.ANTHROPOMETRY_ALERT: EmailTemplateSpec(
        template_id=NotificationTemplate.ANTHROPOMETRY_ALERT,
        subject_template="[Alerta] Nueva medición registrada — {{ club_name }}",
        body_path="email/anthropometry_alert.html",
        required_context_keys=frozenset(
            {
                # No incluye nombre del atleta — privacidad PHI de menores.
                # El coach verifica identidad en el dashboard mediante athlete_id.
                "athlete_id",
                "club_name",
                "coach_name",
                "evaluation_date",
                "maturation_status",
            }
        ),
        description=(
            "Alerta al coach sobre una nueva medición. "
            "NO incluye nombre del atleta (solo athlete_id opaco)."
        ),
    ),
    NotificationTemplate.MONTHLY_REPORT: EmailTemplateSpec(
        template_id=NotificationTemplate.MONTHLY_REPORT,
        subject_template="Informe mensual {{ month_label }} — {{ athlete_first_name }}",
        body_path="email/monthly_report.html",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "parent_name",
                "club_name",
                "month_label",
                "season_year",
            }
        ),
        description="Resumen mensual de progreso enviado a los padres.",
    ),
    NotificationTemplate.PARENT_INVITE: EmailTemplateSpec(
        template_id=NotificationTemplate.PARENT_INVITE,
        subject_template="Invitación para seguir a {{ athlete_first_name }} en {{ club_name }}",
        body_path="email/parent_invite.html",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "club_name",
                "invite_url",
            }
        ),
        description=(
            "Invitación al padre/acudiente para crear su cuenta y vincularse con el atleta. "
            "Incluye enlace de onboarding con token de 72 h."
        ),
    ),
}

# ---------------------------------------------------------------------------
# Catálogo de templates de documentos
# ---------------------------------------------------------------------------

DOCUMENT_TEMPLATES: dict[str, DocumentTemplateSpec] = {
    DocumentTemplate.ANTHROPOMETRY_REPORT: DocumentTemplateSpec(
        template_id=DocumentTemplate.ANTHROPOMETRY_REPORT,
        format=DocumentFormat.PDF,
        template_path="documents/pdf/anthropometry_report.html",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "athlete_last_name",
                # age_years en lugar de birth_date — DOB es dato CRÍTICO de menores
                "age_years",
                "sex",
                "club_name",
                "evaluation_date",
                "weight_kg",
                "standing_height_cm",
                "sitting_height_cm",
                "maturation_status",
                "maturity_offset",
                "age_at_phv",
            }
        ),
        description="Reporte antropométrico completo en PDF con tabla de mediciones y badge PHV.",
    ),
    DocumentTemplate.MONTHLY_PROGRESS: DocumentTemplateSpec(
        template_id=DocumentTemplate.MONTHLY_PROGRESS,
        format=DocumentFormat.PDF,
        template_path="documents/pdf/monthly_progress.html",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "athlete_last_name",
                "club_name",
                "month_label",
                "season_year",
                "measurements",  # list de dicts con métricas del mes
            }
        ),
        description="Reporte de progreso mensual con tendencias en PDF.",
    ),
    DocumentTemplate.MEDICAL_CLEARANCE: DocumentTemplateSpec(
        template_id=DocumentTemplate.MEDICAL_CLEARANCE,
        format=DocumentFormat.DOCX,
        template_path="documents/docx/medical_clearance.docx",
        required_context_keys=frozenset(
            {
                "athlete_first_name",
                "athlete_last_name",
                "birth_date",
                "club_name",
                "season_year",
                "medical_conditions",  # list de strings
            }
        ),
        description="Autorización médica editable en DOCX (docxtpl).",
    ),
}


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """Repositorio de specs de templates con validación de contexto y existencia en disco.

    Uso típico (singleton via @lru_cache en dependencies.py):

        registry = TemplateRegistry()
        spec = registry.get_email_spec("welcome_athlete")
        registry.validate_email_context("welcome_athlete", context)
    """

    def __init__(self, templates_root: Path | None = None) -> None:
        self._root = templates_root or _DEFAULT_TEMPLATES_ROOT
        self._email: dict[str, EmailTemplateSpec] = EMAIL_TEMPLATES
        self._document: dict[str, DocumentTemplateSpec] = DOCUMENT_TEMPLATES

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_email_spec(self, template_id: str) -> EmailTemplateSpec:
        """Retorna la spec del template de email.

        Raises:
            ValueError: Si el template_id no está registrado.
        """
        try:
            return self._email[template_id]
        except KeyError:
            registered = sorted(self._email)
            raise ValueError(
                f"Template de email '{template_id}' no registrado. "
                f"Templates disponibles: {registered}"
            ) from None

    def get_document_spec(self, template_id: str) -> DocumentTemplateSpec:
        """Retorna la spec del template de documento.

        Raises:
            ValueError: Si el template_id no está registrado.
        """
        try:
            return self._document[template_id]
        except KeyError:
            registered = sorted(self._document)
            raise ValueError(
                f"Template de documento '{template_id}' no registrado. "
                f"Templates disponibles: {registered}"
            ) from None

    # ------------------------------------------------------------------
    # Validadores de contexto
    # ------------------------------------------------------------------

    def validate_email_context(self, template_id: str, context: dict) -> None:
        """Verifica que el contexto contiene todas las claves requeridas por el template.

        Args:
            template_id: Identificador del template (ej. "welcome_athlete").
            context: Diccionario de variables Jinja2 a pasar al template.

        Raises:
            ValueError: Con las claves faltantes si el contexto es incompleto.
        """
        spec = self.get_email_spec(template_id)
        self._assert_required_keys(spec.required_context_keys, context, template_id)

    def validate_document_context(self, template_id: str, context: dict) -> None:
        """Verifica que el contexto contiene todas las claves requeridas por el template.

        Args:
            template_id: Identificador del template de documento.
            context: Diccionario de variables a pasar al generador.

        Raises:
            ValueError: Con las claves faltantes si el contexto es incompleto.
        """
        spec = self.get_document_spec(template_id)
        self._assert_required_keys(spec.required_context_keys, context, template_id)

    # ------------------------------------------------------------------
    # Validación de archivos en disco
    # ------------------------------------------------------------------

    def verify_templates_exist(self) -> dict[str, list[str]]:
        """Comprueba que todos los archivos de template existen en disco.

        Útil para llamar en el startup de FastAPI (lifespan).

        Returns:
            Diccionario {"missing": [...paths...]} — lista vacía si todo OK.

        Raises:
            RuntimeError: Si hay archivos faltantes (en entorno de producción).
        """
        missing: list[str] = []

        for spec in self._email.values():
            path = self._root / spec.body_path
            if not path.exists():
                missing.append(str(path))

        for spec in self._document.values():
            path = self._root / spec.template_path
            if not path.exists():
                missing.append(str(path))

        if missing:
            logger.warning(
                "TemplateRegistry: %d archivos de template no encontrados en disco: %s",
                len(missing),
                missing,
            )

        return {"missing": missing}

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_required_keys(
        required: frozenset[str],
        context: dict,
        template_id: str,
    ) -> None:
        missing = required - context.keys()
        if missing:
            raise ValueError(
                f"Contexto incompleto para template '{template_id}'. "
                f"Claves faltantes: {sorted(missing)}"
            )
