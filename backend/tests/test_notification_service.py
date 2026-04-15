import pytest
from app.schemas.notification import NotificationRequest, NotificationRecipient, NotificationTemplate
from app.services.notification.service import NotificationService
from app.services.notification.template_registry import TemplateRegistry
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.email_client import BaseEmailClient, NotificationResult
from app.config import Settings

class DummyEmailClient(BaseEmailClient):
    async def send(self, message):
        return NotificationResult(success=True, message_id="dummy_id")

@pytest.mark.asyncio
async def test_notification_service_send():
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    client = DummyEmailClient()
    settings = Settings(notification_send_emails=True)
    service = NotificationService(client, registry, generator, settings)
    
    req = NotificationRequest(
        recipient=NotificationRecipient(email="test@test.com", name="Test"),
        template=NotificationTemplate.WELCOME_ATHLETE,
        send_async=False,
        context={
            "athlete_first_name": "A", "club_name": "B",
            "season_year": 2024, "parent_name": "P"
        }
    )
    res = await service.send(req)
    assert res.success is True
    assert res.message_id == "dummy_id"
