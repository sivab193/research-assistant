from __future__ import annotations


def test_summarize_uses_abstract_and_mocked_llm(client, saved_paper, monkeypatch, isolated_app):
    captured = {}

    def fake_chat(messages, temperature=0.15):
        captured["messages"] = messages
        return "Grounded summary"

    monkeypatch.setattr(isolated_app, "lm_chat", fake_chat)
    response = client.post(f"/api/papers/{saved_paper['id']}/summarize")

    assert response.status_code == 200
    assert response.get_json() == {
        "answer": "Grounded summary",
        "basis": "abstract (full text was unavailable)",
    }
    assert "Reliable Agent Testing" in captured["messages"][1]["content"]


def test_ask_requires_question_before_paper_lookup(client):
    response = client.post("/api/papers/99999/ask", json={"question": "  "})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Enter a question."


def test_ask_unknown_paper_returns_404(client):
    response = client.post("/api/papers/99999/ask", json={"question": "What changed?"})

    assert response.status_code == 404
    assert response.get_json() == {"error": "Paper not found."}


def test_ask_uses_mocked_llm(client, saved_paper, monkeypatch, isolated_app):
    captured = {}

    def fake_chat(messages, temperature=0.15):
        captured["messages"] = messages
        return "Supported answer"

    monkeypatch.setattr(isolated_app, "lm_chat", fake_chat)

    response = client.post(
        f"/api/papers/{saved_paper['id']}/ask", json={"question": "What was studied?"}
    )

    assert response.status_code == 200
    assert response.get_json()["answer"] == "Supported answer"
    assert response.get_json()["basis"] == "abstract (full text was unavailable)"
    prompt = captured["messages"][1]["content"]
    assert "Reliable Agent Testing" in prompt
    assert "What was studied?" in prompt
    assert "A controlled study of reliable software tests." in prompt


def test_summarize_unknown_paper_returns_404(client):
    response = client.post("/api/papers/99999/summarize")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Paper not found."}


def test_analysis_routes_report_paper_without_usable_text(client):
    paper = client.post("/api/papers", json={"title": "Metadata only"}).get_json()

    summary = client.post(f"/api/papers/{paper['id']}/summarize")
    answer = client.post(
        f"/api/papers/{paper['id']}/ask", json={"question": "What was found?"}
    )

    expected = {"error": "This paper has no usable text. Upload its PDF to analyze it."}
    assert summary.status_code == 503
    assert summary.get_json() == expected
    assert answer.status_code == 503
    assert answer.get_json() == expected
