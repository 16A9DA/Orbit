"""GitHub monitor: commits, repo activity, PRs, failed Actions, security alerts."""
import logging

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def collect():
    if not (settings.GITHUB_TOKEN and settings.GITHUB_USER):
        return _mock()
    try:
        r = requests.get(
            f"{API}/users/{settings.GITHUB_USER}/events/public",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        events = r.json()[:20]
        commits = prs = failed = 0
        for ev in events:
            repo = ev.get("repo", {}).get("name", "?")
            t = ev.get("type", "")
            if t == "PushEvent":
                n = len(ev.get("payload", {}).get("commits", []))
                commits += n
                log_activity("github", f"Pushed {n} commit(s) to {repo}")
            elif t == "PullRequestEvent":
                prs += 1
                log_activity("github", f"PR {ev['payload'].get('action')} on {repo}")
            elif t == "WorkflowRunEvent":
                if ev.get("payload", {}).get("workflow_run", {}).get("conclusion") == "failure":
                    failed += 1
                    notify("critical", f"Failed GitHub Action on {repo}",
                           "A workflow run concluded with failure.", source="github")
        upsert_service("GitHub", "github", "operational",
                       {"commits": commits, "prs": prs, "failed_actions": failed})
        return {"commits": commits, "prs": prs, "failed_actions": failed}
    except requests.RequestException as e:
        log.warning("GitHub collect failed: %s", e)
        upsert_service("GitHub", "github", "unknown", {"error": str(e)})
        return {"error": str(e)}


def _mock():
    upsert_service("GitHub", "github", "operational",
                   {"commits": 12, "prs": 2, "failed_actions": 0, "mock": True})
    log_activity("github", "Pushed 3 commit(s) to ryn/dashboard", {"mock": True})
    log_activity("github", "PR opened on ryn/dashboard", {"mock": True})
    return {"commits": 12, "prs": 2, "failed_actions": 0, "mock": True}
