from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("RESEARCH_ASSISTANT_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "papers.db"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1").rstrip("/")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "70000"))

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=30 * 1024 * 1024)


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '[]',
                year INTEGER,
                abstract TEXT,
                url TEXT,
                pdf_url TEXT,
                pdf_path TEXT,
                full_text TEXT,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def row_to_paper(row: sqlite3.Row) -> dict[str, Any]:
    paper = dict(row)
    paper["authors"] = json.loads(paper.get("authors") or "[]")
    paper["has_full_text"] = bool(paper.get("full_text"))
    paper.pop("full_text", None)
    paper.pop("pdf_path", None)
    return paper


def normalize_search_paper(item: dict[str, Any]) -> dict[str, Any]:
    open_access = item.get("openAccessPdf") or {}
    return {
        "external_id": item.get("paperId"),
        "title": item.get("title") or "Untitled paper",
        "authors": [author.get("name", "Unknown") for author in item.get("authors", [])],
        "year": item.get("year"),
        "abstract": item.get("abstract") or "No abstract available.",
        "url": item.get("url"),
        "pdf_url": open_access.get("url"),
        "source": "Semantic Scholar",
    }


def normalize_openalex_paper(item: dict[str, Any]) -> dict[str, Any]:
    inverted = item.get("abstract_inverted_index") or {}
    ordered_words: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        ordered_words.extend((position, word) for position in positions)
    abstract = " ".join(word for _, word in sorted(ordered_words))
    primary_location = item.get("primary_location") or {}
    best_location = item.get("best_oa_location") or {}
    open_access = item.get("open_access") or {}
    doi = item.get("doi")
    return {
        "external_id": item.get("id"),
        "title": item.get("title") or "Untitled paper",
        "authors": [
            authorship.get("author", {}).get("display_name", "Unknown")
            for authorship in item.get("authorships", [])
        ],
        "year": item.get("publication_year"),
        "abstract": abstract or "No abstract available.",
        "url": doi or primary_location.get("landing_page_url") or item.get("id"),
        "pdf_url": best_location.get("pdf_url") or primary_location.get("pdf_url") or open_access.get("oa_url"),
        "source": "OpenAlex",
    }


def extract_pdf(path: Path) -> tuple[dict[str, Any], str]:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    full_text = "\n\n".join(text for text in pages if text)
    if not full_text:
        raise ValueError("No selectable text was found in this PDF. It may be scanned.")

    metadata = reader.metadata or {}
    lines = [line.strip() for line in full_text[:8000].splitlines() if line.strip()]
    title = str(metadata.get("/Title") or "").strip()
    if not title or title.lower() in {"untitled", "microsoft word"}:
        title = next((line for line in lines[:15] if 12 <= len(line) <= 250), path.stem)

    author_text = str(metadata.get("/Author") or "").strip()
    authors = [name.strip() for name in re.split(r"[,;]", author_text) if name.strip()]
    if not authors:
        probable = next(
            (line for line in lines[1:12] if len(line) < 180 and re.search(r"[A-Za-z]", line)),
            "Unknown",
        )
        authors = [name.strip() for name in re.split(r",|\band\b", probable) if name.strip()]

    year = None
    date_value = str(metadata.get("/CreationDate") or "")
    match = re.search(r"(?:19|20)\d{2}", date_value + "\n" + full_text[:5000])
    if match:
        year = int(match.group())

    abstract = ""
    abstract_match = re.search(
        r"(?is)\babstract\b\s*[:\-—]?\s*(.*?)(?=\n\s*(?:1\.?\s+)?(?:introduction|keywords?|index terms)\b)",
        full_text[:20000],
    )
    if abstract_match:
        abstract = re.sub(r"\s+", " ", abstract_match.group(1)).strip()[:3000]
    if not abstract:
        abstract = re.sub(r"\s+", " ", full_text[:1200]).strip()

    return {"title": title, "authors": authors, "year": year, "abstract": abstract}, full_text


def lm_chat(messages: list[dict[str, str]], temperature: float = 0.15) -> str:
    try:
        response = requests.post(
            f"{LM_STUDIO_URL}/chat/completions",
            json={
                "model": LM_STUDIO_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1200,
                "stream": False,
            },
            timeout=180,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not reach LM Studio. Start its Local Server on port 1234 and load a chat model."
        ) from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("LM Studio returned an unexpected response.") from exc


def paper_source(row: sqlite3.Row) -> tuple[str, str]:
    if row["full_text"]:
        return row["full_text"][:MAX_SOURCE_CHARS], "full PDF text"
    if row["pdf_url"]:
        try:
            response = requests.get(row["pdf_url"], timeout=45, headers={"User-Agent": "ResearchAssistant/1.0"})
            response.raise_for_status()
            if len(response.content) <= 30 * 1024 * 1024:
                target = UPLOAD_DIR / f"download-{row['id']}.pdf"
                target.write_bytes(response.content)
                _, text = extract_pdf(target)
                with get_db() as db:
                    db.execute("UPDATE papers SET pdf_path = ?, full_text = ? WHERE id = ?", (str(target), text, row["id"]))
                return text[:MAX_SOURCE_CHARS], "open-access PDF text"
        except (requests.RequestException, ValueError, OSError):
            pass
    if row["abstract"]:
        return row["abstract"], "abstract (full text was unavailable)"
    raise ValueError("This paper has no usable text. Upload its PDF to analyze it.")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def config():
    return jsonify({"lm_studio_url": LM_STUDIO_URL, "model": LM_STUDIO_MODEL})


@app.get("/api/health")
def health():
    lm_ok = False
    try:
        lm_ok = requests.get(f"{LM_STUDIO_URL}/models", timeout=2).ok
    except requests.RequestException:
        pass
    return jsonify({"app": "ok", "lm_studio": lm_ok})


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"error": "Enter at least two characters."}), 400
    semantic_error = None
    try:
        response = requests.get(
            SEMANTIC_SCHOLAR_URL,
            params={
                "query": query,
                "limit": min(int(request.args.get("limit", 10)), 20),
                "fields": "title,authors,year,abstract,url,openAccessPdf",
            },
            headers={"User-Agent": "AIResearchAssistant/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        return jsonify([normalize_search_paper(item) for item in response.json().get("data", [])])
    except (requests.RequestException, ValueError) as exc:
        semantic_error = exc

    try:
        response = requests.get(
            OPENALEX_URL,
            params={
                "search": query,
                "per-page": min(int(request.args.get("limit", 10)), 20),
                **({"api_key": OPENALEX_API_KEY} if OPENALEX_API_KEY else {}),
            },
            headers={"User-Agent": "AIResearchAssistant/1.0 (mailto:local@example.com)"},
            timeout=20,
        )
        response.raise_for_status()
        return jsonify([normalize_openalex_paper(item) for item in response.json().get("results", [])])
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"error": f"Paper search failed through both providers: {semantic_error}; {exc}"}), 502


@app.get("/api/papers")
def list_papers():
    with get_db() as db:
        rows = db.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
    return jsonify([row_to_paper(row) for row in rows])


@app.post("/api/papers")
def save_paper():
    data = request.get_json(silent=True) or {}
    if not str(data.get("title", "")).strip():
        return jsonify({"error": "A title is required."}), 400
    authors = data.get("authors") if isinstance(data.get("authors"), list) else []
    external_id = data.get("external_id") or f"manual:{uuid.uuid4()}"
    try:
        with get_db() as db:
            cursor = db.execute(
                """INSERT INTO papers
                (external_id, title, authors, year, abstract, url, pdf_url, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    external_id,
                    str(data["title"]).strip(),
                    json.dumps(authors),
                    data.get("year"),
                    data.get("abstract"),
                    data.get("url"),
                    data.get("pdf_url"),
                    data.get("source", "Search"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            row = db.execute("SELECT * FROM papers WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(row_to_paper(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "This paper is already in your library."}), 409


@app.post("/api/upload")
def upload_pdf():
    upload = request.files.get("pdf")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose a PDF file."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted."}), 400
    filename = f"{uuid.uuid4().hex}-{secure_filename(upload.filename)}"
    target = UPLOAD_DIR / filename
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload.save(target)
    try:
        metadata, full_text = extract_pdf(target)
        with get_db() as db:
            cursor = db.execute(
                """INSERT INTO papers
                (external_id, title, authors, year, abstract, pdf_path, full_text, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Uploaded PDF', ?)""",
                (
                    f"upload:{uuid.uuid4()}", metadata["title"], json.dumps(metadata["authors"]),
                    metadata["year"], metadata["abstract"], str(target), full_text,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            row = db.execute("SELECT * FROM papers WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(row_to_paper(row)), 201
    except Exception as exc:
        target.unlink(missing_ok=True)
        return jsonify({"error": f"Could not process PDF: {exc}"}), 400


@app.delete("/api/papers/<int:paper_id>")
def delete_paper(paper_id: int):
    with get_db() as db:
        row = db.execute("SELECT pdf_path FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            return jsonify({"error": "Paper not found."}), 404
        db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    if row["pdf_path"]:
        Path(row["pdf_path"]).unlink(missing_ok=True)
    return "", 204


@app.post("/api/papers/<int:paper_id>/summarize")
def summarize(paper_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        return jsonify({"error": "Paper not found."}), 404
    try:
        source, basis = paper_source(row)
        prompt = f"""Summarize the research paper below. Be faithful to the provided text and do not invent facts.
Use these headings: Research problem, Approach, Key findings, Evidence or datasets, Limitations, Takeaway.
If a detail is absent, say it is not stated in the provided text.

TITLE: {row['title']}
SOURCE BASIS: {basis}
PAPER TEXT:
{source}"""
        answer = lm_chat([{"role": "system", "content": "You are a careful academic research assistant."}, {"role": "user", "content": prompt}])
        return jsonify({"answer": answer, "basis": basis})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503


@app.post("/api/papers/<int:paper_id>/ask")
def ask(paper_id: int):
    question = str((request.get_json(silent=True) or {}).get("question", "")).strip()
    if not question:
        return jsonify({"error": "Enter a question."}), 400
    with get_db() as db:
        row = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        return jsonify({"error": "Paper not found."}), 404
    try:
        source, basis = paper_source(row)
        prompt = f"""Answer the question using only the supplied paper text. If the answer is not supported, say so clearly.
Give a concise answer and end with a short 'Evidence:' section quoting or paraphrasing the relevant passage.

TITLE: {row['title']}
SOURCE BASIS: {basis}
QUESTION: {question}
PAPER TEXT:
{source}"""
        answer = lm_chat([{"role": "system", "content": "You answer questions grounded in research papers."}, {"role": "user", "content": prompt}])
        return jsonify({"answer": answer, "basis": basis})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503


init_db()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
