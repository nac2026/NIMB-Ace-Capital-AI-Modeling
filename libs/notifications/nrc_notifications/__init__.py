"""Email alert delivery — settings, SMTP sender, and templates."""
from .config import NotificationsSettings, get_notifications_settings
from .email_sender import EmailSender
from .templates import AlertItem, render_digest, render_internal_urgent, render_urgent

__all__ = [
    "NotificationsSettings",
    "get_notifications_settings",
    "EmailSender",
    "AlertItem",
    "render_urgent",
    "render_digest",
    "render_internal_urgent",
]
