"""SMTP transport. Exceptions are handled without logging provider messages."""
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


def send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_username or not settings.smtp_password.get_secret_value():
        raise RuntimeError('Email is not configured')
    message = EmailMessage()
    message['From'] = settings.smtp_username
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
