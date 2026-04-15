import pytest
import asyncio
from app.services.notification.email_client import SmtpEmailClient, ResendEmailClient, OutboundEmail

@pytest.mark.asyncio
async def test_smtp_email_client(mocker):
    client = SmtpEmailClient("localhost", 1025, None, None, "a@b.com", "Name")
    mocker.patch("aiosmtplib.send", return_value=True)
    msg = OutboundEmail("to@to.com", "To Name", "Subject", "<h1>Html</h1>", "template_ref")
    res = await client.send(msg)
    assert res.success is True

@pytest.mark.asyncio
async def test_resend_email_client(mocker):
    client = ResendEmailClient("fake_key", "a@b.com", "Name")
    mock_resend = mocker.patch("resend.Emails.send", return_value={"id": "msg_123"})
    client._resend = mocker.Mock()
    client._resend.Emails.send = mock_resend
    msg = OutboundEmail("to@to.com", "To", "Subj", "<p>Html</p>", "template_ref")
    res = await client.send(msg)
    assert res.success is True
    assert res.message_id == "msg_123"
