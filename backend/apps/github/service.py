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
                commit_list = ev.get("payload", {}).get("commits", [])
                n = len(commit_list)
                commits += n

                messages = [
                    c.get("message", "").split("\n")[0]
                    for c in commit_list
                ]

                log_activity(
                    "github",
                    f"Pushed {n} commit(s) to {repo}",
                    {
                        "repo": repo,
                        "commits": messages,
                    },
                )
            elif t == "PullRequestEvent":
                prs += 1
                pr = ev.get("payload", {}).get("pull_request", {})
                log_activity(
                    "github",
                    f"PR {ev['payload'].get('action')} on {repo}",
                    {
                        "repo": repo,
                        "title": pr.get("title"),
                        "url": pr.get("html_url"),
                    },
                )
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


def get_latest_commit(repo=None):

    if not settings.GITHUB_TOKEN:
        return None

    try:
        if repo:
            url = f"{API}/repos/{repo}/commits"
            r = requests.get(
                url,
                headers=_headers(),
                timeout=15,
            )
            r.raise_for_status()

            commit = r.json()[0]

            return {
                "repo": repo,
                "message": commit["commit"]["message"],
                "author": commit["commit"]["author"]["name"],
                "date": commit["commit"]["author"]["date"],
                "url": commit["html_url"],
            }

        # fallback: user's latest push
        r = requests.get(
            f"{API}/users/{settings.GITHUB_USER}/events/public",
            headers=_headers(),
            timeout=15,
        )

        r.raise_for_status()

        for event in r.json():
            if event.get("type") == "PushEvent":
                commits = event["payload"].get("commits", [])

                if commits:
                    return {
                        "repo": event["repo"]["name"],
                        "message": commits[-1]["message"],
                        "sha": commits[-1]["sha"],
                    }

    except requests.RequestException as e:
        log.warning("Latest commit lookup failed: %s", e)

    return None


def get_commit_history(repo=None, limit=10):
    if not settings.GITHUB_TOKEN:
        return []

    try:
        if not repo:
            latest = get_latest_commit()
            if not latest:
                return []
            repo = latest.get("repo")

        r = requests.get(
            f"{API}/repos/{repo}/commits",
            headers=_headers(),
            params={"per_page": limit},
            timeout=15,
        )
        r.raise_for_status()

        commits = []
        for commit in r.json():
            commits.append({
                "repo": repo,
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message", "").split("\n")[0],
                "author": commit.get("commit", {}).get("author", {}).get("name"),
                "date": commit.get("commit", {}).get("author", {}).get("date"),
                "url": commit.get("html_url"),
            })

        return commits

    except requests.RequestException as e:
        log.warning("Commit history lookup failed: %s", e)
        return []


def get_github_context(repo=None):
    """Provide structured GitHub context for the local AI model."""
    latest = get_latest_commit(repo)
    history = get_commit_history(repo)

    return {
        "latest_commit": latest,
        "recent_commits": history,
    }


def get_repository_info(repo):
    if not settings.GITHUB_TOKEN:
        return None

    try:
        r = requests.get(
            f"{API}/repos/{repo}",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        return {
            "name": data.get("full_name"),
            "description": data.get("description"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "language": data.get("language"),
            "default_branch": data.get("default_branch"),
            "created": data.get("created_at"),
            "updated": data.get("updated_at"),
            "url": data.get("html_url"),
        }

    except requests.RequestException as e:
        log.warning("Repository info lookup failed: %s", e)
        return None


def get_repository_readme(repo):
    if not settings.GITHUB_TOKEN:
        return None

    try:
        r = requests.get(
            f"{API}/repos/{repo}/readme",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        import base64
        content = data.get("content", "")

        return base64.b64decode(content).decode("utf-8", errors="ignore")

    except requests.RequestException as e:
        log.warning("README lookup failed: %s", e)
        return None


def get_repository_languages(repo):
    if not settings.GITHUB_TOKEN:
        return {}

    try:
        r = requests.get(
            f"{API}/repos/{repo}/languages",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    except requests.RequestException as e:
        log.warning("Language lookup failed: %s", e)
        return {}


def get_repository_context(repo):
    return {
        "repository": get_repository_info(repo),
        "readme": get_repository_readme(repo),
        "languages": get_repository_languages(repo),
        "commits": get_commit_history(repo, limit=5),
    }


def create_issue(repo, title, body):
    """Create a GitHub issue from an AI action."""
    if not settings.GITHUB_TOKEN:
        return None

    try:
        r = requests.post(
            f"{API}/repos/{repo}/issues",
            headers=_headers(),
            json={
                "title": title,
                "body": body,
            },
            timeout=15,
        )
        r.raise_for_status()
        issue = r.json()

        log_activity(
            "github",
            f"Created issue #{issue.get('number')} in {repo}",
            {
                "repo": repo,
                "title": title,
                "url": issue.get("html_url"),
            },
        )

        return {
            "number": issue.get("number"),
            "url": issue.get("html_url"),
            "title": issue.get("title"),
        }

    except requests.RequestException as e:
        log.warning("Issue creation failed: %s", e)
        return None


def create_branch(repo, branch, from_branch="main"):
    if not settings.GITHUB_TOKEN:
        return None

    try:
        ref = requests.get(
            f"{API}/repos/{repo}/git/ref/heads/{from_branch}",
            headers=_headers(),
            timeout=15,
        )
        ref.raise_for_status()

        sha = ref.json()["object"]["sha"]

        r = requests.post(
            f"{API}/repos/{repo}/git/refs",
            headers=_headers(),
            json={
                "ref": f"refs/heads/{branch}",
                "sha": sha,
            },
            timeout=15,
        )
        r.raise_for_status()

        return {
            "branch": branch,
            "sha": sha,
        }

    except requests.RequestException as e:
        log.warning("Branch creation failed: %s", e)
        return None


def comment_issue(repo, issue_number, comment):
    if not settings.GITHUB_TOKEN:
        return None

    try:
        r = requests.post(
            f"{API}/repos/{repo}/issues/{issue_number}/comments",
            headers=_headers(),
            json={"body": comment},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        return {
            "url": data.get("html_url"),
        }

    except requests.RequestException as e:
        log.warning("Issue comment failed: %s", e)
        return None