"""AI assistant. Analyzes services, alerts, tasks, activity.

Rule-based by default. If ANTHROPIC_API_KEY is set, defers to Claude with the
same context snapshot for a natural-language answer.
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

from apps.monitoring.models import Activity, Alert, Service, Task

log = logging.getLogger(__name__)


def snapshot():
    services = list(Service.objects.all())
    alerts = list(Alert.objects.filter(resolved=False))
    tasks = list(Task.objects.exclude(status="done"))
    activity = list(Activity.objects.all()[:15])
    return services, alerts, tasks, activity


def ask(question):
    services, alerts, tasks, activity = snapshot()
    if settings.ANTHROPIC_API_KEY:
        answer = _ask_claude(question, services, alerts, tasks, activity)
        if answer:
            return answer
    return _rule_based(question, services, alerts, tasks)


def _rule_based(question, services, alerts, tasks):
    q = question.lower()
    down = [s for s in services if s.status in ("down", "degraded")]
    crit = [a for a in alerts if a.severity == "critical"]
    warn = [a for a in alerts if a.severity == "warning"]

    if any(k in q for k in ("problem", "issue", "wrong", "broken")):
        if not alerts and not down:
            return "No open problems. All monitored services report operational."
        lines = []
        if crit:
            lines.append(f"{len(crit)} critical alert(s): " + "; ".join(a.title for a in crit))
        if warn:
            lines.append(f"{len(warn)} warning(s): " + "; ".join(a.title for a in warn))
        if down:
            lines.append("Degraded/down: " + ", ".join(f"{s.name}" for s in down))
        return "\n".join(lines)

    if any(k in q for k in ("work on", "today", "task", "todo", "priority")):
        if not tasks:
            return "No open tasks. Inbox zero."
        ordered = sorted(tasks, key=lambda t: (t.priority != "high", t.deadline or timezone.now()))
        top = ordered[:5]
        return "Suggested focus today:\n" + "\n".join(
            f"- [{t.priority}] {t.title}" + (f" (due {t.deadline:%b %d})" if t.deadline else "")
            for t in top
        )

    # Default: overall system check.
    return (
        f"Systems: {len(services)} tracked, {len(down)} degraded/down. "
        f"Alerts: {len(crit)} critical, {len(warn)} warning. "
        f"Open tasks: {len(tasks)}."
    )


def _ask_claude(question, services, alerts, tasks, activity):
    context = {
        "services": [f"{s.name} ({s.type}): {s.status}" for s in services],
        "alerts": [f"[{a.severity}] {a.title}" for a in alerts],
        "tasks": [f"[{t.priority}] {t.title}" for t in tasks],
        "activity": [f"{a.service}: {a.event}" for a in activity],
    }
    prompt = (
        "You are the assistant inside a local infrastructure dashboard. "
        "Answer concisely using only this state:\n"
        f"{context}\n\nUser: {question}"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    except requests.RequestException as e:
        log.warning("Claude assistant failed, falling back: %s", e)
        return None
