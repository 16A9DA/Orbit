import logging

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.sendgrid.com/v3"

BOUNCE_ALERT = 0.15


def collect():
    if not settings.SENDGRID_API_KEY:
        return _mock()
    try:
        h = {"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"}
        r = requests.get(f"{API}/stats", headers=h,
                         params={"aggregated_by": "day", "limit": 1}, timeout=15)
        r.raise_for_status()
        stats = _flatten(r.json())
        upsert_service("SendGrid", "sendgrid", "operational", stats)
        log_activity("sendgrid", f"Delivered {stats.get('delivered', 0)} emails")
        _check_suspicious(stats)
        return stats
    except requests.RequestException as e:
        log.warning("SendGrid collect failed: %s", e)
        upsert_service("SendGrid", "sendgrid", "unknown", {"error": str(e)})
        return {"error": str(e)}


def _flatten(payload):
    metrics = {}
    for day in payload:
        for s in day.get("stats", []):
            for k, v in s.get("metrics", {}).items():
                metrics[k] = metrics.get(k, 0) + v
    return metrics


def _check_suspicious(stats):
    requests_sent = stats.get("requests", 0)
    bounces = stats.get("bounces", 0) + stats.get("blocks", 0)
    if requests_sent and bounces / requests_sent > BOUNCE_ALERT:
        notify("warning", "SendGrid suspicious activity",
               f"Bounce/block rate {bounces}/{requests_sent} exceeds "
               f"{BOUNCE_ALERT:.0%}.", source="sendgrid")


def _mock():
    stats = {"requests": 540, "delivered": 512, "bounces": 8, "blocks": 2,
             "opens": 320, "mock": True}
    upsert_service("SendGrid", "sendgrid", "operational", stats)
    log_activity("sendgrid", "Delivered 512 emails", {"mock": True})
    return stats
