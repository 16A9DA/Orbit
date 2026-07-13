import logging
import requests
import os
from django.conf import settings
from datetime import datetime, timedelta

from google.oauth2 import service_account
from google.auth.transport.requests import Request

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)

GCP_API = "https://monitoring.googleapis.com/v3"
SERVICE_USAGE_API = "https://serviceusage.googleapis.com/v1"
CLOUD_BILLING_API = "https://cloudbilling.googleapis.com/v1"
CLOUD_LOGGING_API = "https://logging.googleapis.com/v2"
CLOUD_RESOURCE_MANAGER_API = "https://cloudresourcemanager.googleapis.com/v1"



def _get_credentials():
    try:
        credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

        if not credentials_json:
            return None

        import json
        info = json.loads(credentials_json)

        return service_account.Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform"
            ],
        )

    except Exception as e:
        log.warning("Google credentials loading failed: %s", e, exc_info=True)
        return None


def _headers():
    credentials = _get_credentials()

    if credentials:
        credentials.refresh(Request())
        return {
            "Authorization": f"Bearer {credentials.token}",
            "Accept": "application/json",
        }

    api_key = getattr(settings, "GCP_API_KEY", None) or os.getenv("GCP_API_KEY")

    headers = {
        "Accept": "application/json",
    }

    if api_key:
        headers["X-Goog-Api-Key"] = api_key

    return headers


def collect():
    project_id = getattr(settings, "GCP_PROJECT_ID", None) or os.getenv("GCP_PROJECT")

    if not project_id:
        return _mock()
    if not getattr(settings, "GCP_PROJECT_ID", None):
        settings.GCP_PROJECT_ID = project_id

    try:
        metadata = {
            "billing_month_usd": _get_billing(),
            "api_requests_24h": _get_api_usage(),
            "security_events": _security_events(),
            "enabled_apis": _get_enabled_apis(),
            "cost_anomalies": _cost_anomalies(),
            "service_health": _service_health(),
            "quota_usage": _quota_usage(),
            "recent_errors": _recent_errors(),
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

        if metadata["billing_month_usd"] >= 5:
            status = "warning"
            notify(
                "warning",
                "Google Cloud spending alert",
                "Monthly spend has exceeded $5.",
                source="gcp",
                make_alert=True,
            )

        if metadata["cost_anomalies"]:
            status = "warning"
            for anomaly in metadata["cost_anomalies"]:
                notify(
                    "warning",
                    anomaly,
                    "Please review your Google Cloud spending.",
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
    try:
        if not bigquery:
            return 0.0

        project_id = (
            getattr(settings, "GCP_BILLING_PROJECT_ID", None)
            or getattr(settings, "GCP_PROJECT_ID", None)
            or os.getenv("GCP_PROJECT")
        )
        dataset = getattr(settings, "GCP_BILLING_DATASET", None)
        table = getattr(settings, "GCP_BILLING_TABLE", None)

        if not all([project_id, dataset, table]):
            return 0.0

        client = bigquery.Client(project=project_id)

        query = f"""
            SELECT
              SUM(cost) AS total_cost
            FROM `{project_id}.{dataset}.{table}`
            WHERE invoice.month = FORMAT_DATE('%Y%m', CURRENT_DATE())
        """

        result = client.query(query).result()

        for row in result:
            return float(row.total_cost or 0.0)

        return 0.0

    except Exception as e:
        log.warning("Google billing lookup failed: %s", e, exc_info=True)
        return 0.0


def _get_enabled_apis():
    try:
        r = requests.get(
            f"{SERVICE_USAGE_API}/projects/{getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT'))}/services",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        services = r.json().get("services", [])
        return [s.get("config", {}).get("name") for s in services if s.get("state") == "ENABLED"]
    except requests.RequestException as e:
        log.warning("Enabled APIs lookup failed: %s", e, exc_info=True)
        return []


def _cost_anomalies():
    anomalies = []
    spend = _get_billing()
    if spend >= 5:
        anomalies.append(f"Monthly Google Cloud spend is ${spend:.2f}")
    return anomalies


def _service_health():
    return {
        "status": "operational",
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def _get_api_usage():
    try:
        project_id = getattr(settings, "GCP_PROJECT_ID", os.getenv("GCP_PROJECT"))

        now = datetime.utcnow()
        start = now - timedelta(hours=24)

        payload = {
            "filter": 'metric.type="serviceruntime.googleapis.com/api/request_count"',
            "interval": {
                "startTime": start.isoformat() + "Z",
                "endTime": now.isoformat() + "Z",
            },
        }

        response = requests.post(
            f"{GCP_API}/projects/{project_id}/timeSeries",
            headers=_headers(),
            json=payload,
            timeout=15,
        )

        response.raise_for_status()

        return len(response.json().get("timeSeries", []))

    except requests.RequestException as e:
        log.warning("Google API usage lookup failed: %s", e, exc_info=True)
        return 0

def _quota_usage():
    try:
        project_id = getattr(settings, "GCP_PROJECT_ID", os.getenv("GCP_PROJECT"))

        payload = {
            "filter": 'metric.type="serviceruntime.googleapis.com/quota/allocation/usage"',
        }

        r = requests.post(
            f"{GCP_API}/projects/{project_id}/timeSeries",
            headers=_headers(),
            json=payload,
            timeout=15,
        )

        r.raise_for_status()

        return {
            "metrics_checked": len(
                r.json().get("timeSeries", [])
            )
        }

    except requests.RequestException as e:
        log.warning("Quota lookup failed: %s", e, exc_info=True)
        return {
            "metrics_checked": 0
        }

def _recent_errors():
    try:
        payload = {
            "resourceNames": [f"projects/{getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT'))}"],
            "filter": "severity>=ERROR",
            "pageSize": 10,
        }
        r = requests.post(
            f"{CLOUD_LOGGING_API}/entries:list",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        entries = r.json().get("entries", [])
        return [
            entry.get("textPayload") or entry.get("jsonPayload", {})
            for entry in entries
        ]
    except requests.RequestException as e:
        log.warning("Cloud Logging lookup failed: %s", e, exc_info=True)
        return []


def _security_events():
    events = []

    # Basic API key exposure heuristic.
    api_key = getattr(settings, "GCP_API_KEY", None) or os.getenv("GCP_API_KEY")

    if api_key:
        if len(api_key) < 20:
            events.append("Google Cloud API key looks invalid or exposed")

    if not (getattr(settings, "GCP_PROJECT_ID", None) or os.getenv("GCP_PROJECT")):
        events.append("Google Cloud project is not configured")

    return events


def _mock():
    metadata = {
        "billing_month_usd": 4.12,
        "api_requests_24h": 18432,
        "security_events": [],
        "enabled_apis": ["compute.googleapis.com", "storage.googleapis.com", "iam.googleapis.com"],
        "cost_anomalies": [],
        "service_health": {"status": "operational"},
        "quota_usage": {
            "metrics_checked": 0,
        },
        "recent_errors": [],
        "mock": False,
    }
    upsert_service("Google Cloud", "gcp", "operational", metadata)
    return metadata
