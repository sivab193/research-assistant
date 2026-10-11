# Atlas - AI Research Assistant

Atlas is an end-to-end research-paper application that searches scholarly APIs, stores a local paper library, extracts text from PDFs, and generates grounded summaries and answers. It supports private local inference through LM Studio and free cloud models through OpenRouter.

## Features

- Search Semantic Scholar with automatic OpenAlex fallback
- Save papers in a persistent local SQLite library
- Upload PDFs and extract title, authors, year, abstract, and full text
- Retrieve open-access PDFs when a search provider supplies one
- Generate structured, content-grounded paper summaries
- Ask natural-language questions about a selected paper
- Choose LM Studio, OpenRouter, or local-first automatic fallback
- Keep API keys and local research data out of Git

## Quick start

```bash
git clone https://github.com/sivab193/research-assistant.git
cd research-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open <http://127.0.0.1:5000>.

## Option A: LM Studio (private and local)

1. Install [LM Studio](https://lmstudio.ai/).
2. Download `qwen/qwen3-8b` and select the MLX 4-bit build on Apple Silicon.
3. Load the model and start **Developer -> Local Server** on port `1234`.
4. Configure `.env`:

```dotenv
LLM_PROVIDER=lmstudio
LM_STUDIO_URL=http://127.0.0.1:1234/v1
# Optional. Atlas auto-detects the loaded model when omitted.
# LM_STUDIO_MODEL=qwen3-8b-mlx
```

Paper text stays on your Mac when this provider is selected.

## Option B: OpenRouter free models

1. Create an API key from [OpenRouter Keys](https://openrouter.ai/settings/keys).
2. Configure `.env`:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=openrouter/free
```

`openrouter/free` automatically selects an available free model compatible with the request. You can instead specify any free model slug ending in `:free`. Free capacity and rate limits can change over time.

When OpenRouter is selected, the paper text used for summaries and questions is sent to OpenRouter and its selected inference provider. Review OpenRouter's provider and data policies before uploading sensitive or unpublished papers.

## Option C: Local-first fallback

```dotenv
LLM_PROVIDER=auto
OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=openrouter/free
```

Atlas tries LM Studio first. If the local server is unavailable, it falls back to OpenRouter. Selecting `auto` therefore permits paper content to leave your Mac when local inference fails.

## Search API configuration

Atlas queries Semantic Scholar first and automatically falls back to OpenAlex. Both allow limited unauthenticated access, but a free OpenAlex key provides a larger personal request budget:

```dotenv
OPENALEX_API_KEY=your-openalex-key
```

Search queries and open-access PDF downloads contact external services regardless of the chosen LLM provider.

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `lmstudio` | `lmstudio`, `openrouter`, or `auto` |
| `LM_STUDIO_URL` | `http://127.0.0.1:1234/v1` | LM Studio OpenAI-compatible API |
| `LM_STUDIO_MODEL` | Auto-detected | Optional loaded model identifier |
| `OPENROUTER_API_KEY` | None | Required for OpenRouter |
| `OPENROUTER_MODEL` | `openrouter/free` | OpenRouter model or router slug |
| `OPENALEX_API_KEY` | None | Optional authenticated search key |
| `MAX_SOURCE_CHARS` | `70000` | Maximum paper text sent per request |
| `PORT` | `5000` | Atlas web server port |

## Architecture

- **Frontend:** server-rendered HTML with vanilla JavaScript and CSS
- **Backend:** Flask JSON API
- **Database:** SQLite at `data/papers.db`
- **PDF processing:** `pypdf`; uploaded files are stored in `data/uploads/`
- **Paper search:** Semantic Scholar Graph API and OpenAlex
- **LLM APIs:** LM Studio or OpenRouter's OpenAI-compatible Chat Completions endpoint

For searched papers, Atlas attempts to retrieve the open-access PDF URL returned by the search provider. If full text is unavailable, the response is explicitly labeled as grounded only in the abstract. Uploaded PDFs use extracted full text up to `MAX_SOURCE_CHARS`. Image-only PDFs require OCR before upload.

## Demo checklist

1. Search for a topic such as `retrieval augmented generation`.
2. Save a result and open **My library**.
3. Upload a text-based research PDF.
4. Select **Analyze** and generate a summary.
5. Ask a question such as `What are the major limitations?`

## Security and privacy

- `.env`, `data/`, uploads, and `.venv/` are ignored by Git.
- Never commit API keys or paste them into source code.
- LM Studio keeps inference local.
- OpenRouter sends the selected paper context to a third-party service.
- Metadata extraction is heuristic and should be reviewed for accuracy.
