"""Local git collector: surface the user's own commits in Recent Activity.

GitHub's public events miss local-only commits, private repos, and a wrong
GITHUB_USER. Reading the local repo covers all of those.
"""
import logging
import subprocess

from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.monitoring.models import Activity

log = logging.getLogger(__name__)


def _recent_commits(limit=10):
    root = str(settings.PROJECT_ROOT)
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", f"-{int(limit)}", "--pretty=format:%h\x1f%s\x1f%an\x1f%cr"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("Local git log failed: %s", e)
        return []
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "subject": parts[1], "author": parts[2], "when": parts[3]})
    return commits


def collect():
    commits = _recent_commits()
    if not commits:
        upsert_service("Local Git", "git", "unknown", {"error": "No local git history"})
        return {"error": "No local git history"}

    new = 0
    for c in commits:
        event = f"{c['hash']} {c['subject']}"
        # Dedupe on the commit hash so re-polling does not spam Activity.
        if Activity.objects.filter(service="git", event=event).exists():
            continue
        log_activity("git", event, {"hash": c["hash"], "author": c["author"], "when": c["when"]})
        new += 1

    latest = commits[0]
    upsert_service("Local Git", "git", "operational", {
        "latest_commit": f"{latest['hash']} {latest['subject']}",
        "author": latest["author"],
        "when": latest["when"],
        "new_commits": new,
    })
    return {"latest": latest, "new_commits": new}
