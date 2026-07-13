import logging
import re
import json

import requests
from django.conf import settings
from django.utils import timezone

from apps.monitoring.models import Activity, Alert, Service, Task
from apps.notifications.service import send_discord_message
from apps.github.service import get_github_ai_context
from apps.assistant.tools import execute_tool, TOOL_DESCRIPTION

log = logging.getLogger(__name__)


def snapshot():
    services = list(Service.objects.all())
    alerts = list(Alert.objects.filter(resolved=False))
    tasks = list(Task.objects.exclude(status="done"))
    activity = list(Activity.objects.all()[:15])
    return services, alerts, tasks, activity


def ask(question):
    services, alerts, tasks, activity = snapshot()

    action_result = _handle_actions(question)
    if action_result:
        return action_result

    repo_url = _extract_repo_url(question)
    answer = _ask_ollama(question, services, alerts, tasks, activity, repo_url)
    if answer:
        return answer
    return _rule_based(question, services, alerts, tasks)


def _handle_actions(question):
    q = question.lower()

    discord_keywords = (
        "send to discord",
        "send on discord",
        "post to discord",
        "message discord",
    )

    if any(keyword in q for keyword in discord_keywords):
        message = question

        success = send_discord_message(
            message,
            channel="general",
        )

        if success:
            return "Message sent to Discord general channel."

        return "I could not send the Discord message. Check the Discord webhook configuration."

    return None


def _extract_repo_url(question):
    match = re.search(r"https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+", question)
    return match.group(0).rstrip("/.") if match else None


def _ask_ollama(question, services, alerts, tasks, activity, repo_url=None):
    github_context = None
    repo_name = None

    if repo_url:
        match = re.search(r"github\.com/([\w.-]+/[\w.-]+)", repo_url)
        if match:
            repo_name = match.group(1).rstrip("/")

    github_context = get_github_ai_context(repo_name)

    context = {
        "services": [f"{s.name} ({s.type}): {s.status}" for s in services],
        "alerts": [f"[{a.severity}] {a.title}" for a in alerts],
        "tasks": [f"[{t.priority}] {t.title}" for t in tasks],
        "activity": [
            {
                "service": a.service,
                "event": a.event,
                "metadata": getattr(a, "metadata", {}),
                "created": str(a.created_at) if hasattr(a, "created_at") else None,
            }
            for a in activity
        ],
        "repository_url": repo_url,
        "github": github_context,
        "capabilities": [
            "service monitoring",
            "GitHub activity analysis",
            "latest commit tracking",
            "commit history analysis",
            "repository summaries",
            "repository structure analysis",
            "repository code search",
            "infrastructure questions",
            "external service information",
            "notifications and integrations when configured",
            "GitHub actions through available tools",
        ],
    }
    system = (
        "You are the assistant inside a local infrastructure dashboard. "
        "Answer questions about the application, connected services, integrations, and monitored infrastructure. "
        "You can answer questions about GitHub repositories, commits, pull requests, failures, deployments, repository structure, README content, languages, and code search results. "
        "If a GitHub repository URL is provided, summarize the repository using available repository context and clearly state when information is missing. "
        "You can help explain external services such as hosting providers, billing plans, APIs, and configuration options when the information is available in the system state. "
        "For requests that require an action, use available tools when possible. "
        "When calling a tool, return only JSON in this format: {\"tool\": \"tool_name\", \"arguments\": {}}. Use GitHub tools for GitHub actions instead of explaining that you cannot access GitHub. "
        "Available tools:\n" + TOOL_DESCRIPTION + "\n"
        "Do not invent data, pricing, plans, or actions that have not been provided. If information is unavailable, say so clearly. No preamble."
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
        response = r.json().get("message", {}).get("content", "").strip()

        try:
            tool_request = json.loads(response)
            if tool_request.get("tool"):
                result = execute_tool(
                    tool_request["tool"],
                    tool_request.get("arguments", {}),
                )
                return f"Tool execution result:\n{result}"
        except (ValueError, TypeError):
            pass

        return response
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
