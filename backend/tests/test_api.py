import asyncio
from tools.api import get_json


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.last_call = None

    async def get(self, url, params=None, headers=None, timeout=None, follow_redirects=False):
        self.last_call = {"url": url, "params": params, "headers": headers, "timeout": timeout, "follow_redirects": follow_redirects}
        return self._response


def test_get_json_returns_parsed_json_on_success():
    client = _FakeClient(_FakeResponse(200, {"ok": True}))
    assert asyncio.run(get_json(client, "https://example.com")) == {"ok": True}


def test_get_json_maps_error_status_to_error_dict():
    client = _FakeClient(_FakeResponse(404))
    result = asyncio.run(get_json(client, "https://example.com", error_map={404: "not found"}))
    assert result == {"error": "not found"}


def test_get_json_raises_on_unmapped_error_status():
    client = _FakeClient(_FakeResponse(500))
    try:
        asyncio.run(get_json(client, "https://example.com"))
        assert False, "expected raise_for_status to raise"
    except RuntimeError:
        pass


def test_get_json_passes_params_headers_timeout_through():
    client = _FakeClient(_FakeResponse(200, []))
    asyncio.run(get_json(client, "https://example.com", params={"q": "x"}, headers={"A": "B"}, timeout=5.0))
    assert client.last_call == {"url": "https://example.com", "params": {"q": "x"}, "headers": {"A": "B"}, "timeout": 5.0, "follow_redirects": True}
