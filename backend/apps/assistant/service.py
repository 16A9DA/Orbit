import logging
import re
import json

import requests
from django.conf import settings
from django.utils import timezone

from apps.monitoring.models import Activity, Alert, Service, Task
from apps.notifications.service import send_discord_message
from apps.github.service import get_github_ai_context
from apps.google_cloud.service import collect as get_google_cloud_context
from apps.assistant.tools import execute_tool, TOOL_DESCRIPTION

log = logging.getLogger(__name__)


def _extract_json(text):
    """Pull the first balanced {...} object out of a model reply and parse it.

    The 3B model often wraps its tool-call JSON in prose; a bare json.loads on
    the whole string then fails. Scanning for the first balanced object recovers
    the tool call regardless of surrounding text.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


def _demo_extract_json():
    assert _extract_json('{"tool": "x", "arguments": {}}')["tool"] == "x"
    assert _extract_json('Sure! {"tool": "web_search"} done')["tool"] == "web_search"
    assert _extract_json('no json here') is None
    assert _extract_json('') is None


def snapshot():
    services = list(Service.objects.all())
    alerts = list(Alert.objects.filter(resolved=False))
    tasks = list(Task.objects.exclude(status="done"))
    activity = list(Activity.objects.all()[:15])
    return services, alerts, tasks, activity


def ask(question, history=None):
    services, alerts, tasks, activity = snapshot()

    action_result = _handle_actions(question)
    if action_result:
        return action_result

    repo_url = _extract_repo_url(question)
    forced = _route_tool(question, repo_url)
    answer = _ask_ollama(question, services, alerts, tasks, activity, repo_url,
                         history=history, forced=forced)
    if answer:
        return answer
    return _rule_based(question, services, alerts, tasks)


def _route_tool(question, repo_url):
    """Deterministic tool pick for cases the small model routes unreliably.

    Returns {"tool": name, "arguments": {...}} to force, or None to let the
    model decide.
    """
    q = question.lower()
    git_kw = ("what changes", "what did i", "my changes", "uncommitted",
              "recent commits", "local git", "what have i done", "edited locally")
    if any(k in q for k in git_kw):
        return {"tool": "get_local_git_changes", "arguments": {}}
    web_kw = ("how do i", "how to", "how can i", "latest", "documentation",
              "docs for", "set up", "setup", "install", "what is the best",
              "compare", "pricing for", "news", "better than", "alternative",
              "alternatives to", " vs ", "cheaper", "recommend", "which service",
              "free ", "is there a", "what's a good", "should i use")
    # Only reach for the web when the question isn't about a specific repo.
    if not repo_url and any(k in q for k in web_kw):
        return {"tool": "web_answer", "arguments": {"query": question}}
    return None


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


def _ask_ollama(question, services, alerts, tasks, activity, repo_url=None,
                history=None, forced=None):
    github_context = None
    repo_name = None

    if repo_url:
        match = re.search(r"github\.com/([\w.-]+/[\w.-]+)", repo_url)
        if match:
            repo_name = match.group(1).rstrip("/")

    github_context = get_github_ai_context(repo_name)
    google_cloud_context = get_google_cloud_context()

    context = {
        "services": [f"{s.name} ({s.type}): {s.status}" for s in services],
        "service_details": [
            {"name": s.name, "type": s.type, "status": s.status,
             "metadata": getattr(s, "metadata", {})}
            for s in services
        ],
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
        "github_user": settings.GITHUB_USER,
        "github": github_context,
        "google_cloud": google_cloud_context,
        "capabilities": [
            "service monitoring",
            "GitHub activity analysis",
            "latest commit tracking",
            "commit history analysis",
            "repository summaries",
            "repository structure analysis",
            "repository code search",
            "infrastructure questions",
            "Google Cloud billing monitoring",
            "Google Cloud per-service cost breakdown",
            "Google Cloud running instance counts and inventory",
            "Google Cloud public-IP exposure detection",
            "Render deployed apps, deploy logs, and billing monitoring",
            "SendGrid email delivery, bounce, spam, and credit monitoring",
            "API key leak detection across services",
            "overcharge and cost-overage alerting",
            "local git changes and commit history (get_local_git_changes)",
            "sending messages to Discord channels (send_discord)",
            "web search and page reading (web_search, web_fetch)",
            "local git push status: unpushed and recently pushed commits",
            "Google Cloud API usage monitoring",
            "Google Cloud enabled API monitoring",
            "Google Cloud cost anomaly detection",
            "Google Cloud service health monitoring",
            "Google Cloud error monitoring",
            "external service information",
            "notifications and integrations when configured",
            "GitHub actions through available tools",
        ],
    }
    system = (
        "You are Orbit, the user's day-to-day developer and work assistant, living inside their infrastructure dashboard. "
        "You help like a senior engineer: monitor their services, answer deployment and setup questions, and look things up on the internet when needed. You currently monitor their infrastructure and will connect to more tools (such as email) over time. Refer to yourself as Orbit. "
        "Answer questions about the application, connected services, integrations, and monitored infrastructure. "
        "You can answer questions about GitHub repositories, commits, pull requests, failures, deployments, repository structure, README content, languages, and code search results. You can also analyze Google Cloud billing, enabled APIs, usage, service health, cost anomalies, quotas, and recent errors from the connected Google Cloud context. "
        "If a GitHub repository URL is provided, summarize the repository using available repository context and clearly state when information is missing. "
        "The user's own GitHub username is provided as github_user in the system state. When the user names a repository without a URL (for example 'Orbit'), treat it as their own repo and call the tool with just the repository name; do not ask for a URL. Only expect a URL when the repository clearly belongs to someone else. "
        "You can help explain external services such as hosting providers, billing plans, APIs, and configuration options when the information is available in the system state. "
        "For requests that require an action or infrastructure check, use available tools when possible. Use get_google_cloud_context for Google Cloud monitoring questions. Use get_local_git_changes for questions about the user's own local code changes, edits, or recent commits in this project. Use send_discord when the user asks to notify, post, or send a message to Discord. Use web_search and web_fetch when the user needs current or external information from the internet that is not in the system state. "
        "When calling a tool, return only JSON in this format: {\"tool\": \"tool_name\", \"arguments\": {}}. Use GitHub tools for GitHub actions instead of explaining that you cannot access GitHub. "
        "Available tools:\n" + TOOL_DESCRIPTION + "\n"
        "Do not invent data, pricing, plans, or actions that have not been provided. If information is unavailable, say so clearly. No preamble."
    )
    prompt = f"System state:\n{context}\n\nUser: {question}"
    # Prior turns give the model follow-up context ("summarize it", "that repo").
    prior = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-6:]
    try:
        if forced and forced.get("tool"):
            # Skip the routing model call; force the chosen tool directly.
            response = json.dumps(forced)
        else:
            r = requests.post(
                f"{settings.OLLAMA_HOST}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        *prior,
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )
            r.raise_for_status()
            response = r.json().get("message", {}).get("content", "").strip()

        try:
            tool_request = _extract_json(response) or {}
            if tool_request.get("tool"):
                arguments = tool_request.get("arguments") or {}

                # Recover repository argument if the model omitted it.
                if "repo" not in arguments:
                    if repo_name:
                        arguments["repo"] = repo_name
                    elif repo_url:
                        match = re.search(r"github\.com/([\w.-]+/[\w.-]+)", repo_url)
                        if match:
                            arguments["repo"] = match.group(1).rstrip("/")

                result = execute_tool(
                    tool_request["tool"],
                    arguments,
                )

                summary_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are Orbit. A tool has already run and its result is given below. "
                            "Answer the user's request using ONLY that result, in a concise, helpful reply. "
                            "Ground every factual claim in the provided sources. Do not invent facts, "
                            "numbers, or features not present in the result. If the sources disagree or "
                            "do not confirm something, say so plainly instead of guessing. "
                            "When the result contains web sources, cite the source URLs you used at the "
                            "end under a 'Sources:' line so the user can verify. "
                            "Do not mention tools, JSON, or internal implementation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"{question}\n\nTool result:\n{json.dumps(result, indent=2, default=str)}",
                    },
                ]

                try:
                    summary_response = requests.post(
                        f"{settings.OLLAMA_HOST}/api/chat",
                        json={
                            "model": settings.OLLAMA_MODEL,
                            "stream": False,
                            "messages": summary_messages,
                        },
                        timeout=60,
                    )
                    summary_response.raise_for_status()
                    summarized = summary_response.json().get("message", {}).get("content", "").strip()
                except requests.RequestException:
                    summarized = ""
                # Empty summary or Ollama failure: fall back to the raw tool result
                # so web/git lookups always surface something.
                answer = summarized or _format_tool_result(result)
                return _append_sources(answer, result)
        except (ValueError, TypeError):
            pass

        return response
    except requests.RequestException as e:
        log.warning("Ollama assistant unavailable, using rule-based: %s", e)
        return None


def _append_sources(answer, result):
    """Guarantee verifiable source links on web answers, even if the model omits them."""
    if not isinstance(result, dict):
        return answer
    urls = [s.get("url") for s in result.get("sources", []) if s.get("url")]
    if not urls or "Sources:" in answer:
        return answer
    return answer + "\n\nSources:\n" + "\n".join(f"- {u}" for u in urls)


def _format_tool_result(result):
    """Readable fallback rendering of a tool result when no model can summarize."""
    if isinstance(result, dict) and result.get("sources"):
        lines = ["From the web:"]
        for s in result["sources"]:
            lines.append(f"- {s.get('title')} ({s.get('url')})\n  {(s.get('text') or '')[:300]}")
        return "\n".join(lines)
    if isinstance(result, dict) and result.get("results"):
        lines = ["Top results:"]
        for r in result["results"][:5]:
            lines.append(f"- {r.get('title')}: {r.get('snippet') or ''}\n  {r.get('url')}")
        return "\n".join(lines)
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    return str(result)


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
