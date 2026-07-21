import smtplib
from unittest.mock import MagicMock, patch

import pytest

from freyja_backend.core.email import (
    EmailDeliveryError,
    EmailMessage,
    InMemoryEmailSender,
    SmtpConfig,
    SmtpEmailSender,
    get_email_sender,
    set_email_sender_override,
)

_CONFIG = SmtpConfig(
    host="127.0.0.1",
    port=1025,
    use_tls=False,
    from_address="dev@freyja.local",
)


def test_in_memory_email_sender_captures_messages() -> None:
    sender = InMemoryEmailSender()
    message = EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="Cuerpo")

    sender.send(message)

    assert sender.sent_messages == [message]


def test_smtp_email_sender_sends_via_smtplib() -> None:
    smtp_client = MagicMock()
    smtp_client.__enter__.return_value = smtp_client

    with patch("smtplib.SMTP", return_value=smtp_client) as smtp_cls:
        sender = SmtpEmailSender(_CONFIG)
        sender.send(EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="Cuerpo"))

    smtp_cls.assert_called_once_with(_CONFIG.host, _CONFIG.port, timeout=_CONFIG.timeout_seconds)
    smtp_client.send_message.assert_called_once()
    smtp_client.starttls.assert_not_called()
    smtp_client.login.assert_not_called()


def test_smtp_email_sender_uses_starttls_when_configured() -> None:
    config = SmtpConfig(host="smtp.example.dev", port=587, use_tls=True, from_address="a@b.dev")
    smtp_client = MagicMock()
    smtp_client.__enter__.return_value = smtp_client

    with patch("smtplib.SMTP", return_value=smtp_client):
        SmtpEmailSender(config).send(
            EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="Cuerpo")
        )

    smtp_client.starttls.assert_called_once()


def test_smtp_email_sender_logs_in_when_credentials_configured() -> None:
    config = SmtpConfig(
        host="smtp.example.dev",
        port=587,
        use_tls=False,
        from_address="a@b.dev",
        username="user",
        password="secret",
    )
    smtp_client = MagicMock()
    smtp_client.__enter__.return_value = smtp_client

    with patch("smtplib.SMTP", return_value=smtp_client):
        SmtpEmailSender(config).send(
            EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="Cuerpo")
        )

    smtp_client.login.assert_called_once_with("user", "secret")


def test_smtp_email_sender_wraps_smtp_exception_without_leaking_details() -> None:
    with (
        patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "boom")),
        pytest.raises(EmailDeliveryError) as excinfo,
    ):
        SmtpEmailSender(_CONFIG).send(
            EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="secret-body")
        )

    assert "secret-body" not in str(excinfo.value)
    assert "user@freyja-test.dev" not in str(excinfo.value)


def test_smtp_email_sender_wraps_os_error() -> None:
    with (
        patch("smtplib.SMTP", side_effect=OSError("connection refused")),
        pytest.raises(EmailDeliveryError),
    ):
        SmtpEmailSender(_CONFIG).send(
            EmailMessage(to="user@freyja-test.dev", subject="Hola", text_body="Cuerpo")
        )


def test_get_email_sender_returns_smtp_sender_by_default() -> None:
    set_email_sender_override(None)
    sender = get_email_sender(_CONFIG)
    assert isinstance(sender, SmtpEmailSender)


def test_get_email_sender_prefers_override_when_set() -> None:
    override = InMemoryEmailSender()
    set_email_sender_override(override)
    try:
        assert get_email_sender(_CONFIG) is override
    finally:
        set_email_sender_override(None)
