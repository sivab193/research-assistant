from __future__ import annotations

import requests


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}", response=self)


def test_search_uses_semantic_scholar_results(client, monkeypatch, isolated_app):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {"data": [{"paperId": "S1", "title": "Found", "authors": [], "abstract": "A"}]}
        )

    monkeypatch.setattr(isolated_app.requests, "get", fake_get)
    response = client.get("/api/search?q=agents&limit=3")

    assert response.status_code == 200
    assert response.get_json()[0]["external_id"] == "S1"
    assert calls[0][0] == isolated_app.SEMANTIC_SCHOLAR_URL
    assert calls[0][1]["params"]["limit"] == 3


def test_search_falls_back_to_openalex(client, monkeypatch, isolated_app):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == isolated_app.SEMANTIC_SCHOLAR_URL:
            raise requests.Timeout("semantic timeout")
        return FakeResponse({"results": [{"id": "W1", "title": "Fallback", "authorships": []}]})

    monkeypatch.setattr(isolated_app.requests, "get", fake_get)
    response = client.get("/api/search?q=agents")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "abstract": "No abstract available.",
            "authors": [],
            "external_id": "W1",
            "pdf_url": None,
            "source": "OpenAlex",
            "title": "Fallback",
            "url": "W1",
            "year": None,
        }
    ]
    assert calls == [isolated_app.SEMANTIC_SCHOLAR_URL, isolated_app.OPENALEX_URL]


def test_search_rejects_too_short_query_without_network(client, monkeypatch, isolated_app):
    def fail_get(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(isolated_app.requests, "get", fail_get)
    response = client.get("/api/search?q=x")

    assert response.status_code == 400
    assert "two characters" in response.get_json()["error"]


def test_search_returns_502_when_both_providers_fail(client, monkeypatch, isolated_app):
    monkeypatch.setattr(
        isolated_app.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("offline"))
    )

    response = client.get("/api/search?q=agents")

    assert response.status_code == 502
    assert "both providers" in response.get_json()["error"]


def test_search_caps_semantic_scholar_limit_at_twenty(client, monkeypatch, isolated_app):
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse({"data": []})

    monkeypatch.setattr(isolated_app.requests, "get", fake_get)

    response = client.get("/api/search?q=agents&limit=999")

    assert response.status_code == 200
    assert captured["params"]["limit"] == 20


def test_openalex_fallback_caps_limit_and_includes_configured_key(
    client, monkeypatch, isolated_app
):
    calls = []
    monkeypatch.setattr(isolated_app, "OPENALEX_API_KEY", "test-openalex-key")

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == isolated_app.SEMANTIC_SCHOLAR_URL:
            raise requests.Timeout("offline")
        return FakeResponse({"results": []})

    monkeypatch.setattr(isolated_app.requests, "get", fake_get)

    response = client.get("/api/search?q=agents&limit=999")

    assert response.status_code == 200
    assert calls[1][1]["params"] == {
        "search": "agents",
        "per-page": 20,
        "api_key": "test-openalex-key",
    }
