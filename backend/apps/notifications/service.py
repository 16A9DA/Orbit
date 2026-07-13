"""Notification dispatch: in-app record plus optional Discord webhook."""
import logging

import requests
from django.conf import settings

from apps.monitoring.models import Alert, Notification

log = logging.getLogger(__name__)

EMOJI = {"critical": "\U0001f6a8", "warning": "⚠️", "success": "\U0001f7e2", "info": "ℹ️"}


def notify(severity, title, body="", source="", make_alert=True, discord=None):
    """Create in-app notification, optional alert, optional Discord push."""
    note = Notification.objects.create(severity=severity, title=title, body=body)
    if make_alert and severity in ("critical", "warning", "success"):
        Alert.objects.create(severity=severity, title=title, description=body, source=source)

    send_discord = settings.DISCORD_WEBHOOK_URL and (
        discord if discord is not None else severity in ("critical", "warning")
    )
    if send_discord:
        note.delivered_discord = _push_discord(severity, title, body)
        note.save(update_fields=["delivered_discord"])
    return note


def _push_discord(severity, title, body):
    content = f"{EMOJI.get(severity, '')} **{title}**"
    if body:
        content += f"\n{body}"
    try:
        r = requests.post(settings.DISCORD_WEBHOOK_URL, json={"content": content}, timeout=10)
        return r.ok
    except requests.RequestException as e:  # network failure must not break monitoring
        log.warning("Discord webhook failed: %s", e)
        return False
