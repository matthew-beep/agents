import httpx
import os
import base64
from tools.api import get_json

GITHUB_URL = "https://api.github.com"

def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

async def search_repos(client: httpx.AsyncClient, query: str, sort: str = "stars") -> list:
    data = await get_json(
        client,
        f"{GITHUB_URL}/search/repositories",
        params={"q": query, "sort": sort, "per_page": 10},
        headers=_headers(),
        timeout=30.0,
        error_map={422: f"Invalid search query: {query}. Use simple keywords only, e.g. 'local LLM agent tool use language:python'"},
    )
    if "error" in data:
        return data
    items = data.get("items", [])
    return [
        {
            "full_name": r["full_name"],
            "description": r["description"],
            "stars": r["stargazers_count"],
            "language": r["language"],
            "topics": r["topics"],
            "url": r["html_url"],
        }
        for r in items
    ]

async def get_repo(client: httpx.AsyncClient, owner: str, repo: str) -> dict:
    return await get_json(
        client,
        f"{GITHUB_URL}/repos/{owner}/{repo}",
        headers=_headers(),
        timeout=120.0,
        error_map={404: f"Repository {owner}/{repo} not found"},
    )

def _build_tree(paths: list[str]) -> dict:
    tree = {}
    for path in paths:
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    return tree

async def get_repo_tree(client: httpx.AsyncClient, owner: str, repo: str, branch: str | None = None) -> dict:
    if branch is None:
        repo_data = await get_repo(client, owner, repo)
        if "error" in repo_data:
            return repo_data
        branch = repo_data.get("default_branch", "main")
    data = await get_json(
        client,
        f"{GITHUB_URL}/repos/{owner}/{repo}/git/trees/{branch}",
        params={"recursive": 1},
        headers=_headers(),
        timeout=120.0,
        error_map={404: f"Branch '{branch}' not found for {owner}/{repo}."},
    )
    if "error" in data:
        return data
    paths = [entry["path"] for entry in data.get("tree", []) if entry["type"] == "blob"]

    print(f"repo tree: {_build_tree(paths)}")
    return {
        "truncated": data.get("truncated", False),
        "tree": _build_tree(paths),
    }

async def get_file(client: httpx.AsyncClient, owner: str, repo: str, path: str) -> str:
    data = await get_json(
        client,
        f"{GITHUB_URL}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(),
        timeout=30.0,
        error_map={404: f"{path} not found in {owner}/{repo}"},
    )
    if "error" in data:
        return data
    return base64.b64decode(data["content"]).decode("utf-8")

async def list_issues(client: httpx.AsyncClient, owner: str, repo: str, state: str = "open") -> list:
    data = await get_json(
        client,
        f"{GITHUB_URL}/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": 10},
        headers=_headers(),
        timeout=30.0,
        error_map={404: f"Repository {owner}/{repo} not found"},
    )
    if isinstance(data, dict) and "error" in data:
        return data
    return [
        {"number": i["number"], "title": i["title"], "state": i["state"],
         "comments": i["comments"], "labels": [l["name"] for l in i["labels"]]}
        for i in data if "pull_request" not in i
    ]

async def search_code(client: httpx.AsyncClient, query: str, owner: str | None = None, repo: str | None = None) -> list:
    q = query
    if owner and repo:
        q = f"{query} repo:{owner}/{repo}"
    elif owner:
        q = f"{query} user:{owner}"
    data = await get_json(
        client,
        f"{GITHUB_URL}/search/code",
        params={"q": q, "per_page": 10},
        headers=_headers(),
        timeout=30.0,
        error_map={
            401: "GitHub code search requires authentication. Set GITHUB_TOKEN to use this tool.",
            403: "GitHub code search rate limit exceeded. Try again later or narrow the query.",
            422: f"Invalid code search query: {q}. Code search needs qualifiers beyond bare keywords — try 'in:file', 'language:', 'path:', or 'extension:', and scope with owner/repo if possible.",
        },
    )
    if isinstance(data, dict) and "error" in data:
        return data
    items = data.get("items", [])
    return [
        {"path": item["path"], "repo": item["repository"]["full_name"],
         "url": item["html_url"], "score": item.get("score")}
        for item in items
    ]

SYSTEM_PROMPT = """You are a GitHub assistant. Be concise and direct.

You have access to tools that can fetch real data from GitHub.
If you can answer from your own knowledge, do so. Only call a tool when you actually need live data.

When reporting tool results, always use the exact data returned — never infer, summarize, or invent file paths or structure. If the tree is truncated, say so."""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_repo",
            "description": "Get metadata for a GitHub repository, including default_branch, description, stars, and language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_repos",
            "description": "Search GitHub for repositories. Use simple keywords only, e.g. 'local LLM agent tool use'. Optionally append 'language:python' or 'stars:>100'. Do not use complex syntax.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "sort": {"type": "string", "enum": ["stars", "forks", "updated"], "description": "Sort order"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_tree",
            "description": "Get all file paths in a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "branch": {"type": "string", "description": "Branch name (defaults to the repo's default branch)"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file",
            "description": "Get the raw contents of a file in a GitHub repository. Use path='README.md' to get the README.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "path": {"type": "string", "description": "File path within the repository"},
                },
                "required": ["owner", "repo", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for code across GitHub. Requires GITHUB_TOKEN to be configured — if this errors, relay the error to the user rather than retrying. Needs more specific queries than search_repos: combine keywords with qualifiers, e.g. 'in:file', 'language:python', 'path:src/', or 'extension:py' — bare keyword-only queries are often rejected. Pass owner (and optionally repo) to scope the search instead of searching all of GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code search query, e.g. 'def parse_args in:file language:python'"},
                    "owner": {"type": "string", "description": "Optional: scope search to this user or organization"},
                    "repo": {"type": "string", "description": "Optional: scope search to this repository (requires owner)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_issues",
            "description": "List open or closed issues in a GitHub repository. Pull requests are excluded from results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Issue state filter"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
]

TOOL_MAP = {
    "search_repos": search_repos,
    "get_repo": get_repo,
    "get_repo_tree": get_repo_tree,
    "get_file": get_file,
    "search_code": search_code,
    "list_issues": list_issues,
}
