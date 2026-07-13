"""AI assistant. Local-only via Ollama. Falls back to rule-based if Ollama down.

Analyzes services, alerts, tasks, activity. Model picked from installed Ollama
models (default llama3.2:3b, override with OLLAMA_MODEL).
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
    answer = _ask_ollama(question, services, alerts, tasks, activity)
    if answer:
        return answer
    return _rule_based(question, services, alerts, tasks)


def _ask_ollama(question, services, alerts, tasks, activity):
    context = {
        "services": [f"{s.name} ({s.type}): {s.status}" for s in services],
        "alerts": [f"[{a.severity}] {a.title}" for a in alerts],
        "tasks": [f"[{t.priority}] {t.title}" for t in tasks],
        "activity": [f"{a.service}: {a.event}" for a in activity],
    }
    system = (
        "You are the assistant inside a local infrastructure dashboard. "
        "Answer briefly and concretely using only the given system state. "
        "No preamble."
    )
    prompt = f"System state:\n{context}\n\nUser: {question}"
    try:
        r = requests.post(
            f"{settings.OLLAMA_HOST}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()
    except requests.RequestException as e:
        log.warning("Ollama assistant unavailable, using rule-based: %s", e)
        return None


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
            lines.append(f"{len(crit)} critical: " + "; ".join(a.title for a in crit))
        if warn:
            lines.append(f"{len(warn)} warning: " + "; ".join(a.title for a in warn))
        if down:
            lines.append("Degraded/down: " + ", ".join(s.name for s in down))
        return "\n".join(lines)

    if any(k in q for k in ("work on", "today", "task", "todo", "priority")):
        if not tasks:
            return "No open tasks. Inbox zero."
        ordered = sorted(tasks, key=lambda t: (t.priority != "high", t.deadline or timezone.now()))
        return "Suggested focus today:\n" + "\n".join(
            f"- [{t.priority}] {t.title}" + (f" (due {t.deadline:%b %d})" if t.deadline else "")
            for t in ordered[:5]
        )

    return (
        f"Systems: {len(services)} tracked, {len(down)} degraded/down. "
        f"Alerts: {len(crit)} critical, {len(warn)} warning. Open tasks: {len(tasks)}."
    )
