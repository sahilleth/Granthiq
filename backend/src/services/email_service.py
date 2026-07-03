
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from loguru import logger
from src.config import get_settings

settings = get_settings()

def send_email_sync(to_email: str, subject: str, html_content: str):
    """
    Synchronous function to send email via SMTP.
    Should be run in a separate thread to avoid blocking.
    """
    if not settings.email.enabled:
        logger.warning("Email service is disabled. Set EMAIL_ENABLED=true to enable.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.email.from_name} <{settings.email.from_email}>"
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(html_content, 'html'))

        logger.info(f"Connecting to SMTP server: {settings.email.smtp_host}:{settings.email.smtp_port}")
        
        # Connect to server
        if settings.email.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.email.smtp_host, settings.email.smtp_port)
        else:
            server = smtplib.SMTP(settings.email.smtp_host, settings.email.smtp_port)
            if settings.email.tls:
                server.starttls()

        server.login(settings.email.smtp_user, settings.email.smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent successfully to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        # We don't raise here to prevent crashing the flow, but depending on requirements we might want to.
        # For now, just log error.

async def send_email(to_email: str, subject: str, html_content: str):
    """
    Async wrapper for sending email in a separate thread.
    Usage:
        await send_email("user@example.com", "Welcome", "<h1>Hello</h1>")
    """
    if not settings.email.enabled:
        return
        
    await asyncio.to_thread(send_email_sync, to_email, subject, html_content)
