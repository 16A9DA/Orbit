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
        cost = _fetch_cost()
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


def get_recent_deploys(service_id, limit=5):
    """Recent deploys with commit info for a service."""
    try:
        r = requests.get(f"{API}/services/{service_id}/deploys?limit={int(limit)}", headers=_auth(), timeout=15)
        r.raise_for_status()
        out = []
        for item in r.json():
            d = item.get("deploy", item)
            commit = d.get("commit") or {}
            out.append({
                "status": d.get("status"),
                "created_at": d.get("createdAt"),
                "commit_message": (commit.get("message") or "").split("\n")[0],
                "commit_id": (commit.get("id") or "")[:7],
            })
        return out
    except requests.RequestException as e:
        log.warning("Render deploys lookup failed: %s", e)
        return []


def _owner_id(headers):
    try:
        r = requests.get(f"{API}/owners?limit=1", headers=headers, timeout=15)
        r.raise_for_status()
        items = r.json()
        if items:
            return items[0].get("owner", items[0]).get("id")
    except requests.RequestException as e:
        log.warning("Render owner lookup failed: %s", e)
    return None


def get_service_logs(service_id):
    """Recent runtime logs for a service via the /v1/logs endpoint (dashboard on-click)."""
    if not settings.RENDER_API_KEY:
        return {"error": "Render API key not configured", "logs": []}

    deploys = get_recent_deploys(service_id)

    headers = _auth()
    owner = _owner_id(headers)
    if not owner:
        return {"error": "Could not resolve Render owner", "logs": [], "deploys": deploys}

    try:
        r = requests.get(
            f"{API}/logs",
            headers=headers,
            params={"ownerId": owner, "resource": service_id, "limit": 50, "direction": "backward"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        entries = data.get("logs", data if isinstance(data, list) else [])
        logs = [
            f"{e.get('timestamp', '')} {e.get('message', '')}".strip() if isinstance(e, dict) else str(e)
            for e in entries
        ]
        return {"logs": logs, "deploys": deploys}
    except requests.RequestException as e:
        log.warning("Render logs lookup failed: %s", e)
        return {"error": f"Logs unavailable: {e}", "logs": [], "deploys": deploys}


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

def _fetch_cost():
    # Render's public API has no billing endpoint, so the only reliable source
    # of real spend is the RENDER_MONTHLY_COST override. Otherwise unavailable.
    override = getattr(settings, "RENDER_MONTHLY_COST", "")
    if override not in (None, ""):
        try:
            return float(override)
        except (TypeError, ValueError):
            log.warning("Invalid RENDER_MONTHLY_COST: %r", override)
    return None


def _resolve_stale_billing_alerts():
    """Clear old render cost/billing alerts once spend is back within budget.

    Covers both the current 'render_billing' source and legacy 'render'-source
    cost alerts (older builds), matched by title so genuine leak alerts survive.
    """
    try:
        from django.db.models import Q
        from apps.monitoring.models import Alert
        (Alert.objects
         .filter(resolved=False)
         .filter(Q(source="render_billing") | Q(source="render", title__icontains="cost")
                 | Q(source="render", title__icontains="usage exceeded"))
         .update(resolved=True))
    except Exception as e:
        log.warning("Could not resolve stale render alerts: %s", e)


def _finish(cost):
    within_budget = cost is None or cost <= COST_THRESHOLD
    status = "operational" if within_budget else "warning"

    metadata = {
        "monthly_cost": cost,
        "expected_monthly_cost": COST_THRESHOLD,
        "within_expected_cost": within_budget,
    }

    if within_budget:
        _resolve_stale_billing_alerts()
    else:
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
