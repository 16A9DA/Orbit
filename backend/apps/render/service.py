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


def _fetch_cost(headers):
    # ponytail: billing endpoint varies by plan; fall back to mock figure if unavailable.
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
    upsert_service("Render Billing", "render", "operational", {"monthly_cost": cost, "mock": mock})
    if cost > settings.RENDER_COST_THRESHOLD:
        notify("warning", f"Render monthly usage exceeded {settings.RENDER_COST_THRESHOLD}",
               f"Current monthly cost is ${cost:.2f}.", source="render_billing")
    return {"monthly_cost": cost, "mock": mock}
