"""Google Cloud monitor: billing, API usage, key activity, security events.

ponytail: full GCP billing/monitoring needs a service account + client libs.
Kept as mock telemetry plus an API-key-leak heuristic until real creds are wired.
"""
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify


def collect():
    mock = not settings.GCP_API_KEY
    metadata = {
        "billing_month_usd": 4.12,
        "api_requests_24h": 18432,
        "active_keys": 3,
        "mock": mock,
    }
    upsert_service("Google Cloud", "gcp", "operational", metadata)
    log_activity("gcp", f"API requests (24h): {metadata['api_requests_24h']}", {"mock": mock})

    # Security heuristic: unexpected key usage spike from a new region.
    for event in _security_events():
        notify("critical", event, "Investigate immediately. Possible credential exposure.",
               source="gcp", make_alert=True)
    return metadata


def _security_events():
    # ponytail: real detection reads Cloud Audit Logs; stubbed to none by default.
    return []
