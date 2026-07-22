"""Generic HTTP-GET-as-JSON helper shared by tool modules.

Deliberately GitHub-agnostic: no base URL, headers, or auth live here — those stay in
the calling module (see tools/github.py's _headers()/GITHUB_URL) so a future agent
(e.g. the planned web search agent) can reuse this shape without inheriting GitHub
concerns.
"""
import httpx


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    error_map: dict[int, str] | None = None,
) -> dict | list:
    resp = await client.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    if error_map and resp.status_code in error_map:
        return {"error": error_map[resp.status_code]}
    resp.raise_for_status()
    return resp.json()
