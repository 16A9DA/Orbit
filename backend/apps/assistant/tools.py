import re
import subprocess

from django.conf import settings

from apps.github.service import (
    create_issue,
    create_branch,
    comment_issue,
    get_latest_commit,
    get_repository_context,
    get_github_ai_context,
    search_repository_code,
    get_repository_tree,
)
from apps.google_cloud.service import collect as get_google_cloud_context
from apps.notifications.service import send_discord_message

_DISCORD_CHANNELS = {"general", "alerts", "billing", "security", "deployments"}


def send_discord(message, channel="general"):
    if not message:
        return {"error": "message is required"}
    channel = channel if channel in _DISCORD_CHANNELS else "general"
    ok = send_discord_message(message, channel)
    if ok:
        return {"status": "sent", "channel": channel}
    return {"error": f"Discord webhook for channel '{channel}' is not configured or send failed"}


def get_local_git_changes(limit=15):
    root = str(settings.PROJECT_ROOT)

    def _git(*args):
        try:
            return subprocess.run(
                ["git", "-C", root, *args],
                capture_output=True, text=True, timeout=15,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError) as e:
            return f"error: {e}"

    has_upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_ok = has_upstream and not has_upstream.startswith("error")

    return {
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "upstream": has_upstream if upstream_ok else "no upstream configured",
        "status": _git("status", "--short") or "clean",
        "diff_stat": _git("diff", "--stat"),
        "staged_diff_stat": _git("diff", "--cached", "--stat"),
        "recent_commits": _git("log", f"-{int(limit)}", "--oneline"),
        # Commits made locally but not yet pushed to the upstream branch.
        "unpushed_commits": (_git("log", "--oneline", "@{u}..HEAD") or "none") if upstream_ok else "no upstream",
        # Most recent commits already on the upstream (i.e. pushed).
        "recently_pushed": (_git("log", "--oneline", "-10", "@{u}") or "none") if upstream_ok else "no upstream",
    }


def web_search(query, max_results=5):
    """Search the web with DuckDuckGo and return top result snippets."""
    if not query:
        return {"error": "query is required"}
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=int(max_results)))
        return {"results": [
            {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
            for r in results
        ]}
    except Exception as e:
        return {"error": f"Web search failed: {e}"}


def web_fetch(url, max_chars=4000):
    """Fetch a URL and return its readable text via BeautifulSoup."""
    if not url or not url.startswith(("http://", "https://")):
        return {"error": "a valid http(s) url is required"}
    try:
        import requests as _rq
        from bs4 import BeautifulSoup
        r = _rq.get(url, timeout=15, headers={"User-Agent": "OrbitAssistant/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return {"url": url, "text": text[:int(max_chars)]}
    except Exception as e:
        return {"error": f"Fetch failed: {e}"}


GITHUB_TOOLS = {
    "create_issue": create_issue,
    "create_branch": create_branch,
    "comment_issue": comment_issue,
    "get_latest_commit": get_latest_commit,
    "get_repository_context": get_repository_context,
    "get_github_ai_context": get_github_ai_context,
    "search_repository_code": search_repository_code,
    "get_repository_tree": get_repository_tree,
    "get_google_cloud_context": get_google_cloud_context,
    "get_local_git_changes": get_local_git_changes,
    "send_discord": send_discord,
    "web_search": web_search,
    "web_fetch": web_fetch,
}


TOOL_DESCRIPTION = """
Available GitHub tools:

get_google_cloud_context:
Check Google Cloud infrastructure health.
Returns billing status, API usage, enabled APIs, cost anomalies, service health, quotas, and recent errors.
Arguments:
{}

get_local_git_changes:
Get the local git state of this dashboard project: the user's own uncommitted changes and recent commit history.
Use for questions like "what changes have I done", "what did I edit locally", "recent commits".
Returns current branch, working-tree status, diff stats, and recent commit log.
Arguments:
{}

send_discord:
Send a message to a Discord channel when the user asks to notify, post, or send something to Discord.
Valid channels: general, alerts, billing, security, deployments (defaults to general).
Arguments:
{
    "message": "text to send",
    "channel": "general"
}

web_search:
Search the web for current or external information not present in the system state.
Use for news, docs, pricing, or anything requiring live internet data.
Arguments:
{
    "query": "search terms"
}

web_fetch:
Fetch and read the text of a specific web page URL.
Use after web_search to read a result, or when the user gives a URL to read.
Arguments:
{
    "url": "https://example.com"
}

get_repository_context:
Analyze a GitHub repository.
Required arguments:
{
    "repo": "owner/repository"
}
Returns repository metadata, README, languages, and commits.

get_github_ai_context:
Get complete AI context for a repository.
Required arguments:
{
    "repo": "owner/repository"
}
Returns repository details, README, tree structure, and commits.

get_latest_commit:
Get latest commit.
Arguments:
{
    "repo": "owner/repository"
}

search_repository_code:
Search files inside a repository.
Arguments:
{
    "repo": "owner/repository",
    "query": "search term"
}

get_repository_tree:
Get repository file structure.
Arguments:
{
    "repo": "owner/repository",
    "branch": "main"
}

create_issue:
Create a GitHub issue.
Arguments:
{
    "repo": "owner/repository",
    "title": "issue title",
    "body": "issue description"
}

create_branch:
Create a branch.
Arguments:
{
    "repo": "owner/repository",
    "branch": "new branch name",
    "from_branch": "main"
}

comment_issue:
Comment on an issue.
Arguments:
{
    "repo": "owner/repository",
    "issue_number": 1,
    "comment": "message"
}
"""



def normalize_tool_arguments(name, arguments):
    """Normalize and validate arguments before executing tools."""
    arguments = arguments or {}

    if "repo" in arguments and isinstance(arguments["repo"], str):
        arguments["repo"] = re.sub(
            r"^https?://github\\.com/",
            "",
            arguments["repo"],
        ).rstrip("/")

        # A bare repo name (no owner) means one of the user's own repositories.
        repo = arguments["repo"]
        if repo and "/" not in repo and settings.GITHUB_USER:
            arguments["repo"] = f"{settings.GITHUB_USER}/{repo}"

    required_repo_tools = {
        "get_repository_context",
        "get_github_ai_context",
        "get_latest_commit",
        "search_repository_code",
        "get_repository_tree",
        "create_issue",
        "create_branch",
        "comment_issue",
    }

    if name in required_repo_tools and not arguments.get("repo"):
        return {
            "error": "Missing required repo argument. Expected owner/repository format."
        }

    return arguments


def execute_tool(name, arguments):
    tool = GITHUB_TOOLS.get(name)

    if not tool:
        return {
            "error": f"Unknown tool: {name}"
        }

    arguments = normalize_tool_arguments(name, arguments)

    if "error" in arguments:
        return arguments

    try:
        return tool(**arguments)
    except TypeError as e:
        return {
            "error": f"Invalid arguments for {name}: {str(e)}"
        }