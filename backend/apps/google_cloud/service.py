import logging
import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)

GCP_API = "https://monitoring.googleapis.com/v3"
SERVICE_USAGE_API = "https://serviceusage.googleapis.com/v1"


def _headers():
    return {
        "Authorization": f"Bearer {settings.GCP_API_KEY}",
        "Accept": "application/json",
    }


def collect():
    if not settings.GCP_API_KEY:
        return _mock()

    try:
        metadata = {
            "billing_month_usd": _get_billing(),
            "api_requests_24h": _get_api_usage(),
            "security_events": _security_events(),
            "mock": False,
        }

        status = "operational"

        if metadata["security_events"]:
            status = "warning"
            for event in metadata["security_events"]:
                notify(
                    "critical",
                    event,
                    "Investigate immediately. Possible credential exposure.",
                    source="gcp",
                    make_alert=True,
                )

        upsert_service("Google Cloud", "gcp", status, metadata)
        log_activity(
            "gcp",
            f"API requests (24h): {metadata['api_requests_24h']}",
            metadata,
        )

        return metadata

    except requests.RequestException as e:
        log.warning("Google Cloud collect failed: %s", e)
        upsert_service("Google Cloud", "gcp", "unknown", {"error": str(e)})
        return {"error": str(e)}


def _get_billing():
    # Replace with Cloud Billing API call once billing account endpoint is configured.
    return 0


def _get_api_usage():
    response = requests.get(
        f"{GCP_API}/projects/{settings.GCP_PROJECT_ID}/timeSeries",
        headers=_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return len(response.json().get("timeSeries", []))


def _security_events():
    events = []

    # Basic API key exposure heuristic.
    if hasattr(settings, "GCP_API_KEY") and settings.GCP_API_KEY:
        if len(settings.GCP_API_KEY) < 20:
            events.append("Google Cloud API key looks invalid or exposed")

    return events


def _mock():
    metadata = {
        "billing_month_usd": 4.12,
        "api_requests_24h": 18432,
        "security_events": [],
        "mock": True,
    }
    upsert_service("Google Cloud", "gcp", "operational", metadata)
    return metadata
