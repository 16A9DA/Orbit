import logging
from urllib.parse import urlparse

import requests
from django.conf import settings

from apps.monitoring.models import Alert, Notification

log = logging.getLogger(__name__)

EMOJI = {"critical": "\U0001f6a8", "warning": "⚠️", "success": "\U0001f7e2", "info": "ℹ️"}

# Only Discord's own webhook hosts are allowed as targets. Prevents a tampered
# .env from turning notifications into an SSRF / data-exfiltration channel.
_ALLOWED_HOSTS = {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}

# Which Orbit channel each source posts to. Unknown sources use "alerts".
SOURCE_CHANNEL = {
    "github": "deployments",
    "render": "deployments",
    "render_billing": "billing",
    "gcp": "security",
    "sendgrid": "security",
    "assistant": "general",
}


def _valid_webhook(url):
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme == "https" and p.hostname in _ALLOWED_HOSTS and "/webhooks/" in p.path


def _resolve_url(channel):
    url = settings.DISCORD_CHANNELS.get(channel, "") or settings.DISCORD_WEBHOOK_URL
    return url if _valid_webhook(url) else ""


def notify(severity, title, body="", source="", make_alert=True, discord=None, channel=None):
    """Create in-app notification, optional alert, optional Discord push.

    channel: explicit Orbit channel name; otherwise derived from source.
    """
    note = Notification.objects.create(severity=severity, title=title, body=body)
    if make_alert and severity in ("critical", "warning", "success"):
        Alert.objects.create(severity=severity, title=title, description=body, source=source)

    want = discord if discord is not None else severity in ("critical", "warning")
    if want:
        target = channel or SOURCE_CHANNEL.get(source, "alerts")
        url = _resolve_url(target)
        if url:
            note.delivered_discord = _push_discord(url, severity, title, body)
            note.save(update_fields=["delivered_discord"])
        else:
            log.info("No valid Discord webhook for channel %r; in-app only.", target)
    return note



def _push_discord(url, severity, title, body):
    content = f"{EMOJI.get(severity, '')} **{title}**"
    if body:
        content += f"\n{body}"
    try:
        r = requests.post(url, json={"content": content}, timeout=10)
        return r.ok
    except requests.RequestException as e:  # network failure must not break monitoring
        log.warning("Discord webhook failed: %s", e)
        return False


# Direct assistant-generated message to a Discord channel
def send_discord_message(message, channel="general"):
    """Send a direct assistant-generated message to a Discord channel."""
    url = _resolve_url(channel)

    if not url:
        log.info("No valid Discord webhook for channel %r", channel)
        return False

    try:
        r = requests.post(
            url,
            json={"content": message},
            timeout=10,
        )
        return r.ok
    except requests.RequestException as e:
        log.warning("Discord direct message failed: %s", e)
        return False
