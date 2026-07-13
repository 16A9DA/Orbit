import logging

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.render.com/v1"


def collect():
    if not settings.RENDER_API_KEY:
        return _finish(_mock_cost(), mock=True)
    try:
        h = {"Authorization": f"Bearer {settings.RENDER_API_KEY}", "Accept": "application/json"}
        r = requests.get(f"{API}/services?limit=20", headers=h, timeout=15)
        r.raise_for_status()
        services = r.json()
        for item in services:
            s = item.get("service", item)
            name = s.get("name", "render-service")
            suspended = s.get("suspended", "not_suspended")
            status = "operational" if suspended == "not_suspended" else "down"
            upsert_service(name, "render", status, {"id": s.get("id")})
            log_activity("render", f"Service {name} status {status}")
        cost = _fetch_cost(h)
        return _finish(cost)
    except requests.RequestException as e:
        log.warning("Render collect failed: %s", e)
        upsert_service("Render", "render", "unknown", {"error": str(e)})
        return {"error": str(e)}


def get_deployment_logs(service_id, deploy_id):
    """Get logs for a Render deployment."""
    if not settings.RENDER_API_KEY:
        return []

    headers = {
        "Authorization": f"Bearer {settings.RENDER_API_KEY}",
        "Accept": "application/json",
    }

    try:
        r = requests.get(
            f"{API}/services/{service_id}/deploys/{deploy_id}/logs",
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("logs", data if isinstance(data, list) else [])
    except requests.RequestException as e:
        log.warning("Render deployment logs lookup failed: %s", e)
        return []


def get_deployment_details(service_id, deploy_id):
    if not settings.RENDER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {settings.RENDER_API_KEY}",
        "Accept": "application/json",
    }

    try:
        r = requests.get(
            f"{API}/services/{service_id}/deploys/{deploy_id}",
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.warning("Render deployment details lookup failed: %s", e)
        return None

def _fetch_cost(headers):
    try:
        r = requests.get(f"{API}/billing", headers=headers, timeout=15)
        if r.ok:
            return float(r.json().get("currentMonthCost", 0))
    except requests.RequestException:
        pass
    return _mock_cost()


def _mock_cost():
    return 1.85


def _finish(cost, mock=False):
    expected_limit = 5.68
    within_budget = cost <= expected_limit
    status = "operational" if within_budget else "warning"

    metadata = {
        "monthly_cost": cost,
        "expected_monthly_cost": expected_limit,
        "within_expected_cost": within_budget,
        "mock": mock,
    }

    if not within_budget:
        metadata["issue"] = f"Render cost exceeded expected $5.00 limit. Current: ${cost:.2f}"
        notify(
            "warning",
            "Render cost exceeded expected limit",
            metadata["issue"],
            source="render_billing",
        )

    upsert_service(
        "Render Billing",
        "render",
        status,
        metadata,
    )

    return metadata
