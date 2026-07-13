import logging

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.sendgrid.com/v3"


BOUNCE_ALERT = 0.15
SPAM_ALERT = 0.05


def collect():
    if not settings.SENDGRID_API_KEY:
        return _mock()
    try:
        h = {"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"}
        r = requests.get(f"{API}/stats", headers=h,
                         params={"aggregated_by": "day", "limit": 7}, timeout=15)
        r.raise_for_status()
        stats = _flatten(r.json())

        stats.update(_get_reputation(h))

        status = _service_status(stats)

        upsert_service("SendGrid", "sendgrid", status, stats)
        log_activity(
            "sendgrid",
            f"Delivered {stats.get('delivered', 0)} emails",
            stats,
        )

        _check_suspicious(stats)
        return stats
    except requests.RequestException as e:
        log.warning("SendGrid collect failed: %s", e)
        upsert_service("SendGrid", "sendgrid", "unknown", {"error": str(e)})
        return {"error": str(e)}

# --- reputation and status helpers ---

def _get_reputation(headers):
    result = {}

    try:
        r = requests.get(
            f"{API}/user/credits",
            headers=headers,
            timeout=15,
        )
        if r.ok:
            result["credits"] = r.json()
    except requests.RequestException as e:
        log.warning("SendGrid reputation lookup failed: %s", e)

    return result


def _service_status(stats):
    requests_sent = stats.get("requests", 0)
    bounces = stats.get("bounces", 0) + stats.get("blocks", 0)
    spam = stats.get("spam_reports", 0)

    if requests_sent:
        bounce_rate = bounces / requests_sent
        spam_rate = spam / requests_sent

        if bounce_rate > BOUNCE_ALERT or spam_rate > SPAM_ALERT:
            return "warning"

    return "operational"


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
    spam = stats.get("spam_reports", 0)

    if requests_sent and bounces / requests_sent > BOUNCE_ALERT:
        notify(
            "warning",
            "SendGrid bounce rate is high",
            f"Bounce/block rate {bounces}/{requests_sent} exceeds {BOUNCE_ALERT:.0%}.",
            source="sendgrid",
        )

    if requests_sent and spam / requests_sent > SPAM_ALERT:
        notify(
            "warning",
            "SendGrid spam complaints detected",
            f"Spam rate {spam}/{requests_sent} exceeds {SPAM_ALERT:.0%}.",
            source="sendgrid",
        )


def _mock():
    stats = {"requests": 540, "delivered": 512, "bounces": 8, "blocks": 2,
             "opens": 320, "mock": True}
    upsert_service("SendGrid", "sendgrid", "operational", stats)
    log_activity("sendgrid", "Delivered 512 emails", {"mock": True})
    return stats
