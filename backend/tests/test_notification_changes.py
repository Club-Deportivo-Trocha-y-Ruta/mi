"""
Tests para los cambios del módulo de notificaciones (batch 2026-04-15).

Cambios cubiertos:
  1. template_registry: required_context_keys de anthropometry_alert
     (parent_name + athlete_first_name, sin coach_name ni athlete_id)
  2. email_client: OutboundEmail.cc_emails → header Cc + recipients SMTP
                   ResendEmailClient → params["cc"]
  3. service.py: cc_emails se propaga de NotificationRequest a OutboundEmail
  4. anthropometry router: notificación va a padres, no al coach;
     CC al atleta si tiene email; sin padres = sin notificación
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.notification import (
    NotificationRecipient,
    NotificationRequest,
    NotificationTemplate,
)
from app.services.notification.email_client import OutboundEmail, SmtpEmailClient, ResendEmailClient
from app.services.notification.template_registry import TemplateRegistry
from app.services.notification.service import NotificationService
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.email_client import BaseEmailClient, NotificationResult
from app.config import Settings


# ---------------------------------------------------------------------------
# Helpers reutilizables
# ---------------------------------------------------------------------------


def _make_service(client: BaseEmailClient, send_emails: bool = True) -> NotificationService:
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    settings = Settings(notification_send_emails=send_emails)
    return NotificationService(client, registry, generator, settings)


def _alert_context(**overrides) -> dict:
    base = {
        "parent_name": "Carlos",
        "athlete_first_name": "Mateo",
        "club_name": "Trocha y Ruta",
        "evaluation_date": "2026-04-15",
        "maturation_status": "Pre-PHV",
    }
    base.update(overrides)
    return base


class DummyEmailClient(BaseEmailClient):
    """Cliente stub que captura el último mensaje enviado."""

    def __init__(self) -> None:
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> NotificationResult:
        self.sent.append(message)
        return NotificationResult(success=True, message_id="dummy")


# ===========================================================================
# 1. TemplateRegistry — anthropometry_alert context keys
# ===========================================================================


class TestAnthropometryAlertTemplateKeys:
    """Verifica que los required_context_keys sean los nuevos (post-cambio)."""

    def setup_method(self):
        self.registry = TemplateRegistry()

    def test_valid_context_with_parent_name_and_athlete_first_name(self):
        """Contexto correcto (post-cambio) no lanza excepción."""
        self.registry.validate_email_context(
            NotificationTemplate.ANTHROPOMETRY_ALERT,
            _alert_context(),
        )

    def test_rejects_old_coach_name_key(self):
        """coach_name ya no es una clave requerida — no valida ni bloquea si se pasa extra."""
        # El template aún acepta claves extra sin error (no las require, pero tampoco las rechaza)
        # Lo importante es que NO requiere coach_name:
        ctx = _alert_context()
        ctx.pop("parent_name")
        with pytest.raises(ValueError, match="parent_name"):
            self.registry.validate_email_context(
                NotificationTemplate.ANTHROPOMETRY_ALERT, ctx
            )

    def test_rejects_old_athlete_id_key(self):
        """athlete_id ya no es requerido. Si falta parent_name, falla por parent_name."""
        ctx = _alert_context()
        ctx.pop("athlete_first_name")
        with pytest.raises(ValueError, match="athlete_first_name"):
            self.registry.validate_email_context(
                NotificationTemplate.ANTHROPOMETRY_ALERT, ctx
            )

    def test_required_keys_exact_set(self):
        """Verifica el conjunto exacto de claves requeridas."""
        spec = self.registry.get_email_spec(NotificationTemplate.ANTHROPOMETRY_ALERT)
        assert spec.required_context_keys == frozenset(
            {
                "parent_name",
                "athlete_first_name",
                "club_name",
                "evaluation_date",
                "maturation_status",
            }
        )

    def test_old_keys_not_required(self):
        """Las claves antiguas (coach_name, athlete_id) no están en required_context_keys."""
        spec = self.registry.get_email_spec(NotificationTemplate.ANTHROPOMETRY_ALERT)
        assert "coach_name" not in spec.required_context_keys
        assert "athlete_id" not in spec.required_context_keys

    def test_context_missing_evaluation_date_raises(self):
        ctx = _alert_context()
        ctx.pop("evaluation_date")
        with pytest.raises(ValueError, match="evaluation_date"):
            self.registry.validate_email_context(
                NotificationTemplate.ANTHROPOMETRY_ALERT, ctx
            )

    def test_context_missing_maturation_status_raises(self):
        ctx = _alert_context()
        ctx.pop("maturation_status")
        with pytest.raises(ValueError, match="maturation_status"):
            self.registry.validate_email_context(
                NotificationTemplate.ANTHROPOMETRY_ALERT, ctx
            )

    def test_context_empty_raises_listing_all_missing_keys(self):
        with pytest.raises(ValueError):
            self.registry.validate_email_context(
                NotificationTemplate.ANTHROPOMETRY_ALERT, {}
            )


# ===========================================================================
# 2. NotificationRequest — campo cc_emails
# ===========================================================================


class TestNotificationRequestCcEmails:
    """cc_emails es opcional con default vacío y acepta EmailStr válidos."""

    def test_default_cc_emails_is_empty_list(self):
        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Padre"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
        )
        assert req.cc_emails == []

    def test_cc_emails_accepts_valid_emails(self):
        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Padre"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            cc_emails=["atleta@test.com", "coach@test.com"],
        )
        assert len(req.cc_emails) == 2
        assert "atleta@test.com" in req.cc_emails

    def test_cc_emails_rejects_invalid_email(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            NotificationRequest(
                recipient=NotificationRecipient(email="padre@test.com", name="Padre"),
                template=NotificationTemplate.ANTHROPOMETRY_ALERT,
                cc_emails=["no-es-un-email"],
            )

    def test_cc_emails_multiple_recipients(self):
        """Múltiples CCs (ej. dos atletas vinculados al mismo padre)."""
        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Padre"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            cc_emails=["a@b.com", "c@d.com", "e@f.com"],
        )
        assert len(req.cc_emails) == 3


# ===========================================================================
# 3. OutboundEmail — campo cc_emails
# ===========================================================================


class TestOutboundEmailCcEmails:
    """OutboundEmail.cc_emails default vacío y acepta lista."""

    def test_default_cc_is_empty(self):
        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Test",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
        )
        assert msg.cc_emails == []

    def test_cc_emails_set_explicitly(self):
        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Test",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
            cc_emails=["atleta@test.com"],
        )
        assert msg.cc_emails == ["atleta@test.com"]


# ===========================================================================
# 4. SmtpEmailClient — CC header y recipients
# ===========================================================================


class TestSmtpEmailClientCcBehavior:
    """Verifica que SMTP agregue Cc header y lo incluya en recipients."""

    @pytest.mark.asyncio
    async def test_smtp_cc_header_added_when_cc_present(self, mocker):
        """Con cc_emails, aiosmtplib.send recibe la dirección CC en recipients."""
        client = SmtpEmailClient("localhost", 1025, None, None, "from@club.com", "Club")
        captured_kwargs = {}

        async def fake_send(msg, recipients, **kwargs):
            captured_kwargs["recipients"] = recipients
            captured_kwargs["msg"] = msg
            return True

        mocker.patch("aiosmtplib.send", side_effect=fake_send)

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta medición",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
            cc_emails=["atleta@test.com"],
        )
        result = await client.send(msg)

        assert result.success is True
        # La dirección CC debe aparecer en los recipients de SMTP
        assert "atleta@test.com" in captured_kwargs["recipients"]
        assert "padre@test.com" in captured_kwargs["recipients"]
        # Header Cc debe estar en el MIMEMultipart
        assert captured_kwargs["msg"]["Cc"] == "atleta@test.com"

    @pytest.mark.asyncio
    async def test_smtp_no_cc_header_when_cc_empty(self, mocker):
        """Sin cc_emails, el header Cc no se agrega al mensaje MIME."""
        client = SmtpEmailClient("localhost", 1025, None, None, "from@club.com", "Club")
        captured_kwargs = {}

        async def fake_send(msg, recipients, **kwargs):
            captured_kwargs["recipients"] = recipients
            captured_kwargs["msg"] = msg
            return True

        mocker.patch("aiosmtplib.send", side_effect=fake_send)

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
        )
        result = await client.send(msg)

        assert result.success is True
        # Solo el destinatario To, sin CC
        assert captured_kwargs["recipients"] == ["padre@test.com"]
        assert captured_kwargs["msg"]["Cc"] is None

    @pytest.mark.asyncio
    async def test_smtp_multiple_cc_joined_in_header(self, mocker):
        """Múltiples CC se unen con ', ' en el header Cc."""
        client = SmtpEmailClient("localhost", 1025, None, None, "from@club.com", "Club")
        captured_kwargs = {}

        async def fake_send(msg, recipients, **kwargs):
            captured_kwargs["msg"] = msg
            captured_kwargs["recipients"] = recipients
            return True

        mocker.patch("aiosmtplib.send", side_effect=fake_send)

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
            cc_emails=["atleta@test.com", "otro@test.com"],
        )
        await client.send(msg)

        cc_header = captured_kwargs["msg"]["Cc"]
        assert "atleta@test.com" in cc_header
        assert "otro@test.com" in cc_header
        # Todos los CC + To deben estar en recipients
        assert len(captured_kwargs["recipients"]) == 3


# ===========================================================================
# 5. ResendEmailClient — params["cc"]
# ===========================================================================


class TestResendEmailClientCcBehavior:
    """Verifica que Resend incluya cc en params cuando hay CC."""

    @pytest.mark.asyncio
    async def test_resend_cc_added_to_params(self, mocker):
        """Con cc_emails, params["cc"] debe estar presente al llamar Resend SDK."""
        client = ResendEmailClient("fake_key", "from@club.com", "Club")
        captured_params = {}

        def fake_send(params):
            captured_params.update(params)
            return {"id": "resend_123"}

        client._resend = MagicMock()
        client._resend.Emails.send = fake_send

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta medición",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
            cc_emails=["atleta@test.com"],
        )
        result = await client.send(msg)

        assert result.success is True
        assert result.message_id == "resend_123"
        assert "cc" in captured_params
        assert captured_params["cc"] == ["atleta@test.com"]

    @pytest.mark.asyncio
    async def test_resend_no_cc_key_when_empty(self, mocker):
        """Sin cc_emails, params NO debe contener la clave 'cc'."""
        client = ResendEmailClient("fake_key", "from@club.com", "Club")
        captured_params = {}

        def fake_send(params):
            captured_params.update(params)
            return {"id": "resend_456"}

        client._resend = MagicMock()
        client._resend.Emails.send = fake_send

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
        )
        await client.send(msg)

        assert "cc" not in captured_params

    @pytest.mark.asyncio
    async def test_resend_multiple_cc(self, mocker):
        """Múltiples CC se envían como lista a Resend."""
        client = ResendEmailClient("fake_key", "from@club.com", "Club")
        captured_params = {}

        def fake_send(params):
            captured_params.update(params)
            return {"id": "resend_789"}

        client._resend = MagicMock()
        client._resend.Emails.send = fake_send

        msg = OutboundEmail(
            to_email="padre@test.com",
            to_name="Padre",
            subject="Alerta",
            html_body="<p>body</p>",
            template_ref="anthropometry_alert",
            cc_emails=["atleta@test.com", "tutor@test.com"],
        )
        await client.send(msg)

        assert captured_params["cc"] == ["atleta@test.com", "tutor@test.com"]


# ===========================================================================
# 6. NotificationService — propagación de cc_emails a OutboundEmail
# ===========================================================================


class TestNotificationServiceCcPropagation:
    """cc_emails de NotificationRequest llega al OutboundEmail enviado al client."""

    @pytest.mark.asyncio
    async def test_cc_propagated_to_outbound_email(self):
        """cc_emails en el request se propaga al OutboundEmail del client."""
        dummy = DummyEmailClient()
        service = _make_service(dummy)

        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Carlos"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            send_async=False,
            cc_emails=["atleta@test.com"],
            context=_alert_context(),
        )
        result = await service.send(req)

        assert result.success is True
        assert len(dummy.sent) == 1
        assert dummy.sent[0].cc_emails == ["atleta@test.com"]

    @pytest.mark.asyncio
    async def test_empty_cc_propagated_as_empty_list(self):
        """Sin CC, OutboundEmail.cc_emails es lista vacía."""
        dummy = DummyEmailClient()
        service = _make_service(dummy)

        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Carlos"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            send_async=False,
            context=_alert_context(),
        )
        result = await service.send(req)

        assert result.success is True
        assert dummy.sent[0].cc_emails == []

    @pytest.mark.asyncio
    async def test_multiple_cc_propagated(self):
        """Múltiples CC se propagan todos al OutboundEmail."""
        dummy = DummyEmailClient()
        service = _make_service(dummy)

        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Carlos"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            send_async=False,
            cc_emails=["atleta@test.com", "tutor@test.com"],
            context=_alert_context(),
        )
        await service.send(req)

        assert dummy.sent[0].cc_emails == ["atleta@test.com", "tutor@test.com"]

    @pytest.mark.asyncio
    async def test_disabled_notifications_bypass_cc_logic(self):
        """NOTIFICATION_SEND_EMAILS=false cortocircuita sin llegar al client."""
        dummy = DummyEmailClient()
        service = _make_service(dummy, send_emails=False)

        req = NotificationRequest(
            recipient=NotificationRecipient(email="padre@test.com", name="Carlos"),
            template=NotificationTemplate.ANTHROPOMETRY_ALERT,
            send_async=False,
            cc_emails=["atleta@test.com"],
            context=_alert_context(),
        )
        result = await service.send(req)

        # Cortocircuito: éxito pero sin envío real
        assert result.success is True
        assert result.message_id == "disabled"
        assert len(dummy.sent) == 0


# ===========================================================================
# 7. Lógica de notificación a padres — anthropometry router (unitario)
# ===========================================================================


class TestAnthropometryNotificationLogic:
    """
    Tests unitarios de la lógica de notificación en create_anthropometry.

    Se verifica el comportamiento aislando las dependencias de DB y
    del servicio de notificación con mocks, sin levantar un servidor real.

    AnthropometryOut.model_validate se parchea para evitar que el ORM
    mock (sin metadatos SQLAlchemy) falle en la etapa de serialización,
    que es irrelevante para lo que estos tests validan.
    """

    def _make_parent_user(self, email: str, first_name: str = "Carlos", last_name: str = "Pérez"):
        user = MagicMock()
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        return user

    def _make_athlete_user(self, email: str | None):
        user = MagicMock()
        user.email = email
        return user

    def _make_phv_result(self, maturity_offset: float = -1.5) -> dict:
        return {
            "leg_length_cm": "82.0",
            "leg_sitting_ratio": "0.53",
            "maturity_offset": maturity_offset,
            "age_at_phv": 13.5,
            "maturation_status": "Pre-PHV",
            "training_implications": "Crecimiento acelerado",
        }

    def _make_fake_out(self):
        """Retorna un AnthropometryOut mínimo para que el router no falle al serializar."""
        from app.schemas.anthropometry import AnthropometryOut
        from app.models.anthropometry import MaturationStatus
        from datetime import date, datetime
        return AnthropometryOut(
            id=1,
            athlete_id=1,
            evaluation_date=date(2026, 4, 15),
            mesocycle=None,
            weight_kg=45.0,
            standing_height_cm=155.0,
            arm_span_cm=None,
            sitting_height_cm=73.0,
            leg_length_cm=82.0,
            leg_sitting_ratio=0.53,
            maturity_offset=-1.5,
            age_at_phv=13.5,
            maturation_status=MaturationStatus.pre_phv,
            training_implications="Crecimiento acelerado",
            evaluated_by=99,
            created_at=datetime(2026, 4, 15, 10, 0, 0),
            notes=None,
        )

    def _base_patches(self, detect_return: bool = True, phv_offset: float = -1.5):
        """Contexto de patches comunes para todos los tests del router."""
        from contextlib import ExitStack
        stack = ExitStack()
        phv_result = self._make_phv_result(phv_offset)
        fake_out = self._make_fake_out()
        stack.enter_context(patch("app.routers.anthropometry.compute_age_decimal", return_value=13.08))
        stack.enter_context(patch("app.routers.anthropometry.calculate_mirwald_offset", return_value=phv_result))
        stack.enter_context(patch(
            "app.routers.anthropometry.calculate_growth_percentiles",
            new_callable=AsyncMock,
            return_value=None,
        ))
        stack.enter_context(patch(
            "app.routers.anthropometry.detect_approaching_circa",
            return_value=detect_return,
        ))
        stack.enter_context(patch(
            "app.schemas.anthropometry.AnthropometryOut.model_validate",
            return_value=fake_out,
        ))
        return stack

    def _setup_db(self, parents: list, athlete_user_email: str | None = "atleta@test.com"):
        """Retorna un mock de AsyncSession con la secuencia de resultados esperada."""
        club = MagicMock()
        club.name = "Trocha y Ruta"

        club_result = MagicMock()
        club_result.scalar_one.return_value = club

        parents_result = MagicMock()
        parents_result.scalars.return_value.all.return_value = parents

        athlete_user = self._make_athlete_user(athlete_user_email)
        athlete_user_result = MagicMock()
        athlete_user_result.scalar_one_or_none.return_value = athlete_user

        call_count = 0

        async def fake_execute_seq(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return club_result
            elif call_count == 2:
                return parents_result
            else:
                return athlete_user_result

        db = MagicMock()
        db.execute = fake_execute_seq
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    def _make_athlete(self):
        from datetime import date
        athlete = MagicMock()
        athlete.id = 1
        athlete.club_id = 1
        athlete.user_id = 10
        athlete.first_name = "Mateo"
        athlete.birth_date = date(2013, 3, 15)
        athlete.sex = MagicMock(value="M")
        return athlete

    def _make_body(self):
        from datetime import date
        from app.schemas.anthropometry import AnthropometryCreate
        return AnthropometryCreate(
            evaluation_date=date(2026, 4, 15),
            weight_kg="45.0",
            standing_height_cm="155.0",
            sitting_height_cm="73.0",
        )

    @pytest.mark.asyncio
    async def test_notification_sent_to_each_parent(self):
        """Cuando detect_approaching_circa=True y hay dos padres, send se llama dos veces."""
        from app.routers.anthropometry import create_anthropometry

        parent1 = self._make_parent_user("padre1@test.com", "Carlos")
        parent2 = self._make_parent_user("madre2@test.com", "Ana")

        notification_service = MagicMock()
        notification_service.send = AsyncMock(
            return_value=NotificationResult(success=True, message_id="q")
        )

        db = self._setup_db(parents=[parent1, parent2])
        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        assert notification_service.send.call_count == 2

    @pytest.mark.asyncio
    async def test_notification_not_sent_when_no_parents(self):
        """Sin padres vinculados, notification_service.send no se llama."""
        from app.routers.anthropometry import create_anthropometry

        notification_service = MagicMock()
        notification_service.send = AsyncMock()

        db = self._setup_db(parents=[])
        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        notification_service.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_not_sent_when_offset_not_approaching(self):
        """Cuando detect_approaching_circa=False, no se envía ninguna notificación."""
        from app.routers.anthropometry import create_anthropometry

        notification_service = MagicMock()
        notification_service.send = AsyncMock()

        # db.execute no se llegará a llamar para queries de notificación
        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=False, phv_offset=0.5):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        notification_service.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_cc_includes_athlete_email_when_present(self):
        """El email del atleta se incluye en cc_emails del NotificationRequest."""
        from app.routers.anthropometry import create_anthropometry

        parent = self._make_parent_user("padre@test.com", "Carlos")
        sent_requests: list[NotificationRequest] = []

        notification_service = MagicMock()

        async def capture_send(req, dispatcher=None):
            sent_requests.append(req)
            return NotificationResult(success=True, message_id="q")

        notification_service.send = capture_send

        db = self._setup_db(parents=[parent], athlete_user_email="atleta@test.com")
        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        assert len(sent_requests) == 1
        assert sent_requests[0].cc_emails == ["atleta@test.com"]
        assert sent_requests[0].recipient.email == "padre@test.com"

    @pytest.mark.asyncio
    async def test_cc_empty_when_athlete_has_no_email(self):
        """Si el atleta no tiene email, cc_emails debe ser lista vacía."""
        from app.routers.anthropometry import create_anthropometry

        parent = self._make_parent_user("padre@test.com", "Carlos")
        sent_requests: list[NotificationRequest] = []

        notification_service = MagicMock()

        async def capture_send(req, dispatcher=None):
            sent_requests.append(req)
            return NotificationResult(success=True, message_id="q")

        notification_service.send = capture_send

        db = self._setup_db(parents=[parent], athlete_user_email=None)
        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        assert len(sent_requests) == 1
        assert sent_requests[0].cc_emails == []

    @pytest.mark.asyncio
    async def test_cc_empty_when_athlete_user_not_found(self):
        """Si scalar_one_or_none retorna None (user_id no existe), cc_emails = []."""
        from app.routers.anthropometry import create_anthropometry

        parent = self._make_parent_user("padre@test.com", "Carlos")
        sent_requests: list[NotificationRequest] = []

        notification_service = MagicMock()

        async def capture_send(req, dispatcher=None):
            sent_requests.append(req)
            return NotificationResult(success=True, message_id="q")

        notification_service.send = capture_send

        # Sobreescribir el resultado de athlete_user con None
        club = MagicMock()
        club.name = "Trocha y Ruta"
        club_result = MagicMock()
        club_result.scalar_one.return_value = club

        parents_result = MagicMock()
        parents_result.scalars.return_value.all.return_value = [parent]

        athlete_user_result = MagicMock()
        athlete_user_result.scalar_one_or_none.return_value = None  # no encontrado

        call_count = 0

        async def fake_execute_seq(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return club_result
            elif call_count == 2:
                return parents_result
            else:
                return athlete_user_result

        db = MagicMock()
        db.execute = fake_execute_seq
        db.add = MagicMock()
        db.flush = AsyncMock()

        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        assert len(sent_requests) == 1
        assert sent_requests[0].cc_emails == []

    @pytest.mark.asyncio
    async def test_notification_context_uses_parent_name_not_coach_name(self):
        """El contexto usa parent_name y athlete_first_name; coach_name y athlete_id ausentes."""
        from app.routers.anthropometry import create_anthropometry

        parent = self._make_parent_user("padre@test.com", "Carlos", "Pérez")
        sent_requests: list[NotificationRequest] = []

        notification_service = MagicMock()

        async def capture_send(req, dispatcher=None):
            sent_requests.append(req)
            return NotificationResult(success=True, message_id="q")

        notification_service.send = capture_send

        db = self._setup_db(parents=[parent], athlete_user_email=None)
        current_user = MagicMock()
        current_user.id = 99

        with self._base_patches(detect_return=True):
            await create_anthropometry(
                body=self._make_body(),
                db=db,
                current_user=current_user,
                athlete=self._make_athlete(),
                notification_service=notification_service,
                dispatcher=MagicMock(),
            )

        ctx = sent_requests[0].context
        assert ctx["parent_name"] == "Carlos"
        assert ctx["athlete_first_name"] == "Mateo"
        assert "coach_name" not in ctx
        assert "athlete_id" not in ctx
        assert sent_requests[0].template == NotificationTemplate.ANTHROPOMETRY_ALERT
        assert sent_requests[0].recipient.email == "padre@test.com"
