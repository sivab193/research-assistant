from __future__ import annotations

from pathlib import Path


def test_save_list_and_delete_paper(client):
    created = client.post(
        "/api/papers",
        json={"title": "A New Paper", "authors": ["A. Author"], "abstract": "Useful."},
    )
    assert created.status_code == 201
    paper = created.get_json()
    assert paper["title"] == "A New Paper"
    assert paper["authors"] == ["A. Author"]

    listing = client.get("/api/papers")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.get_json()] == [paper["id"]]

    deleted = client.delete(f"/api/papers/{paper['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/papers").get_json() == []


def test_save_requires_title(client):
    response = client.post("/api/papers", json={"authors": ["Nobody"]})

    assert response.status_code == 400
    assert response.get_json()["error"] == "A title is required."


def test_duplicate_external_id_is_rejected(client):
    payload = {"external_id": "duplicate:1", "title": "Same paper"}
    assert client.post("/api/papers", json=payload).status_code == 201

    response = client.post("/api/papers", json=payload)

    assert response.status_code == 409
    assert "already" in response.get_json()["error"].lower()


def test_delete_unknown_paper_returns_404(client):
    response = client.delete("/api/papers/99999")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Paper not found."


def test_save_blank_title_and_non_list_authors_are_normalized(client):
    blank = client.post("/api/papers", json={"title": "   "})
    created = client.post("/api/papers", json={"title": "Normalized", "authors": "Ada"})

    assert blank.status_code == 400
    assert blank.get_json() == {"error": "A title is required."}
    assert created.status_code == 201
    assert created.get_json()["authors"] == []
    assert created.get_json()["source"] == "Search"


def test_list_papers_returns_newest_first(client):
    first = client.post("/api/papers", json={"title": "First"}).get_json()
    second = client.post("/api/papers", json={"title": "Second"}).get_json()

    listing = client.get("/api/papers")

    assert listing.status_code == 200
    assert [paper["id"] for paper in listing.get_json()] == [second["id"], first["id"]]


def test_delete_removes_stored_pdf_and_returns_empty_body(client, saved_paper, isolated_app):
    stored_pdf = isolated_app.UPLOAD_DIR / "stored.pdf"
    stored_pdf.parent.mkdir(parents=True, exist_ok=True)
    stored_pdf.write_bytes(b"pdf")
    with isolated_app.get_db() as db:
        db.execute(
            "UPDATE papers SET pdf_path = ? WHERE id = ?",
            (str(stored_pdf), saved_paper["id"]),
        )

    response = client.delete(f"/api/papers/{saved_paper['id']}")

    assert response.status_code == 204
    assert response.data == b""
    assert not Path(stored_pdf).exists()
