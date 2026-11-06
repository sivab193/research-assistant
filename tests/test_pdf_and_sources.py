from __future__ import annotations

from pathlib import Path

import pytest
import requests


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, pages, metadata=None):
        self.pages = [FakePage(text) for text in pages]
        self.metadata = metadata


def test_extract_pdf_uses_metadata_and_bounded_abstract(monkeypatch, isolated_app, tmp_path):
    reader = FakeReader(
        ["Metadata Title\nAda One, Ben Two\nAbstract: A focused result.\n1 Introduction\nBody"],
        {"/Title": "Authoritative Title", "/Author": "Ada One; Ben Two", "/CreationDate": "D:20250101"},
    )
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: reader)

    metadata, full_text = isolated_app.extract_pdf(tmp_path / "paper.pdf")

    assert metadata == {
        "title": "Authoritative Title",
        "authors": ["Ada One", "Ben Two"],
        "year": 2025,
        "abstract": "A focused result.",
    }
    assert full_text.endswith("Body")


def test_extract_pdf_falls_back_to_text_fields(monkeypatch, isolated_app, tmp_path):
    reader = FakeReader(
        ["A Descriptive Paper Title\nAda One and Ben Two\nPublished in 2024\nNo abstract heading here."],
        {"/Title": "Untitled"},
    )
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: reader)

    metadata, _ = isolated_app.extract_pdf(tmp_path / "fallback.pdf")

    assert metadata["title"] == "A Descriptive Paper Title"
    assert metadata["authors"] == ["Ada One", "Ben Two"]
    assert metadata["year"] == 2024
    assert metadata["abstract"].startswith("A Descriptive Paper Title")


def test_extract_pdf_uses_filename_and_unknown_author_when_text_has_no_candidate(
    monkeypatch, isolated_app, tmp_path
):
    reader = FakeReader(["tiny\n7\n8"], {})
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: reader)

    metadata, _ = isolated_app.extract_pdf(tmp_path / "file-name.pdf")

    assert metadata["title"] == "file-name"
    assert metadata["authors"] == ["Unknown"]
    assert metadata["year"] is None


def test_extract_pdf_rejects_pages_without_selectable_text(monkeypatch, isolated_app, tmp_path):
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: FakeReader([None, "   "], {}))

    with pytest.raises(ValueError, match="No selectable text"):
        isolated_app.extract_pdf(tmp_path / "scan.pdf")


def test_extract_pdf_prefers_metadata_year_over_conflicting_text_year(
    monkeypatch, isolated_app, tmp_path
):
    reader = FakeReader(
        ["A Sufficiently Long Paper Title\nAda Author\nThe study was published in 2026."],
        {"/CreationDate": "D:20200101"},
    )
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: reader)

    metadata, _ = isolated_app.extract_pdf(tmp_path / "paper.pdf")

    assert metadata["year"] == 2020


def test_extract_pdf_caps_heading_abstract_at_three_thousand_characters(
    monkeypatch, isolated_app, tmp_path
):
    reader = FakeReader(
        ["A Sufficiently Long Paper Title\nAda Author\nAbstract\n" + ("x" * 3500) + "\nIntroduction"],
        {},
    )
    monkeypatch.setattr(isolated_app, "PdfReader", lambda path: reader)

    metadata, _ = isolated_app.extract_pdf(tmp_path / "paper.pdf")

    assert len(metadata["abstract"]) == 3000
    assert metadata["abstract"] == "x" * 3000


def test_paper_source_prefers_and_truncates_saved_full_text(isolated_app, monkeypatch):
    monkeypatch.setattr(isolated_app, "MAX_SOURCE_CHARS", 5)
    row = {"full_text": "abcdefgh", "pdf_url": None, "abstract": "abstract"}

    assert isolated_app.paper_source(row) == ("abcde", "full PDF text")


def test_paper_source_downloads_extracts_and_persists_open_pdf(
    client, saved_paper, monkeypatch, isolated_app
):
    class Download:
        content = b"%PDF controlled bytes"

        def raise_for_status(self):
            return None

    with isolated_app.get_db() as db:
        db.execute("UPDATE papers SET pdf_url = ? WHERE id = ?", ("https://example.test/p.pdf", saved_paper["id"]))
        row = db.execute("SELECT * FROM papers WHERE id = ?", (saved_paper["id"],)).fetchone()

    monkeypatch.setattr(isolated_app.requests, "get", lambda *args, **kwargs: Download())
    monkeypatch.setattr(isolated_app, "extract_pdf", lambda path: ({}, "downloaded complete text"))

    source, basis = isolated_app.paper_source(row)

    assert (source, basis) == ("downloaded complete text", "open-access PDF text")
    with isolated_app.get_db() as db:
        persisted = db.execute("SELECT pdf_path, full_text FROM papers WHERE id = ?", (saved_paper["id"],)).fetchone()
    assert persisted["full_text"] == "downloaded complete text"
    assert Path(persisted["pdf_path"]).read_bytes() == b"%PDF controlled bytes"


def test_paper_source_falls_back_to_abstract_when_pdf_download_fails(monkeypatch, isolated_app):
    row = {"full_text": None, "pdf_url": "https://example.test/p.pdf", "abstract": "Fallback abstract"}
    monkeypatch.setattr(
        isolated_app.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("offline")),
    )

    assert isolated_app.paper_source(row) == (
        "Fallback abstract",
        "abstract (full text was unavailable)",
    )


def test_paper_source_rejects_paper_without_any_text(isolated_app):
    row = {"full_text": None, "pdf_url": None, "abstract": None}

    with pytest.raises(ValueError, match="no usable text"):
        isolated_app.paper_source(row)


def test_paper_source_skips_oversized_download_and_uses_abstract(monkeypatch, isolated_app):
    class SizedContent:
        def __len__(self):
            return 30 * 1024 * 1024 + 1

    class OversizedDownload:
        content = SizedContent()

        def raise_for_status(self):
            return None

    row = {
        "full_text": None,
        "pdf_url": "https://example.test/oversized.pdf",
        "abstract": "Safe fallback",
    }
    monkeypatch.setattr(isolated_app.requests, "get", lambda *args, **kwargs: OversizedDownload())
    monkeypatch.setattr(isolated_app, "MAX_SOURCE_CHARS", 100)
    monkeypatch.setattr(isolated_app, "extract_pdf", lambda path: pytest.fail("must not parse"))

    assert isolated_app.paper_source(row) == (
        "Safe fallback",
        "abstract (full text was unavailable)",
    )
