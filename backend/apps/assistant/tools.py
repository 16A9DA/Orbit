
import re


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


GITHUB_TOOLS = {
    "create_issue": create_issue,
    "create_branch": create_branch,
    "comment_issue": comment_issue,
    "get_latest_commit": get_latest_commit,
    "get_repository_context": get_repository_context,
    "get_github_ai_context": get_github_ai_context,
    "search_repository_code": search_repository_code,
    "get_repository_tree": get_repository_tree,
}


TOOL_DESCRIPTION = """
Available GitHub tools:

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