# Atlas — Local AI Research Assistant

Atlas is a small end-to-end research-paper application. It searches Semantic Scholar, saves papers in SQLite, extracts metadata and text from uploaded PDFs, and uses a model running in LM Studio for grounded summaries and question answering.

## Features

- Search Semantic Scholar by topic or keyword, with automatic OpenAlex fallback
- Save results to a persistent local SQLite library
- Upload text-based PDFs and extract title, authors, year, abstract, and full text
- Download an open-access PDF when one is available for a saved search result
- Generate a structured summary based on paper content
- Ask questions with answers constrained to the selected paper
- No cloud LLM key: model inference stays on your Mac through LM Studio

## 1. Set up LM Studio on a Mac mini M4

1. Install and open [LM Studio](https://lmstudio.ai/).
2. Download a chat/instruct model. Good starting choices:
   - `Qwen3-8B` or `Qwen2.5-7B-Instruct` (fast and strong on 16 GB unified memory)
   - `Llama-3.1-8B-Instruct` (widely supported)
   - `Gemma-3-12B-it` in a 4-bit quantization (better quality if you have 24 GB+ memory)
3. Open **Developer → Local Server**, load the model, and start the server on port `1234`.
4. Keep the context length at 16k or higher when memory permits.

The application calls LM Studio's OpenAI-compatible endpoint at `http://127.0.0.1:1234/v1`. LM Studio normally accepts any value in the `model` field when one model is loaded.

## 2. Install and run

```bash
cd ai-research-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

Optional configuration:

```bash
export LM_STUDIO_URL=http://127.0.0.1:1234/v1
export LM_STUDIO_MODEL=your-loaded-model-identifier  # optional; otherwise auto-detected
export MAX_SOURCE_CHARS=70000
export PORT=5000
python app.py
```

## Architecture

- **Frontend:** server-rendered HTML plus vanilla JavaScript and CSS
- **Backend:** Flask JSON API
- **Database:** SQLite at `data/papers.db`
- **PDF processing:** `pypdf`; uploaded PDFs live in `data/uploads/`
- **Paper search:** Semantic Scholar Graph API with automatic OpenAlex fallback (no API key required)
- **Local LLM:** LM Studio OpenAI-compatible Chat Completions API

For searched papers, Atlas first tries to fetch the open-access PDF URL returned by Semantic Scholar. If it cannot obtain full text, it explicitly labels the response as grounded only in the abstract. For uploaded PDFs, it uses extracted full text (up to `MAX_SOURCE_CHARS`). Scanned/image-only PDFs need OCR before upload.

## Demo checklist

1. Search for a topic such as “retrieval augmented generation”.
2. Save a result and open **My library**.
3. Upload a text-based research PDF.
4. Select **Analyze** and generate a summary.
5. Ask “What are the major limitations?”

## Privacy and limitations

Paper text sent for analysis goes only to the configured LM Studio server. Search queries and open-access PDF requests go to external services. Metadata extraction is heuristic, and very large papers are truncated to the configured character limit to fit local model context windows.
