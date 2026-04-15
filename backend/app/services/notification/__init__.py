# Re-exports públicos del módulo notification (Paso 6 completo).

from app.services.notification.email_client import create_email_client
from app.services.notification.service import NotificationService
from app.services.notification.template_registry import TemplateRegistry

__all__ = ["NotificationService", "TemplateRegistry", "create_email_client"]
