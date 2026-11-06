from __future__ import annotations

import pytest
import requests


class FakeResponse:
    def __init__(self, payload=None, *, ok=True, status_code=200, content=b""):
        self.payload = payload or {}
        self.ok = ok
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}", response=self)


def test_index_and_config_routes(client, monkeypatch, isolated_app):
    index = client.get("/")
    assert index.status_code == 200
    assert b"Atlas" in index.data

    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(isolated_app, "OPENROUTER_MODEL", "provider/free")
    assert client.get("/api/config").get_json() == {
        "provider": "openrouter",
        "model": "provider/free",
    }
    # Configuration metadata must not expose an API key.
    assert "key" not in client.get("/api/config").get_json()


def test_health_reports_available_lm_studio(client, monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "lmstudio")
    monkeypatch.setattr(isolated_app.requests, "get", lambda *args, **kwargs: FakeResponse(ok=True))

    assert client.get("/api/health").get_json() == {
        "app": "ok",
        "llm": True,
        "provider": "lmstudio",
        "model": "auto-detect",
    }


def test_health_auto_falls_back_to_configured_openrouter(client, monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(isolated_app.requests, "get", lambda *args, **kwargs: FakeResponse(ok=False))

    result = client.get("/api/health").get_json()

    assert result["llm"] is True
    assert result["provider"] == "openrouter"


def test_health_auto_prefers_available_lm_studio(client, monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(isolated_app.requests, "get", lambda *args, **kwargs: FakeResponse(ok=True))

    assert client.get("/api/health").get_json() == {
        "app": "ok",
        "llm": True,
        "provider": "lmstudio",
        "model": "auto-detect",
    }


@pytest.mark.parametrize(("key", "expected_ok"), [("", False), ("test-key", True)])
def test_health_openrouter_reflects_key_availability(
    key, expected_ok, client, monkeypatch, isolated_app
):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", key)
    monkeypatch.setattr(isolated_app, "OPENROUTER_MODEL", "provider/free")

    assert client.get("/api/health").get_json() == {
        "app": "ok",
        "llm": expected_ok,
        "provider": "openrouter",
        "model": "provider/free",
    }


def test_health_reports_lm_studio_request_failure(client, monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "lmstudio")
    monkeypatch.setattr(
        isolated_app.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("offline")),
    )

    result = client.get("/api/health").get_json()

    assert result["llm"] is False
    assert result["provider"] == "lmstudio"


def test_lm_studio_chat_auto_detects_model_and_returns_content(monkeypatch, isolated_app):
    calls = []
    monkeypatch.setattr(isolated_app, "LM_STUDIO_MODEL", "")
    monkeypatch.setattr(
        isolated_app.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"data": [{"id": "local-model"}]}),
    )

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"choices": [{"message": {"content": "  local answer  "}}]})

    monkeypatch.setattr(isolated_app.requests, "post", fake_post)

    answer = isolated_app.lm_studio_chat([{"role": "user", "content": "Hi"}], 0.2)

    assert answer == "local answer"
    assert calls[0][1]["json"]["model"] == "local-model"
    assert calls[0][1]["json"]["temperature"] == 0.2


def test_lm_studio_chat_reports_unreachable_server(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LM_STUDIO_MODEL", "fixed")
    monkeypatch.setattr(
        isolated_app.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("offline")),
    )

    with pytest.raises(RuntimeError, match="Could not reach LM Studio"):
        isolated_app.lm_studio_chat([], 0.1)


def test_lm_studio_chat_rejects_empty_model_list(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LM_STUDIO_MODEL", "")
    monkeypatch.setattr(
        isolated_app.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"data": []}),
    )

    with pytest.raises(RuntimeError, match="no chat model is loaded"):
        isolated_app.lm_studio_chat([], 0.1)


def test_lm_studio_chat_rejects_malformed_response(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LM_STUDIO_MODEL", "fixed")
    monkeypatch.setattr(isolated_app.requests, "post", lambda *args, **kwargs: FakeResponse({"choices": []}))

    with pytest.raises(RuntimeError, match="unexpected response"):
        isolated_app.lm_studio_chat([], 0.1)


def test_openrouter_requires_key(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is missing"):
        isolated_app.openrouter_chat([], 0.1)


def test_openrouter_sends_bearer_key_and_returns_content(monkeypatch, isolated_app):
    captured = {}
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "secret-for-test")

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse({"choices": [{"message": {"content": "cloud answer"}}]})

    monkeypatch.setattr(isolated_app.requests, "post", fake_post)

    assert isolated_app.openrouter_chat([], 0.3) == "cloud answer"
    assert captured["headers"]["Authorization"] == "Bearer secret-for-test"
    assert captured["json"]["model"] == isolated_app.OPENROUTER_MODEL


def test_openrouter_reports_provider_error_detail(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        isolated_app.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {"error": {"message": "quota exhausted"}}, status_code=429
        ),
    )

    with pytest.raises(RuntimeError, match=r"OpenRouter request failed\. quota exhausted"):
        isolated_app.openrouter_chat([], 0.1)


def test_openrouter_rejects_malformed_success_response(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        isolated_app.requests,
        "post",
        lambda *args, **kwargs: FakeResponse({"choices": []}),
    )

    with pytest.raises(RuntimeError, match="unexpected response"):
        isolated_app.openrouter_chat([], 0.1)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("lmstudio", "local"), ("openrouter", "cloud")],
)
def test_lm_chat_dispatches_to_selected_provider(provider, expected, monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", provider)
    monkeypatch.setattr(isolated_app, "lm_studio_chat", lambda messages, temperature: "local")
    monkeypatch.setattr(isolated_app, "openrouter_chat", lambda messages, temperature: "cloud")

    assert isolated_app.lm_chat([]) == expected


def test_lm_chat_auto_falls_back_to_openrouter(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        isolated_app,
        "lm_studio_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(isolated_app, "openrouter_chat", lambda messages, temperature: "fallback")

    assert isolated_app.lm_chat([]) == "fallback"


def test_lm_chat_auto_returns_lm_studio_success_without_cloud(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(isolated_app, "lm_studio_chat", lambda *args, **kwargs: "local")
    monkeypatch.setattr(
        isolated_app,
        "openrouter_chat",
        lambda *args, **kwargs: pytest.fail("cloud fallback must not run"),
    )

    assert isolated_app.lm_chat([]) == "local"


def test_lm_chat_auto_reraises_local_failure_without_cloud_key(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(isolated_app, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(
        isolated_app,
        "lm_studio_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("local offline")),
    )

    with pytest.raises(RuntimeError, match="local offline"):
        isolated_app.lm_chat([])


def test_lm_chat_rejects_unknown_provider(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "LLM_PROVIDER", "unknown")

    with pytest.raises(RuntimeError, match="LLM_PROVIDER must be"):
        isolated_app.lm_chat([])


def test_analysis_routes_translate_llm_failures_to_503(
    client, saved_paper, monkeypatch, isolated_app
):
    monkeypatch.setattr(
        isolated_app,
        "lm_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider offline")),
    )

    summary = client.post(f"/api/papers/{saved_paper['id']}/summarize")
    answer = client.post(
        f"/api/papers/{saved_paper['id']}/ask", json={"question": "What happened?"}
    )

    assert summary.status_code == 503
    assert summary.get_json()["error"] == "provider offline"
    assert answer.status_code == 503
    assert answer.get_json()["error"] == "provider offline"
