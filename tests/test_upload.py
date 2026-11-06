from __future__ import annotations

import io

from reportlab.pdfgen import canvas


def test_upload_requires_file(client):
    response = client.post("/api/upload", data={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Choose a PDF file."


def test_upload_rejects_non_pdf(client):
    response = client.post(
        "/api/upload",
        data={"pdf": (io.BytesIO(b"plain text"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Only PDF files are accepted."


def test_upload_saves_extracted_metadata(client, monkeypatch, isolated_app):
    monkeypatch.setattr(
        isolated_app,
        "extract_pdf",
        lambda path: (
            {"title": "Uploaded Study", "authors": ["U. Author"], "year": 2026, "abstract": "A."},
            "Complete uploaded paper text.",
        ),
    )

    response = client.post(
        "/api/upload",
        data={"pdf": (io.BytesIO(b"%PDF-1.4 fake but extraction is isolated"), "study.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    paper = response.get_json()
    assert paper["title"] == "Uploaded Study"
    assert paper["authors"] == ["U. Author"]
    assert paper["year"] == 2026
    assert paper["abstract"] == "A."
    assert paper["source"] == "Uploaded PDF"
    assert paper["has_full_text"] is True
    assert client.get("/api/papers").get_json() == [paper]


def test_upload_removes_file_when_extraction_fails(client, monkeypatch, isolated_app):
    def fail_extract(path):
        raise ValueError("No selectable text was found")

    monkeypatch.setattr(isolated_app, "extract_pdf", fail_extract)
    response = client.post(
        "/api/upload",
        data={"pdf": (io.BytesIO(b"%PDF-1.4"), "scan.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "No selectable text" in response.get_json()["error"]
    assert list(isolated_app.UPLOAD_DIR.iterdir()) == []


def test_upload_parses_a_real_small_pdf(client, tmp_path):
    pdf_path = tmp_path / "real-study.pdf"
    document = canvas.Canvas(str(pdf_path))
    document.setTitle("Real PDF Study")
    document.setAuthor("Ada Author; Ben Researcher")
    document.drawString(72, 750, "Real PDF Study")
    document.drawString(72, 730, "Ada Author and Ben Researcher")
    document.drawString(72, 700, "Abstract: A real generated PDF validates the complete upload path.")
    document.drawString(72, 680, "Introduction")
    document.save()

    response = client.post(
        "/api/upload",
        data={"pdf": (io.BytesIO(pdf_path.read_bytes()), "real-study.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    paper = response.get_json()
    assert paper["title"] == "Real PDF Study"
    assert paper["authors"] == ["Ada Author", "Ben Researcher"]
    assert paper["abstract"] == "A real generated PDF validates the complete upload path."
    assert paper["source"] == "Uploaded PDF"
    assert paper["has_full_text"] is True


def test_upload_over_limit_is_rejected_by_flask_without_large_allocation(client, isolated_app):
    original_limit = isolated_app.app.config["MAX_CONTENT_LENGTH"]
    isolated_app.app.config["MAX_CONTENT_LENGTH"] = 128
    try:
        response = client.post(
            "/api/upload",
            data={"pdf": (io.BytesIO(b"x" * 256), "large.pdf")},
            content_type="multipart/form-data",
        )
    finally:
        isolated_app.app.config["MAX_CONTENT_LENGTH"] = original_limit

    assert response.status_code == 413
