import logging
import re

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.render.com/v1"

COST_THRESHOLD = 5.68

# Render API keys look like "rnd_<alphanumerics>".
RENDER_KEY_RE = re.compile(r"^rnd_[A-Za-z0-9]{16,}$")


def _auth():
    return {"Authorization": f"Bearer {settings.RENDER_API_KEY}", "Accept": "application/json"}


def _check_leak():
    """Alert on a malformed or possibly exposed Render API key."""
    key = settings.RENDER_API_KEY
    if key and not RENDER_KEY_RE.match(key):
        notify(
            "critical",
            "Render API key is malformed or possibly exposed",
            "Rotate the Render API key immediately.",
            source="render",
            make_alert=True,
        )


def collect():
    if not settings.RENDER_API_KEY:
        upsert_service("Render", "render", "unknown", {"error": "Render API key not configured"})
        return {"error": "Render API key not configured"}
    _check_leak()
    try:
        h = _auth()
        r = requests.get(f"{API}/services?limit=20", headers=h, timeout=15)
        r.raise_for_status()
        services = r.json()
        for item in services:
            s = item.get("service", item)
            name = s.get("name", "render-service")
            suspended = s.get("suspended", "not_suspended")
            status = "operational" if suspended == "not_suspended" else "down"
            deploy = _latest_deploy(h, s.get("id"))
            upsert_service(name, "render", status, {
                "id": s.get("id"),
                "service_type": s.get("type"),
                "url": s.get("serviceDetails", {}).get("url") or s.get("dashboardUrl"),
                "branch": s.get("branch"),
                "suspended": suspended,
                "latest_deploy": deploy,
            })
            log_activity("render", f"Service {name} status {status}")
        cost = _fetch_cost(h)
        return _finish(cost)
    except requests.RequestException as e:
        log.warning("Render collect failed: %s", e)
        upsert_service("Render", "render", "unknown", {"error": str(e)})
        return {"error": str(e)}


def _latest_deploy(headers, service_id):
    """Most recent deploy id/status/time for a service, for log lookups."""
    if not service_id:
        return None
    try:
        r = requests.get(f"{API}/services/{service_id}/deploys?limit=1", headers=headers, timeout=15)
        r.raise_for_status()
        items = r.json()
        if not items:
            return None
        d = items[0].get("deploy", items[0])
        return {"id": d.get("id"), "status": d.get("status"), "created_at": d.get("createdAt")}
    except requests.RequestException as e:
        log.warning("Render latest deploy lookup failed: %s", e)
        return None


def get_service_logs(service_id):
    """Logs for a service's most recent deploy. Used by the dashboard on click."""
    if not settings.RENDER_API_KEY:
        return {"error": "Render API key not configured", "logs": []}
    deploy = _latest_deploy(_auth(), service_id)
    if not deploy or not deploy.get("id"):
        return {"error": "No deploys found", "logs": []}
    return {"deploy": deploy, "logs": get_deployment_logs(service_id, deploy["id"])}


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
    return None


def _finish(cost):
    within_budget = cost is None or cost <= COST_THRESHOLD
    status = "operational" if within_budget else "warning"

    metadata = {
        "monthly_cost": cost,
        "expected_monthly_cost": COST_THRESHOLD,
        "within_expected_cost": within_budget,
    }

    if not within_budget:
        metadata["issue"] = f"Render cost exceeded ${COST_THRESHOLD:.2f} limit. Current: ${cost:.2f}"
        notify(
            "warning",
            "Render cost exceeded expected limit",
            metadata["issue"],
            source="render_billing",
            make_alert=True,
        )

    upsert_service(
        "Render Billing",
        "render",
        status,
        metadata,
    )

    return metadata
