"""GitHub monitor: commits, repo activity, PRs, failed Actions, security alerts."""
import logging

import base64

import requests
from django.conf import settings

from apps.monitoring.collector import log_activity, upsert_service
from apps.notifications.service import notify

log = logging.getLogger(__name__)
API = "https://api.github.com"


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
    }

    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    return headers


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
    """Return the latest commit from a repository or the authenticated user activity."""
    try:
        if repo:
            r = requests.get(
                f"{API}/repos/{repo}/commits",
                headers=_headers(),
                params={"per_page": 1},
                timeout=15,
            )
            r.raise_for_status()
            commit = r.json()[0]

            return {
                "repo": repo,
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message", "").split("\n")[0],
                "author": commit.get("commit", {}).get("author", {}).get("name"),
                "date": commit.get("commit", {}).get("author", {}).get("date"),
                "url": commit.get("html_url"),
            }

        r = requests.get(
            f"{API}/users/{settings.GITHUB_USER}/events/public",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()

        for event in r.json():
            if event.get("type") == "PushEvent":
                commits = event.get("payload", {}).get("commits", [])
                if commits:
                    commit = commits[-1]
                    return {
                        "repo": event.get("repo", {}).get("name"),
                        "sha": commit.get("sha"),
                        "message": commit.get("message", "").split("\n")[0],
                    }

    except requests.RequestException as e:
        log.warning("Latest commit lookup failed: %s", e, exc_info=True)

    return None


def get_commit_history(repo=None, limit=10):
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
        log.warning("Commit history lookup failed: %s", e, exc_info=True)
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
        log.warning("Repository info lookup failed: %s", e, exc_info=True)
        return None


def get_repository_readme(repo):
    """Return decoded README content for AI summarization."""
    try:
        r = requests.get(
            f"{API}/repos/{repo}/readme",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        content = data.get("content")
        if not content:
            return None

        return base64.b64decode(content).decode("utf-8", errors="ignore")

    except requests.RequestException as e:
        log.warning("README lookup failed for %s: %s", repo, e, exc_info=True)
        return None


def get_repository_languages(repo):
    try:
        r = requests.get(
            f"{API}/repos/{repo}/languages",
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    except requests.RequestException as e:
        log.warning("Language lookup failed: %s", e, exc_info=True)
        return {}


def get_repository_context(repo):
    """Complete repository context for AI analysis."""
    return {
        "repository": get_repository_info(repo),
        "readme": get_repository_readme(repo),
        "languages": get_repository_languages(repo),
        "commits": get_commit_history(repo, limit=10),
        "latest_commit": get_latest_commit(repo),
    }


def create_issue(repo, title, body="Created by AI assistant"):
    if not settings.GITHUB_TOKEN:
        return {"error": "GitHub token missing"}

    try:
        log.info("Creating GitHub issue repo=%s title=%s", repo, title)
        r = requests.post(
            f"{API}/repos/{repo}/issues",
            headers=_headers(),
            json={"title": title, "body": body},
            timeout=15,
        )
        log.info("GitHub issue response status=%s body=%s", r.status_code, r.text)
        r.raise_for_status()
        issue = r.json()

        log_activity(
            "github",
            f"Created issue #{issue.get('number')} in {repo}",
            {"repo": repo, "title": title, "url": issue.get("html_url")},
        )

        return {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "url": issue.get("html_url"),
        }

    except requests.RequestException as e:
        log.warning("Issue creation failed: %s", e)
        return {"error": str(e)}


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
def get_repository_tree(repo, branch="main"):
    try:
        r = requests.get(
            f"{API}/repos/{repo}/git/trees/{branch}",
            headers=_headers(),
            params={"recursive": 1},
            timeout=15,
        )
        r.raise_for_status()
        return [item.get("path") for item in r.json().get("tree", [])]
    except requests.RequestException as e:
        log.warning("Repository tree lookup failed: %s", e)
        return []


def search_repository_code(repo, query):
    try:
        r = requests.get(
            f"{API}/search/code",
            headers=_headers(),
            params={"q": f"{query} repo:{repo}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("items", [])
    except requests.RequestException as e:
        log.warning("Repository search failed: %s", e)
        return []


def get_github_ai_context(repo=None):
    context = get_github_context(repo)

    if repo:
        context["repository"] = get_repository_context(repo)
        context["readme_available"] = bool(context["repository"].get("readme"))
        context["tree"] = get_repository_tree(repo)

    return context