from __future__ import annotations

import os
from pathlib import Path

import pytest


# The submitted HW1 target is the Flask application in app.py.
# app.py initializes its database at import time. Redirect that initialization to
# a disposable directory before importing the application module.
_IMPORT_DATA_DIR = Path(__file__).resolve().parents[1] / ".pytest_cache" / "atlas-import-data"
os.environ["RESEARCH_ASSISTANT_DATA_DIR"] = str(_IMPORT_DATA_DIR)

import app as atlas  # noqa: E402


@pytest.fixture(autouse=True)
def block_unexpected_network(monkeypatch: pytest.MonkeyPatch):
    """Fail fast if a test reaches requests without installing an explicit mock."""

    def deny_network(*args, **kwargs):
        raise AssertionError("Unexpected live network call; mock requests.get/post in this test")

    monkeypatch.setattr(atlas.requests.sessions.Session, "request", deny_network)


@pytest.fixture
def isolated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(atlas, "DATA_DIR", data_dir)
    monkeypatch.setattr(atlas, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(atlas, "DB_PATH", data_dir / "papers.db")
    atlas.app.config.update(TESTING=True)
    atlas.init_db()
    return atlas


@pytest.fixture
def client(isolated_app):
    return isolated_app.app.test_client()


@pytest.fixture
def saved_paper(client):
    response = client.post(
        "/api/papers",
        json={
            "external_id": "paper:fixture",
            "title": "Reliable Agent Testing",
            "authors": ["Ada Tester", "Lin Check"],
            "year": 2026,
            "abstract": "A controlled study of reliable software tests.",
            "source": "Test fixture",
        },
    )
    assert response.status_code == 201
    return response.get_json()
