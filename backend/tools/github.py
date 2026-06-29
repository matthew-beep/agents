import httpx
import os
import base64

GITHUB_URL = "https://api.github.com"

def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

async def search_repos(query: str, sort: str = "stars") -> list:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GITHUB_URL}/search/repositories",
            params={"q": query, "sort": sort, "per_page": 10},
            headers=_headers(),
        )
        if resp.status_code == 422:
            return {"error": f"Invalid search query: {query}. Use simple keywords only, e.g. 'local LLM agent tool use language:python'"}
        resp.raise_for_status()
        items = resp.json().get("items", [])
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

async def get_repo(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(f"{GITHUB_URL}/repos/{owner}/{repo}", headers=_headers())
        if resp.status_code == 404:
            return {"error": f"Repository {owner}/{repo} not found"}
        resp.raise_for_status()
        return resp.json()

def _build_tree(paths: list[str]) -> dict:
    tree = {}
    for path in paths:
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    return tree

async def get_repo_tree(owner: str, repo: str, branch: str = "main") -> dict:
    repo_data = await get_repo(owner, repo)
    branch = repo_data.get("default_branch", "main")
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(f"{GITHUB_URL}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1", headers=_headers())
        if resp.status_code == 404:
            return {"error": f"Branch '{branch}' not found for {owner}/{repo}."}
        resp.raise_for_status()
        data = resp.json()
        paths = [entry["path"] for entry in data.get("tree", []) if entry["type"] == "blob"]

        print(f"repo tree: {_build_tree(paths)}")
        return {
            "truncated": data.get("truncated", False),
            "tree": _build_tree(paths),
        }

async def get_file(owner: str, repo: str, path: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GITHUB_URL}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
        )
        if resp.status_code == 404:
            return {"error": f"{path} not found in {owner}/{repo}"}
        resp.raise_for_status()
        return base64.b64decode(resp.json()["content"]).decode("utf-8")


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
                    "branch": {"type": "string", "description": "Branch name (default: main)"},
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
]

TOOL_MAP = {
    "search_repos": search_repos,
    "get_repo": get_repo,
    "get_repo_tree": get_repo_tree,
    "get_file": get_file,
}
