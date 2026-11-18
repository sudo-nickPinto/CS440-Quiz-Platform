"""One place that sends every email the app writes itself.

Roster invitations, join-request approvals and join-request rejections all go
through EmailService. Auth0 still sends its own sign-up and verification
emails; those are configured in the Auth0 dashboard, not here.

Which transport is used comes from EMAIL_BACKEND:

- ``log`` (the default): nothing leaves the machine; each message is printed
  in the server window. Good for local development.
- ``smtp``: sends through SMTP_HOST, with STARTTLS unless SMTP_STARTTLS=false
  (see docs/EMAIL.md).
- ``memory``: keeps messages in ``EmailService.outbox``, for tests.

Emails are sent after the database change is committed, from a background
task, and a failure is logged instead of undoing the change: a student who
was approved stays approved even if the mail server is down.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, parseaddr
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)

APP_NAME = "QuizBurg"


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str


class EmailTransport(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


class LogTransport:
    """Prints each email in the server window. The app doesn't configure
    logging, so an INFO log line would be hidden."""

    def send(self, message: OutgoingEmail) -> None:
        print(
            "\n--- Email not sent (EMAIL_BACKEND=log) ---\n"
            f"Subject: {message.subject}\n\n{message.body}\n"
            "------------------------------------------",
            flush=True,
        )


class MemoryTransport:
    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        self.outbox.append(message)


class SmtpTransport:
    def __init__(self, settings: Settings) -> None:
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password.get_secret_value()
        self.starttls = settings.smtp_starttls
        self.sender = settings.email_from
        self.timeout = settings.smtp_timeout_seconds

    def send(self, message: OutgoingEmail) -> None:
        mime = MimeMessage()
        name, address = parseaddr(self.sender)
        mime["From"] = formataddr((name or APP_NAME, address))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(mime)


def _transport_for(settings: Settings) -> EmailTransport:
    backend = settings.email_backend.strip().lower()
    if backend == "smtp":
        if not settings.smtp_host:
            raise ValueError("EMAIL_BACKEND=smtp needs SMTP_HOST.")
        return SmtpTransport(settings)
    if backend == "memory":
        return MemoryTransport()
    if backend == "log":
        return LogTransport()
    raise ValueError(f"Unknown EMAIL_BACKEND {settings.email_backend!r}.")


class EmailService:
    """Writes and sends the app's own emails."""

    def __init__(self, transport: EmailTransport, app_url: str) -> None:
        self.transport = transport
        self.app_url = app_url.rstrip("/")

    @classmethod
    def from_settings(cls, settings: Settings) -> EmailService:
        return cls(_transport_for(settings), settings.app_base_url)

    @property
    def outbox(self) -> list[OutgoingEmail]:
        """Messages kept by the memory transport (tests only)."""
        return getattr(self.transport, "outbox", [])

    # -- Messages --------------------------------------------------------

    def added_to_class(self, to: str, class_name: str, class_id: int) -> OutgoingEmail:
        """Sent when an organizer adds someone who already has an account.
        They are a student straight away; there is nothing to accept."""
        return OutgoingEmail(
            to=to,
            subject=f"You've been added to {class_name} on {APP_NAME}",
            body="\n".join(
                [
                    "Hello,",
                    "",
                    f"Your instructor added you to {class_name} on {APP_NAME}, "
                    "the class quiz app.",
                    "",
                    f"Open the class: {self.app_url}/app/classes/{class_id}",
                    "",
                    f"- {APP_NAME}",
                ]
            ),
        )

    def roster_invitation(
        self,
        to: str,
        class_name: str,
        *,
        has_account: bool = False,
        join_code: str | None = None,
    ) -> OutgoingEmail:
        """Sent to a roster email that has no account yet."""
        steps = (
            f"Create your {APP_NAME} account at {self.app_url} with this "
            f"email address ({to}). You'll be in the class as soon as you "
            "sign up."
        )
        lines = [
            "Hello,",
            "",
            f"Your instructor added you to {class_name} on {APP_NAME}, the "
            "class quiz app.",
            "",
            steps,
        ]
        if join_code:
            lines += [
                "",
                "You can also join straight away with this link:",
                f"{self.app_url}/app/join/class/{join_code}",
            ]
        lines += ["", f"- {APP_NAME}"]
        return OutgoingEmail(
            to=to,
            subject=f"You're invited to {class_name} on {APP_NAME}",
            body="\n".join(lines),
        )

    def join_approved(self, to: str, class_name: str, class_id: int) -> OutgoingEmail:
        return OutgoingEmail(
            to=to,
            subject=f"You're in {class_name}",
            body="\n".join(
                [
                    "Hello,",
                    "",
                    f"An organizer approved your request to join {class_name} "
                    f"on {APP_NAME}.",
                    "",
                    f"Open the class: {self.app_url}/app/classes/{class_id}",
                    "",
                    f"- {APP_NAME}",
                ]
            ),
        )

    def join_rejected(self, to: str, class_name: str) -> OutgoingEmail:
        return OutgoingEmail(
            to=to,
            subject=f"Your request to join {class_name}",
            body="\n".join(
                [
                    "Hello,",
                    "",
                    f"An organizer of {class_name} did not approve your request "
                    f"to join the class on {APP_NAME}.",
                    "",
                    "If you think this is a mistake, contact your instructor. "
                    "They can invite you directly.",
                    "",
                    f"- {APP_NAME}",
                ]
            ),
        )

    # -- Sending ---------------------------------------------------------

    def send_all(self, messages: list[OutgoingEmail]) -> None:
        """Send each message; log failures instead of raising."""
        for message in messages:
            try:
                self.transport.send(message)
            except Exception:
                # The address is personal data; log only the subject.
                logger.exception("Could not send email %r", message.subject)
