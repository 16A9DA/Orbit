

from apps.github.service import (
    create_issue,
    create_branch,
    comment_issue,
    get_latest_commit,
    get_repository_context,
)


GITHUB_TOOLS = {
    "create_issue": create_issue,
    "create_branch": create_branch,
    "comment_issue": comment_issue,
    "get_latest_commit": get_latest_commit,
    "get_repository_context": get_repository_context,
}


TOOL_DESCRIPTION = """
Available GitHub actions:

create_issue:
Create a GitHub issue.
Arguments:
{
    repo: string,
    title: string,
    body: string
}

create_branch:
Create a new branch.
Arguments:
{
    repo: string,
    branch: string,
    from_branch: string
}

comment_issue:
Add a comment to a GitHub issue.
Arguments:
{
    repo: string,
    issue_number: integer,
    comment: string
}

get_latest_commit:
Return the latest commit information.

get_repository_context:
Return repository metadata, README, languages, and recent commits.
"""


def execute_tool(name, arguments):
    tool = GITHUB_TOOLS.get(name)

    if not tool:
        return {
            "error": f"Unknown tool: {name}"
        }

    return tool(**arguments)