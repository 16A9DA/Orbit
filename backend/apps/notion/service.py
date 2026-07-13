"""Notion sync: pinned pages plus tasks (due date, priority, status)."""
import logging

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.monitoring.collector import log_activity, upsert_service
from apps.monitoring.models import Task

log = logging.getLogger(__name__)
API = "https://api.notion.com/v1"

PRIORITY_MAP = {"High": "high", "Medium": "medium", "Low": "low"}
STATUS_MAP = {"Done": "done", "In Progress": "in_progress", "In progress": "in_progress"}


def collect():
    if not (settings.NOTION_TOKEN and settings.NOTION_TASKS_DB):
        return _mock()
    try:
        h = {
            "Authorization": f"Bearer {settings.NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        r = requests.post(f"{API}/databases/{settings.NOTION_TASKS_DB}/query",
                          headers=h, json={"page_size": 50}, timeout=20)
        r.raise_for_status()
        count = 0
        for page in r.json().get("results", []):
            if _sync_task(page):
                count += 1
        upsert_service("Notion", "notion", "operational", {"tasks_synced": count})
        log_activity("notion", f"Synced {count} task(s)")
        return {"tasks_synced": count}
    except requests.RequestException as e:
        log.warning("Notion collect failed: %s", e)
        upsert_service("Notion", "notion", "unknown", {"error": str(e)})
        return {"error": str(e)}


def _prop(props, name, default=None):
    return props.get(name, {}) if name in props else (default or {})


def _sync_task(page):
    props = page.get("properties", {})
    title = _plain_title(props)
    if not title:
        return False
    priority = _select(props, "Priority")
    status = _select(props, "Status")
    due = _date(props, "Due")
    Task.objects.update_or_create(
        source="notion",
        external_id=page.get("id", ""),
        defaults={
            "title": title,
            "priority": PRIORITY_MAP.get(priority, "medium"),
            "status": STATUS_MAP.get(status, "todo"),
            "deadline": parse_datetime(due) if due else None,
        },
    )
    return True


def _plain_title(props):
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    return ""


def _select(props, name):
    p = props.get(name, {})
    sel = p.get("select") or p.get("status")
    return sel.get("name") if sel else None


def _date(props, name):
    p = props.get(name, {}).get("date")
    return p.get("start") if p else None


def _mock():
    demo = [
        ("Ship dashboard v1", "high", "in_progress"),
        ("Write API docs", "medium", "todo"),
        ("Review security alerts", "high", "todo"),
    ]
    for i, (title, prio, st) in enumerate(demo):
        Task.objects.update_or_create(
            source="notion", external_id=f"mock-{i}",
            defaults={"title": title, "priority": prio, "status": st},
        )
    upsert_service("Notion", "notion", "operational",
                   {"tasks_synced": len(demo), "pinned_pages": ["Projects", "Documentation", "Notes"],
                    "mock": True})
    log_activity("notion", f"Synced {len(demo)} task(s)", {"mock": True})
    return {"tasks_synced": len(demo), "mock": True}
