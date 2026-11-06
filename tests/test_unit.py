from __future__ import annotations

import sqlite3

import app
import pytest


def test_normalize_semantic_scholar_paper_maps_fields():
    result = app.normalize_search_paper(
        {
            "paperId": "S1",
            "title": "Testing Agents",
            "authors": [{"name": "A. One"}, {"name": "B. Two"}],
            "year": 2025,
            "abstract": "Evidence.",
            "url": "https://example.test/paper",
            "openAccessPdf": {"url": "https://example.test/paper.pdf"},
        }
    )

    assert result == {
        "external_id": "S1",
        "title": "Testing Agents",
        "authors": ["A. One", "B. Two"],
        "year": 2025,
        "abstract": "Evidence.",
        "url": "https://example.test/paper",
        "pdf_url": "https://example.test/paper.pdf",
        "source": "Semantic Scholar",
    }


def test_normalize_openalex_reconstructs_abstract_in_position_order():
    result = app.normalize_openalex_paper(
        {
            "id": "https://openalex.org/W1",
            "title": "Ordered Words",
            "publication_year": 2024,
            "abstract_inverted_index": {"world": [1], "Hello": [0], "again": [2]},
            "authorships": [{"author": {"display_name": "Casey Author"}}],
            "doi": "https://doi.org/10.1/example",
            "best_oa_location": {"pdf_url": "https://example.test/open.pdf"},
        }
    )

    assert result["abstract"] == "Hello world again"
    assert result["authors"] == ["Casey Author"]
    assert result["url"] == "https://doi.org/10.1/example"
    assert result["pdf_url"] == "https://example.test/open.pdf"


def test_row_to_paper_decodes_authors_and_hides_private_text():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT 1 AS id, 'A paper' AS title, '[\"A\", \"B\"]' AS authors, "
        "'secret text' AS full_text, '/tmp/private.pdf' AS pdf_path"
    ).fetchone()

    result = app.row_to_paper(row)
    connection.close()

    assert result["authors"] == ["A", "B"]
    assert result["has_full_text"] is True
    assert "full_text" not in result
    assert "pdf_path" not in result


def test_normalizers_supply_safe_defaults_for_sparse_results():
    semantic = app.normalize_search_paper({})
    openalex = app.normalize_openalex_paper({})

    assert semantic["title"] == "Untitled paper"
    assert semantic["abstract"] == "No abstract available."
    assert openalex["title"] == "Untitled paper"
    assert openalex["abstract"] == "No abstract available."


def test_normalizers_supply_unknown_for_missing_author_names():
    semantic = app.normalize_search_paper({"authors": [{}]})
    openalex = app.normalize_openalex_paper({"authorships": [{"author": {}}]})

    assert semantic["authors"] == ["Unknown"]
    assert openalex["authors"] == ["Unknown"]


@pytest.mark.parametrize(
    ("item", "expected_url", "expected_pdf_url"),
    [
        (
            {
                "id": "W1",
                "doi": "https://doi.org/example",
                "primary_location": {"landing_page_url": "https://landing", "pdf_url": "https://primary.pdf"},
                "best_oa_location": {"pdf_url": "https://best.pdf"},
                "open_access": {"oa_url": "https://oa.pdf"},
            },
            "https://doi.org/example",
            "https://best.pdf",
        ),
        (
            {
                "id": "W2",
                "primary_location": {"landing_page_url": "https://landing", "pdf_url": "https://primary.pdf"},
                "open_access": {"oa_url": "https://oa.pdf"},
            },
            "https://landing",
            "https://primary.pdf",
        ),
        (
            {"id": "W3", "open_access": {"oa_url": "https://oa.pdf"}},
            "W3",
            "https://oa.pdf",
        ),
    ],
)
def test_normalize_openalex_uses_documented_url_fallbacks(item, expected_url, expected_pdf_url):
    result = app.normalize_openalex_paper(item)

    assert result["url"] == expected_url
    assert result["pdf_url"] == expected_pdf_url


def test_row_to_paper_defaults_empty_authors_and_false_full_text():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT 1 AS id, NULL AS authors, '' AS full_text, NULL AS pdf_path"
    ).fetchone()

    result = app.row_to_paper(row)
    connection.close()

    assert result["authors"] == []
    assert result["has_full_text"] is False
    assert "full_text" not in result
    assert "pdf_path" not in result


def test_row_to_paper_surfaces_malformed_authors_json():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT 1 AS id, 'not-json' AS authors, NULL AS full_text, NULL AS pdf_path"
    ).fetchone()

    with pytest.raises(ValueError):
        app.row_to_paper(row)
    connection.close()
