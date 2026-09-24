import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

_email_logger = logging.getLogger("freyja_backend.email")


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class EmailDeliveryError(Exception):
    """Raised when the transport failed to hand off the message. Never carries
    the recipient, subject, body, or any credential — only what the caller
    needs to know: delivery did not happen.

    Callers in auth_service (register_user, request_password_reset) catch
    this and degrade gracefully, on purpose: they log a sanitized operational
    signal and still return the same generic success acknowledgement, rather
    than failing the whole request. This is deliberately NOT "fail-closed" —
    the account/token creation that already committed to PostgreSQL is what
    is fail-closed (an unexpected exception there rolls back and surfaces as
    a 500). A transient SMTP outage instead degrades to "the account/token
    exists but no email went out"; the user can get a working link by
    retrying register/forgot-password, since each call reissues and
    invalidates the previous pending token."""


class InMemoryEmailSender:
    """Test double: captures messages instead of sending them anywhere. Used
    exclusively by the test suite (see conftest.py's autouse override) — never
    reachable from application configuration."""

    def __init__(self) -> None:
        self.sent_messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent_messages.append(message)


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    use_tls: bool
    from_address: str
    username: str | None = None
    password: str | None = None
    timeout_seconds: float = 10.0


class SmtpEmailSender:
    """The only production email transport. Configuration (host/port/TLS/
    credentials) is what distinguishes a local Mailpit instance from a real
    provider — the code path is identical either way, so there is no separate
    "local" implementation to keep in sync or accidentally select in
    production."""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._config.from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)

        try:
            with smtplib.SMTP(
                self._config.host, self._config.port, timeout=self._config.timeout_seconds
            ) as client:
                if self._config.use_tls:
                    client.starttls(context=ssl.create_default_context())
                if self._config.username and self._config.password:
                    client.login(self._config.username, self._config.password)
                client.send_message(mime)
        except (smtplib.SMTPException, OSError) as exc:
            # Never log the recipient, subject, body, credentials, or the
            # server's raw response — only the exception's type.
            _email_logger.error("email_send_failed", extra={"error_type": type(exc).__name__})
            raise EmailDeliveryError("No se pudo enviar el correo.") from exc


_email_sender_override: EmailSender | None = None


def set_email_sender_override(sender: EmailSender | None) -> None:
    """Test-only hook: point the application at a different EmailSender."""
    global _email_sender_override
    _email_sender_override = sender


def get_email_sender(config: SmtpConfig) -> EmailSender:
    if _email_sender_override is not None:
        return _email_sender_override
    return SmtpEmailSender(config)
